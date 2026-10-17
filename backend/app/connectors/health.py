"""Availability of a user's connections, while someone is watching.

The topic lives here rather than in ``app/realtime`` because it is about
connectors: the transport carries it without knowing what it is. Registration
at the bottom of this file is the whole of what the socket has to learn.

A probe deliberately does not borrow from the pool. A check is meant to
exercise the credentials and the route to the server — the same reasoning that
already keeps the manual check out of the pool — and a pooled connection would
report a source as up after its password stopped working.
"""

import asyncio
import contextlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel

from app.adapters.errors import UNANSWERED
from app.adapters.protocol import ConnectionCheckResult, DataAdapter
from app.adapters.registry import UnknownAdapterType
from app.adapters.registry import get as get_adapter
from app.connectors import crud, service
from app.connectors.access import context_for
from app.connectors.models import Connector
from app.core.config import settings
from app.core.db import async_session_maker
from app.core.schemas import get_datetime_utc
from app.core.translation import current_language, say
from app.realtime.topics import Subscriber, TopicSet, UnknownTopic, register
from app.users import preferences

NAME = "connector.health"


class ConnectorHealth(BaseModel):
    """What the last probe of one connection said, and when.

    The result is the same model the manual check answers with, nested rather
    than restated: it already reduces a driver failure to a kind and a safe
    message, and a second copy of those fields would be a second place for the
    password to leak through.
    """

    connector_id: uuid.UUID
    result: ConnectionCheckResult
    checked_at: datetime


def delay_after(*, misses: int, base: float, cap: float) -> float:
    """How long before probing a connection again.

    A dead host answers by timing out, so probing it as often as a live one
    makes every round as slow as its worst member. The wait doubles per failure
    and stops at the cap; the cap wins outright, so settings that put it below
    the interval still produce a sane number.
    """
    doublings = min(misses, 32)
    return min(base * float(2**doublings), cap)


@dataclass
class _Probe:
    """What the monitor remembers about one connection between rounds."""

    misses: int = 0
    due_at: float = 0.0


@dataclass
class _Watch:
    """One user's watchers, what is known about them, and the task doing it."""

    subscribers: set[Subscriber] = field(default_factory=set)
    known: dict[uuid.UUID, ConnectorHealth] = field(default_factory=dict)
    # Since when each connection has not been reached, until a check reaches
    # it again: what the search skips and says so of (D200). A server that
    # refused the password or a key that is locked was reached, and the search
    # asks it so the failure is said as what it is (D201).
    down_since: dict[uuid.UUID, datetime] = field(default_factory=dict)
    task: asyncio.Task[None] | None = None
    stopping: asyncio.Task[None] | None = None


