"""New letters in a user's own mailboxes, while that user is in the application (D372).

Built as `connector.health` is (D19): a monitor per user, started by the first
subscriber and stopped after a grace when the last one leaves. A round asks
each mailbox one STATUS of its inbox and reads headings only when its UIDNEXT
has moved.
"""

import asyncio
import contextlib
import logging
import uuid
from dataclasses import dataclass, field

from pydantic import BaseModel
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.mailbox import InboxMark, MessageHeading, SupportsMailbox
from app.adapters.registry import UnknownAdapterType
from app.adapters.registry import get as get_adapter
from app.connectors import service
from app.connectors.access import context_for
from app.connectors.health import delay_after
from app.connectors.models import Connector
from app.core.config import settings
from app.core.db import async_session_maker
from app.realtime.topics import Subscriber, register

NAME = "mail.arrivals"

logger = logging.getLogger(__name__)


class MailArrivals(BaseModel):
    connector_id: uuid.UUID
    # The inbox's unread letters now.
    unseen: int
    # How many arrived since the last round; none on the first one.
    count: int
    # The newest of them, newest first, at most three.
    newest: list[MessageHeading]


@dataclass
class _Mailbox:
    mark: InboxMark | None = None
    misses: int = 0
    due_at: float = 0.0


@dataclass
class _Watch:
    subscribers: set[Subscriber] = field(default_factory=set)
    # The last unread count of each mailbox, handed to a second socket.
    unseen: dict[uuid.UUID, int] = field(default_factory=dict)
    task: asyncio.Task[None] | None = None
    stopping: asyncio.Task[None] | None = None


class ArrivalsTopic:
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
            known = dict(watch.unseen)
        for connector_id, unseen in known.items():
            await self._deliver(
                subscriber,
                MailArrivals(connector_id=connector_id, unseen=unseen, count=0, newest=[]),
            )

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
        async with self._lock:
            watch = self._watches[subscriber.user_id]
            watch.stopping = asyncio.create_task(self._stop_later(subscriber.user_id, grace))

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

    async def _deliver(self, subscriber: Subscriber, event: MailArrivals) -> None:
        with contextlib.suppress(Exception):
            await subscriber.deliver(NAME, event)

    async def _announce(self, user_id: uuid.UUID, event: MailArrivals) -> None:
        async with self._lock:
            watch = self._watches.get(user_id)
            if watch is None:
                return
            before = watch.unseen.get(event.connector_id)
            watch.unseen[event.connector_id] = event.unseen
            subscribers = list(watch.subscribers)
        # Nothing new and nothing changed is not worth a frame.
        if event.count == 0 and before == event.unseen:
            return
        for subscriber in subscribers:
            await self._deliver(subscriber, event)

    async def _monitor(self, user_id: uuid.UUID) -> None:
        boxes: dict[uuid.UUID, _Mailbox] = {}
        loop = asyncio.get_running_loop()
        while True:
            base = settings.MAIL_ARRIVALS_INTERVAL_SECONDS
            async with async_session_maker() as session:
                connectors = await _own_mailboxes(session, user_id)
            live = {connector.id for connector in connectors}
            for gone in set(boxes) - live:
                del boxes[gone]
                async with self._lock:
                    watch = self._watches.get(user_id)
                    if watch is not None:
                        watch.unseen.pop(gone, None)
            now = loop.time()
            for connector in connectors:
                box = boxes.setdefault(connector.id, _Mailbox())
                if box.due_at > now:
                    continue
                event = await self._look(connector, box)
                box.due_at = loop.time() + delay_after(
                    misses=box.misses, base=base, cap=settings.HEALTH_BACKOFF_CAP_SECONDS
                )
                if event is not None:
                    await self._announce(user_id, event)
            await asyncio.sleep(base)

    async def _look(self, connector: Connector, box: _Mailbox) -> MailArrivals | None:
        """One mailbox's inbox, which never raises: one bad mailbox stops no round."""
        mailbox = _mailbox(connector)
        if mailbox is None:
            return None
        try:
            async with asyncio.timeout(settings.HEALTH_PROBE_TIMEOUT_SECONDS * 4):
                found = await mailbox.inbox_arrivals(box.mark)
        except Exception as failure:  # noqa: BLE001 - reduced to a miss; a driver's text names the host
            box.misses += 1
            logger.info("Mail arrivals not read: %s", type(failure).__name__)
            return None
        box.misses = 0
        box.mark = found.mark
        return MailArrivals(
            connector_id=connector.id, unseen=found.unseen, count=found.count, newest=found.newest
        )


async def _own_mailboxes(session: AsyncSession, user_id: uuid.UUID) -> list[Connector]:
    """The user's own switched-on connections whose type is a mailbox.

    Own only: a grantee cannot open somebody's mailbox (D367), so nobody else
    is told what arrived in it.
    """
    statement = select(Connector).where(
        col(Connector.owner_id) == user_id, col(Connector.enabled).is_(True)
    )
    found = list((await session.exec(statement)).all())
    return [connector for connector in found if _is_mailbox_type(connector.adapter_type)]


def _is_mailbox_type(name: str) -> bool:
    try:
        return issubclass(get_adapter(name).adapter_class, SupportsMailbox)
    except UnknownAdapterType:
        return False


def _mailbox(connector: Connector) -> SupportsMailbox | None:
    try:
        adapter_type = get_adapter(connector.adapter_type)
        options = service.merge_options(connector.config, connector.secrets)
        adapter = service.build_adapter(adapter_type, options, context_for(connector.owner_id))
    except Exception:  # noqa: BLE001 - a stored connection that no longer builds is skipped
        return None
    return adapter if isinstance(adapter, SupportsMailbox) else None


register(NAME, ArrivalsTopic)
