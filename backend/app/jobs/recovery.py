"""Settling what a stopped process left running.

At startup and once. A job whose row says `running` while nothing is running
it is a lie a client would wait on for ever, so it ends as `interrupted` —
and nothing is replayed. What a half-finished create left behind is a question
for whoever looks at the service; starting it again by ourselves is how one
container becomes two (D81).
"""

import logging

from app.core.db import async_session_maker
from app.jobs.runner import recover_interrupted

logger = logging.getLogger(__name__)


async def settle_stranded() -> int:
    """End every non-terminal job, and say how many there were."""
    try:
        async with async_session_maker() as session:
            stranded = await recover_interrupted(session)
    except Exception:
        # A failed sweep must not stop the application from serving: the rows
        # are still there and the next start tries again.
        logger.exception("Settling interrupted jobs failed")
        return 0
    if stranded:
        logger.info("Marked %d jobs interrupted", stranded)
    return stranded
