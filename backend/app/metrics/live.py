"""New points on the socket, while somebody watches (D127).

A subscription names nothing: `metrics.points` pushes the new points of every
series its subscriber may read, and the screen keeps those it draws. The
alternative — arguments on the subscribe frame — would change the transport
every topic shares (D18) for a stream that is small anyway: an agent reports a
few dozen series every half minute.

No channel between processes: the metrics process writes the store, and one
monitor per watching user reads it every couple of seconds, the arrangement
D19 has for connection health.
"""

import asyncio
import contextlib
import logging
import time
import uuid
from dataclasses import dataclass, field

from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.core.db import async_session_maker
from app.metrics.access import readable_sources
from app.metrics.holder import StoreHolder
from app.metrics.store import MetricsStore, StoreUnavailable
from app.realtime.topics import Subscriber, register

NAME = "metrics.points"

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 2.0
GRACE_SECONDS = 5.0
# Points one round may carry. A host that was silent and comes back with a
# backlog is read by its history, not replayed through the socket.
MAX_POINTS_PER_ROUND = 2000
# The collector marks a series seen before its batch of points is written, up
# to a second later. A series seen longer ago than this with no newer point has
# none coming, and is not asked about again.
SETTLED_SECONDS = 10


class SeriesPoints(BaseModel):
    series_id: int
    # [ts, value], seconds, oldest first.
    points: list[list[float]]


class LivePoints(BaseModel):
    series: list[SeriesPoints]


@dataclass
class _Watch:
    subscribers: set[Subscriber] = field(default_factory=set)
    task: asyncio.Task[None] | None = None
    stopping: asyncio.Task[None] | None = None


class Watermarks:
    """What has been pushed already, per series. Pure, so a round can be tested."""

    def __init__(self, started: int) -> None:
        self._started = started
        self._pushed: dict[int, int] = {}
        self._first = True

    def changed(self, seen: dict[int, int]) -> dict[int, int]:
        """Series written since last pushed, with the moment to read after.

        The first round only remembers: whoever subscribed has just read the
        history. A series born after the subscription is read from then on.
        """
        if self._first:
            self._pushed = dict(seen)
            self._first = False
            return {}
        return {
            series_id: self._pushed.get(series_id, self._started)
            for series_id, last in seen.items()
            if last > self._pushed.get(series_id, self._started)
        }

    def advance(self, series_id: int, ts: int) -> None:
        self._pushed[series_id] = max(ts, self._pushed.get(series_id, self._started))


class LiveTopic:
    def __init__(self) -> None:
        self._watches: dict[uuid.UUID, _Watch] = {}
        self._lock = asyncio.Lock()
        # Its own handle on the store: topics are built before anything else the
        # lifespan makes, and the handle is small.
        self._stores = StoreHolder()

    async def subscribe(self, subscriber: Subscriber) -> None:
        async with self._lock:
            watch = self._watches.setdefault(subscriber.user_id, _Watch())
            watch.subscribers.add(subscriber)
            if watch.stopping is not None:
                watch.stopping.cancel()
                watch.stopping = None
            if watch.task is None:
                watch.task = asyncio.create_task(self._monitor(subscriber.user_id))

    async def unsubscribe(self, subscriber: Subscriber) -> None:
        async with self._lock:
            watch = self._watches.get(subscriber.user_id)
            if watch is None:
                return
            watch.subscribers.discard(subscriber)
            if watch.subscribers:
                return
            watch.stopping = asyncio.create_task(self._stop_later(subscriber.user_id))

    async def aclose(self) -> None:
        for user_id in list(self._watches):
            await self._stop(user_id)
        await self._stores.aclose()

    async def _stop_later(self, user_id: uuid.UUID) -> None:
        await asyncio.sleep(GRACE_SECONDS)
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

    async def _monitor(self, user_id: uuid.UUID) -> None:
        marks = Watermarks(started=int(time.time()))
        while True:
            try:
                await self._round(user_id, marks)
            except (StoreUnavailable, SQLAlchemyError, OSError):
                logger.info("A round of live points was skipped", exc_info=True)
            await asyncio.sleep(INTERVAL_SECONDS)

    async def _round(self, user_id: uuid.UUID, marks: Watermarks) -> None:
        async with async_session_maker() as session:
            store = await self._stores.get(session)
            sources = sorted(await readable_sources(session, user_id))
        if store is None:
            return
        payload = await read_round(store, sources, marks, now=int(time.time()))
        if payload is None:
            return
        async with self._lock:
            watch = self._watches.get(user_id)
            subscribers = list(watch.subscribers) if watch is not None else []
        for subscriber in subscribers:
            with contextlib.suppress(Exception):
                await subscriber.deliver(NAME, payload)


async def read_round(
    store: MetricsStore, sources: list[uuid.UUID], marks: Watermarks, *, now: int
) -> LivePoints | None:
    """One round: the points written since the last one, or None."""
    seen = await store.seen(sources)
    changed = marks.changed(seen)
    if not changed:
        return None
    rows = await store.points_after(sorted(changed), min(changed.values()), MAX_POINTS_PER_ROUND)
    grouped: dict[int, list[list[float]]] = {}
    for row in rows:
        if row.ts <= changed[row.series_id]:
            continue
        grouped.setdefault(row.series_id, []).append([float(row.ts), row.value])
        marks.advance(row.series_id, row.ts)
    if len(rows) < MAX_POINTS_PER_ROUND:
        for series_id in changed:
            if seen[series_id] < now - SETTLED_SECONDS:
                marks.advance(series_id, seen[series_id])
    if not grouped:
        return None
    return LivePoints(
        series=[SeriesPoints(series_id=key, points=value) for key, value in sorted(grouped.items())]
    )


register(NAME, LiveTopic)