class HealthTopic:
    """One monitor per user, alive only while that user is watching.

    Per user rather than per socket: two tabs of the same person would
    otherwise double the traffic to somebody else's database for the sake of
    the same coloured dot. A second socket is handed what is already known and
    costs nothing.
    """

    def __init__(self) -> None:
        self._watches: dict[uuid.UUID, _Watch] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, subscriber: Subscriber) -> None:
        async with self._lock:
            watch = self._watches.setdefault(subscriber.user_id, _Watch())
            watch.subscribers.add(subscriber)
            if watch.stopping is not None:
                watch.stopping.cancel()
                watch.stopping = None
            if watch.task is None:
                watch.task = asyncio.create_task(self._monitor(subscriber.user_id))
            snapshot = list(watch.known.values())

        for health in snapshot:
            await self._deliver(subscriber, health)

    async def unsubscribe(self, subscriber: Subscriber) -> None:
        async with self._lock:
            watch = self._watches.get(subscriber.user_id)
            if watch is None:
                return
            watch.subscribers.discard(subscriber)
            if watch.subscribers:
                return
            grace = settings.HEALTH_GRACE_SECONDS

        if grace <= 0:
            await self._stop(subscriber.user_id)
            return

        # A reloaded page closes one socket and opens another. Without the
        # grace the monitor would be torn down and rebuilt every time, and the
        # new one would start from knowing nothing.
        async with self._lock:
            watch = self._watches[subscriber.user_id]
            watch.stopping = asyncio.create_task(
                self._stop_later(subscriber.user_id, grace)
            )

    async def aclose(self) -> None:
        for user_id in list(self._watches):
            await self._stop(user_id)

    async def _stop_later(self, user_id: uuid.UUID, grace: float) -> None:
        await asyncio.sleep(grace)
        await self._stop(user_id)

    async def _stop(self, user_id: uuid.UUID) -> None:
        async with self._lock:
            watch = self._watches.pop(user_id, None)
        if watch is None:
            return
        for task in (watch.task, watch.stopping):
            if task is None or task is asyncio.current_task():
                continue
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _deliver(self, subscriber: Subscriber, health: ConnectorHealth) -> None:
        # A socket that has gone away is not this topic's problem to report:
        # the route that owns it unsubscribes it in its own teardown.
        with contextlib.suppress(Exception):
            await subscriber.deliver(NAME, health)

    async def _announce(self, user_id: uuid.UUID, health: ConnectorHealth) -> None:
        async with self._lock:
            watch = self._watches.get(user_id)
            if watch is None:
                return
            watch.known[health.connector_id] = health
            if health.result.error_kind in UNANSWERED:
                watch.down_since.setdefault(health.connector_id, health.checked_at)
            else:
                watch.down_since.pop(health.connector_id, None)
            subscribers = list(watch.subscribers)
        for subscriber in subscribers:
            await self._deliver(subscriber, health)

    def unreachable(self, user_id: uuid.UUID) -> dict[uuid.UUID, datetime]:
        """The connections this person's monitor last could not reach, and since when.

        Only while somebody watches: with no socket open nothing is probed, and
        nothing here claims a connection is down.
        """
        watch = self._watches.get(user_id)
        return {} if watch is None else dict(watch.down_since)

    async def record(self, user_id: uuid.UUID, health: ConnectorHealth) -> None:
        """Take in a result the monitor did not produce.

        The manual check goes through here, so pressing the button and the dot
        cannot end up saying different things about the same connection.
        """
        await self._announce(user_id, health)

    async def _monitor(self, user_id: uuid.UUID) -> None:
        probes: dict[uuid.UUID, _Probe] = {}
        loop = asyncio.get_running_loop()
        while True:
            cap = settings.HEALTH_BACKOFF_CAP_SECONDS
            async with async_session_maker() as session:
                chosen = await preferences.of(session, user_id)
                connectors = await crud.visible_enabled_of(session, user_id=user_id)

            # Read every round rather than when the watch opened: somebody
            # changing how often their connections are probed is looking at
            # the dots while they do it.
            base = preferences.check_seconds(chosen.connector_checks)
            # What a probe says is worded in the account's language; with none
            # chosen, in the one of the socket that started the watch (D226).
            if chosen.language is not None:
                current_language.set(chosen.language)

            live = {connector.id for connector in connectors}
            for gone in set(probes) - live:
                del probes[gone]
                await self._forget(user_id, gone)

            if base is None:
                # Asked for no rounds at all. Nothing is probed, and what was
                # probed before is dropped so that switching back on starts
                # with a round rather than with a stale answer.
                for known in list(probes):
                    del probes[known]
                    await self._forget(user_id, known)
                await asyncio.sleep(settings.HEALTH_INTERVAL_SECONDS)
                continue

            now = loop.time()
            due = [c for c in connectors if probes.get(c.id, _Probe()).due_at <= now]
            await self._probe_all(user_id, due, probes, base=base, cap=cap)

            # The round is the server's tick and the choice is what falls due
            # inside it, so a long interval does not also make a change of
            # mind take that long to notice.
            await asyncio.sleep(min(base, settings.HEALTH_INTERVAL_SECONDS))

    async def _forget(self, user_id: uuid.UUID, connector_id: uuid.UUID) -> None:
        """Drop what is known about a connection that left the round.

        Deleted, or switched off. Either way a stale result would have the dot
        claiming something about a source nobody is probing any more.
        """
        async with self._lock:
            watch = self._watches.get(user_id)
            if watch is not None:
                watch.known.pop(connector_id, None)
                watch.down_since.pop(connector_id, None)

    async def _probe_all(
        self,
        user_id: uuid.UUID,
        connectors: list[Connector],
        probes: dict[uuid.UUID, _Probe],
        *,
        base: float,
        cap: float,
    ) -> None:
        limit = asyncio.Semaphore(settings.HEALTH_CONCURRENCY)
        loop = asyncio.get_running_loop()

        async def one(connector: Connector) -> None:
            async with limit:
                result = await _probe(connector)
            probe = probes.setdefault(connector.id, _Probe())
            probe.misses = 0 if result.ok else probe.misses + 1
            probe.due_at = loop.time() + delay_after(
                misses=probe.misses, base=base, cap=cap
            )
            await self._announce(
                user_id,
                ConnectorHealth(
                    connector_id=connector.id,
                    result=result,
                    checked_at=get_datetime_utc(),
                ),
            )

        async with asyncio.TaskGroup() as group:
            for connector in connectors:
                group.create_task(one(connector))


def _adapter(connector: Connector) -> DataAdapter:
    adapter_type = get_adapter(connector.adapter_type)
    options = service.merge_options(connector.config, connector.secrets)
    return service.build_adapter(
        adapter_type,
        options,
        context_for(connector.owner_id),
    )


async def _probe(connector: Connector) -> ConnectionCheckResult:
    """One probe, which never raises.

    A background round must not end because one source misbehaved, and a
    source type that has been removed from the registry since the connector
    was stored is a reason to report it down, not to stop watching the rest.
    """
    try:
        async with asyncio.timeout(settings.HEALTH_PROBE_TIMEOUT_SECONDS):
            return await _adapter(connector).check_connection()
    except TimeoutError:
        return ConnectionCheckResult(
            ok=False,
            message=say("The source did not answer in time"),
            error_kind="timeout",
        )
    except UnknownAdapterType:
        return ConnectionCheckResult(
            ok=False, message=say("This source type is no longer available")
        )
    except Exception:
        # Deliberately without the text: a driver message carries the
        # connection string, password included.
        return ConnectionCheckResult(
            ok=False, message=say("The check could not be made")
        )


async def announce_check(
    topics: TopicSet,
    user_id: uuid.UUID,
    connector_id: uuid.UUID,
    result: ConnectionCheckResult,
) -> None:
    """Hand a manually made check to whoever is watching.

    Nothing happens if nobody is: the topic keeps what is known only for users
    with a socket open.
    """
    try:
        topic = topics.get(NAME)
    except UnknownTopic:
        return
    if not isinstance(topic, HealthTopic):
        return
    await topic.record(
        user_id,
        ConnectorHealth(
            connector_id=connector_id, result=result, checked_at=get_datetime_utc()
        ),
    )


def unreachable_of(topics: TopicSet, user_id: uuid.UUID) -> dict[uuid.UUID, datetime]:
    """What `HealthTopic.unreachable` says, for a caller that holds the topics."""
    try:
        topic = topics.get(NAME)
    except UnknownTopic:
        return {}
    if not isinstance(topic, HealthTopic):
        return {}
    return topic.unreachable(user_id)


register(NAME, HealthTopic)
