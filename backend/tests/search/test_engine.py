"""Identical cells in flight share one task, and nobody is given less by it (D200)."""

import asyncio
import time

import pytest

from app.search.engine import _Inflight
from app.search.models import SearchMode
from app.search.providers import Found

KEY = ("person", "cell", ("words",), 50)


class _Counted:
    """A cell's work, counting how often it was started."""

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self.started = 0
        self.entered = asyncio.Event()
        self.tasks: list[asyncio.Task[object]] = []

    async def __call__(self) -> Found:
        self.started += 1
        task = asyncio.current_task()
        assert task is not None
        self.tasks.append(task)
        self.entered.set()
        await asyncio.sleep(self.seconds)
        return Found(notice=f"run {self.started}")


async def test_an_identical_cell_joins_the_task_in_flight() -> None:
    inflight = _Inflight()
    work = _Counted(0.1)
    deadline = time.monotonic() + 5

    found = await asyncio.gather(
        inflight.run(KEY, work, mode="search", deadline=deadline),
        inflight.run(KEY, work, mode="search", deadline=deadline - 1),
    )

    assert work.started == 1
    assert [one.notice for one in found] == ["run 1", "run 1"]


@pytest.mark.parametrize(
    ("mode", "later"), [("search", 0.0), ("typing", 1.0)], ids=["another mode", "more time"]
)
async def test_a_cell_is_not_given_the_bounds_of_another_answer(
    mode: SearchMode, later: float
) -> None:
    """The running task's deadline and mode are its starter's: joining it would
    hand a search a keystroke's seconds."""
    inflight = _Inflight()
    work = _Counted(0.1)
    deadline = time.monotonic() + 5

    await asyncio.gather(
        inflight.run(KEY, work, mode="typing", deadline=deadline),
        inflight.run(KEY, work, mode=mode, deadline=deadline + later),
    )

    assert work.started == 2


async def test_an_answer_does_not_join_a_task_being_stopped() -> None:
    """The last waiter's leaving cancels the task, which is not done until its
    cancellation has run; an answer joining it then would end with it."""
    inflight = _Inflight()
    work = _Counted(0.2)
    deadline = time.monotonic() + 5
    older = asyncio.create_task(inflight.run(KEY, work, mode="search", deadline=deadline))
    await asyncio.sleep(0)

    older.cancel()
    newer = asyncio.create_task(inflight.run(KEY, work, mode="search", deadline=deadline))

    with pytest.raises(asyncio.CancelledError):
        await older
    found = await asyncio.wait_for(newer, 5)
    assert found.notice == "run 2"
    assert work.started == 2


async def test_a_task_ended_under_its_waiter_is_a_cell_that_did_not_answer() -> None:
    """Cancelled by nobody waiting for it, it raises no cancellation into an
    answer that is still running."""
    inflight = _Inflight()
    work = _Counted(5)
    waiter = asyncio.create_task(
        inflight.run(KEY, work, mode="search", deadline=time.monotonic() + 5)
    )
    await work.entered.wait()

    work.tasks[0].cancel()

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(waiter, 5)
