"""What changed on a connection, told while somebody looks at it (D303).

A screen says which nodes it shows on a connection — the levels open in its
catalog, the tabs open on its nodes — through the route below, again every
half minute while it shows them. The source watches those and the topic
tells every socket of that person which levels and nodes to read again. A
watch nobody renewed within the lease is closed, as is one asked for nothing.

Per person and connection rather than per socket, for the reason health is per
person (D19): two tabs showing the same znode need one watch, not two. What one
tab shows replaces what was asked before, so two tabs showing different nodes
of one connection watch the last one's; the other refreshes by hand.
"""

import asyncio
import contextlib
import logging
import uuid
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from app.adapters.changes import Changed, ChangeWatch, SupportsChangeWatch
from app.adapters.protocol import AdapterError
from app.adapters.resources import ResourcesDep
from app.connectors.access import resolve_adapter
from app.core.db import SessionDep
from app.core.problems import Problem
from app.realtime.topics import Subscriber, TopicsDep, register
from app.users.deps import CurrentUser

logger = logging.getLogger(__name__)

NAME = "source.changes"

# How long a screen's word holds without being said again, and how often the
# topic looks for words that ran out. The screen says it every thirty seconds.
LEASE_SECONDS = 90.0
REAP_SECONDS = 15.0

# How long changes are gathered before they are told, so a burst of writes is
# one refresh rather than a hundred.
GATHER_SECONDS = 0.3

# Past this many levels and nodes in one telling, the screen reads everything
# of the connection again rather than being told each one.
MAX_TOLD = 200

MAX_FOLLOWED = 300


class SourceChanges(BaseModel):
    """What to read again on one connection. None among the levels is its top."""

    connector_id: uuid.UUID
    levels: list[str | None] = Field(default_factory=list)
    nodes: list[str] = Field(default_factory=list)
    everything: bool = False


@dataclass
class _Follow:
    watch: ChangeWatch
    expires_at: float
    levels: set[str | None] = field(default_factory=set)
    nodes: set[str] = field(default_factory=set)
    flush: asyncio.TimerHandle | None = None


