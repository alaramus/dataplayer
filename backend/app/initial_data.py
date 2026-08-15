import asyncio
import logging

from app.core.db import async_session_maker, loop_factory
from app.users.bootstrap import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def init() -> None:
    async with async_session_maker() as session:
        await init_db(session)


async def main() -> None:
    logger.info("Creating initial data")
    await init()
    logger.info("Initial data created")


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=loop_factory)
