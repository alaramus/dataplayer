"""Blocking pieces of a transfer, and what a Stop waits for (D168)."""

import asyncio
import threading
import time

import pytest
from anyio import to_thread

from app.connectors.paste.transfer import in_worker


async def test_a_stop_waits_for_the_piece_in_hand() -> None:
    started = threading.Event()
    finished = threading.Event()

    def piece() -> None:
        started.set()
        time.sleep(0.3)
        finished.set()

    task = asyncio.create_task(in_worker(piece))
    await to_thread.run_sync(started.wait)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Unwaited, the cleanup after a Stop would remove the file this piece
    # was still writing to.
    assert finished.is_set()


async def test_a_piece_answers_and_fails_as_the_work_does() -> None:
    def failing() -> None:
        raise OSError("disk")

    assert await in_worker(lambda: 42) == 42
    with pytest.raises(OSError, match="disk"):
        await in_worker(failing)
