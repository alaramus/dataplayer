"""Create or migrate the tables LangGraph keeps the agent's working state in.

Run at prestart, after Alembic, in a process of its own (D139): see
`app.ai.checkpoints.prepare` for why it cannot run inside the application.
"""

import asyncio
import logging

from app.adapters.postgres.checkpoint_pool import checkpoint_pool
from app.ai.checkpoints import prepare
from app.core.config import settings
from app.core.db import loop_factory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    async with checkpoint_pool(str(settings.DATABASE_URL), max_size=1) as pool:
        await prepare(pool)
    logger.info("Agent checkpoint tables ready")


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=loop_factory)