class SourceChangesTopic:
    def __init__(self) -> None:
        self._subscribers: dict[uuid.UUID, set[Subscriber]] = {}
        self._follows: dict[tuple[uuid.UUID, uuid.UUID], _Follow] = {}
        self._lock = asyncio.Lock()
        self._reaper: asyncio.Task[None] | None = None

    async def subscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.setdefault(subscriber.user_id, set()).add(subscriber)

    async def unsubscribe(self, subscriber: Subscriber) -> None:
        mine = self._subscribers.get(subscriber.user_id)
        if mine is not None:
            mine.discard(subscriber)
            if not mine:
                del self._subscribers[subscriber.user_id]

    async def follow(
        self,
        user_id: uuid.UUID,
        connector_id: uuid.UUID,
        source: SupportsChangeWatch,
        node_ids: list[str | None],
    ) -> None:
        """Watch these on this connection for this person, or stop when none."""
        key = (user_id, connector_id)
        loop = asyncio.get_running_loop()
        async with self._lock:
            known = self._follows.get(key)
            if not node_ids:
                if known is not None:
                    del self._follows[key]
            elif known is None:
                watch = await source.watch_changes(self._sink(loop, key))
                known = self._follows[key] = _Follow(
                    watch=watch, expires_at=loop.time() + LEASE_SECONDS
                )
            else:
                known.expires_at = loop.time() + LEASE_SECONDS
            if self._reaper is None:
                self._reaper = asyncio.create_task(self._reap())
        if not node_ids:
            if known is not None:
                await _closed(known)
            return
        assert known is not None
        await known.watch.follow(node_ids)

    def _sink(
        self, loop: asyncio.AbstractEventLoop, key: tuple[uuid.UUID, uuid.UUID]
    ) -> _Sink:
        return _Sink(self, loop, key)

    def note(self, key: tuple[uuid.UUID, uuid.UUID], changed: Changed) -> None:
        """Gather one change, on the loop; told after a moment with the rest."""
        known = self._follows.get(key)
        if known is None:
            return
        known.levels |= changed.levels
        known.nodes |= changed.nodes
        if known.flush is None:
            loop = asyncio.get_running_loop()
            known.flush = loop.call_later(
                GATHER_SECONDS, lambda: asyncio.ensure_future(self._tell(key))
            )

    async def _tell(self, key: tuple[uuid.UUID, uuid.UUID]) -> None:
        known = self._follows.get(key)
        if known is None:
            return
        levels, nodes = known.levels, known.nodes
        known.levels, known.nodes, known.flush = set(), set(), None
        user_id, connector_id = key
        everything = len(levels) + len(nodes) > MAX_TOLD
        told = SourceChanges(
            connector_id=connector_id,
            levels=[] if everything else sorted(levels, key=lambda one: one or ""),
            nodes=[] if everything else sorted(nodes),
            everything=everything,
        )
        for subscriber in list(self._subscribers.get(user_id, ())):
            with contextlib.suppress(Exception):
                await subscriber.deliver(NAME, told)

    async def _reap(self) -> None:
        while True:
            await asyncio.sleep(REAP_SECONDS)
            now = asyncio.get_running_loop().time()
            async with self._lock:
                expired = [key for key, one in self._follows.items() if one.expires_at <= now]
                gone = [self._follows.pop(key) for key in expired]
            for one in gone:
                await _closed(one)

    async def aclose(self) -> None:
        if self._reaper is not None:
            self._reaper.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reaper
            self._reaper = None
        async with self._lock:
            follows = list(self._follows.values())
            self._follows.clear()
        for one in follows:
            await _closed(one)


@dataclass(frozen=True)
class _Sink:
    """What a source calls from its driver's thread: moved onto the loop."""

    topic: SourceChangesTopic
    loop: asyncio.AbstractEventLoop
    key: tuple[uuid.UUID, uuid.UUID]

    def __call__(self, changed: Changed) -> None:
        with contextlib.suppress(RuntimeError):
            self.loop.call_soon_threadsafe(self.topic.note, self.key, changed)


async def _closed(follow: _Follow) -> None:
    if follow.flush is not None:
        follow.flush.cancel()
    try:
        await follow.watch.close()
    except Exception:  # noqa: BLE001 - a watch already gone has nothing to close
        logger.debug("A change watch did not close cleanly", exc_info=True)


register(NAME, SourceChangesTopic)


# --- the route a screen says what it shows through ---------------------------

router = APIRouter(prefix="/connectors", tags=["connectors"])


class FollowRequest(BaseModel):
    """The nodes a screen shows on one connection; empty stops the watch."""

    node_ids: Annotated[list[str | None], Field(max_length=MAX_FOLLOWED)] = Field(
        default_factory=list
    )


@router.post("/{connector_id}/changes/follow", status_code=204)
async def follow_changes(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    topics: TopicsDep,
    connector_id: uuid.UUID,
    body: FollowRequest,
) -> Response:
    """Watch what this screen shows on this connection for half a minute more (D303)."""
    adapter, _ = await resolve_adapter(
        session, connector_id, current_user, resources, requires="read"
    )
    if not isinstance(adapter, SupportsChangeWatch):
        raise Problem(501, "connectors.no_live_changes", error_kind="config")
    topic = topics.get(NAME)
    if not isinstance(topic, SourceChangesTopic):
        raise RuntimeError("The source.changes topic is not this one")
    try:
        await topic.follow(current_user.id, connector_id, adapter, body.node_ids)
    except AdapterError as failure:
        raise HTTPException(
            status_code=502,
            detail={"message": failure.message, "error_kind": failure.error_kind},
        ) from None
    return Response(status_code=204)
