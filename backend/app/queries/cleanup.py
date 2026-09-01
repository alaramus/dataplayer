"""Emptying Trash, on a timer nobody has to coordinate.

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
from app.queries import crud

logger = logging.getLogger(__name__)


async def sweep_once() -> int:
    async with async_session_maker() as session:
        return await crud.sweep_trash(session)


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
            logger.exception("Emptying query Trash failed")
        else:
            if removed:
                logger.info("Removed %d expired query documents", removed)
        await asyncio.sleep(settings.QUERY_TRASH_SWEEP_SECONDS)


@asynccontextmanager
async def sweeping() -> AsyncIterator[None]:
    """Run the sweep for as long as the application does."""
    task = asyncio.create_task(_sweep_forever())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
