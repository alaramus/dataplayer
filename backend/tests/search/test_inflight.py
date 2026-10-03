"""Identical cells share one task, and nobody joins one that is ending (D200)."""

import asyncio
import time
from collections.abc import Callable

from app.search.engine import _Inflight
from app.search.providers import Found

KEY = ("person", "objects:saved_queries/contents", ("orders",), 50)
# One deadline for every waiter: a later one would get a task of its own.
DEADLINE = time.monotonic() + 600


class _Slow:
    """A start that waits for ever and, cancelled, takes a moment to end — as
    a task does whose worker thread finishes the document it is reading."""

    def __init__(self) -> None:
        self.stops: list[Callable[[], bool]] = []

    async def __call__(self, stopped: Callable[[], bool]) -> Found:
        self.stops.append(stopped)
        if len(self.stops) > 1:
            return Found(notice=f"answer {len(self.stops)}")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await asyncio.sleep(0.05)
            raise
        return Found()


async def _settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


async def test_a_newcomer_never_joins_a_task_its_last_waiter_left() -> None:
    inflight = _Inflight()
    start = _Slow()
    first = asyncio.create_task(inflight.run(KEY, start, mode="search", deadline=DEADLINE))
    await _settle()

    first.cancel()
    await _settle()
    # The first task is still ending: it was cancelled, and is not done.
    found = await asyncio.wait_for(inflight.run(KEY, start, mode="search", deadline=DEADLINE), 1)

    assert found.notice == "answer 2"
    assert start.stops[0]() is True
    assert start.stops[1]() is False
    await asyncio.gather(first, return_exceptions=True)


async def test_a_shared_task_is_told_to_stop_only_when_nobody_waits_for_it() -> None:
    inflight = _Inflight()
    start = _Slow()
    one = asyncio.create_task(inflight.run(KEY, start, mode="search", deadline=DEADLINE))
    other = asyncio.create_task(inflight.run(KEY, start, mode="search", deadline=DEADLINE))
    await _settle()
    assert len(start.stops) == 1

    one.cancel()
    await _settle()
    assert start.stops[0]() is False

    other.cancel()
    await _settle()
    assert start.stops[0]() is True
    await asyncio.gather(one, other, return_exceptions=True)
