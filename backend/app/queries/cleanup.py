"""Expiring query history, on a timer nobody has to coordinate.

D63: expiry does not justify a job framework. The sweep is idempotent and
counts rows, so running it at startup and again every hour in every process is
correct even when several processes do it at once.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.db import async_session_maker
from app.queries import history
from app.queries.execution import recover_interrupted
from app.queries.sessions import QuerySessions

logger = logging.getLogger(__name__)


async def sweep_once() -> int:
    """Expire retained run history (D63)."""
    async with async_session_maker() as session:
        return await history.sweep(session)


async def recover_once() -> int:
    """Settle what a stopped process left behind (D64).

    At startup and once: a run in a non-terminal state has no task and no
    connection any more, so it is marked interrupted. SQL is never replayed.
    """
    async with async_session_maker() as session:
        return await recover_interrupted(session)


async def _sweep_forever() -> None:
    while True:
        try:
            removed = await sweep_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            # A failed sweep is not a reason to stop sweeping: the next round
            # removes what this one could not. Logged as an event with no
            # content — this task never sees a document body.
            logger.exception("Expiring query history failed")
        else:
            if removed:
                logger.info("Removed %d expired query runs", removed)
        await asyncio.sleep(settings.QUERY_HISTORY_SWEEP_SECONDS)


async def _end_idle_transactions(sessions: QuerySessions) -> None:
    """Roll back what has been left open, on a timer of its own.

    More often than history expires: an open transaction holds locks, and
    five minutes is the promise the console shows a countdown against (D66).
    """
    while True:
        try:
            ended = await sessions.sweep()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Ending idle transactions failed")
        else:
            if ended:
                logger.info("Rolled back %d idle transactions", ended)
        await asyncio.sleep(settings.QUERY_TRANSACTION_SWEEP_SECONDS)


@asynccontextmanager
async def sweeping(sessions: QuerySessions) -> AsyncIterator[None]:
    """Run the sweeps for as long as the application does."""
    try:
        stranded = await recover_once()
    except Exception:
        logger.exception("Settling interrupted query runs failed")
    else:
        if stranded:
            logger.info("Marked %d query runs interrupted", stranded)
    tasks = [
        asyncio.create_task(_sweep_forever()),
        asyncio.create_task(_end_idle_transactions(sessions)),
    ]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
