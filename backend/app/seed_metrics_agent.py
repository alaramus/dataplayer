"""Register the development agent for the first superuser.

A development tool, not part of the API. The agent in the `monitor-agent`
Compose profile reports under METRICS_DEV_AGENT_KEY; this makes that key one an
agent holds, so its datagrams are accepted without a screen to issue a key (D128).
Does nothing when the key is not set or already registered.

    python -m app.seed_metrics_agent
"""

import asyncio
import logging

from app.core.config import settings
from app.core.db import async_session_maker, loop_factory
from app.metrics import crud as metrics_crud
from app.users import crud as user_crud

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

AGENT_NAME = "Development agent"


async def seed() -> None:
    secret = settings.METRICS_DEV_AGENT_KEY
    key = secret.get_secret_value().strip() if secret is not None else ""
    if not key:
        logger.info("METRICS_DEV_AGENT_KEY is not set; no development agent")
        return
    async with async_session_maker() as session:
        if await metrics_crud.agent_by_key(session, key) is not None:
            logger.info("The development agent is already registered")
            return
        owner = await user_crud.get_user_by_email(
            session=session, email=str(settings.FIRST_SUPERUSER)
        )
        if owner is None:
            logger.info("No first superuser; no development agent")
            return
        await metrics_crud.create_agent(session, owner_id=owner.id, name=AGENT_NAME, key=key)
        logger.info("Registered %s for %s", AGENT_NAME, owner.email)


if __name__ == "__main__":
    asyncio.run(seed(), loop_factory=loop_factory)
