"""Application-database access for metrics, and nothing else."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.metrics import keys
from app.metrics.dashboards import Dashboard
from app.metrics.models import MetricsAgent, MetricsStoreSetting


async def store_setting(session: AsyncSession) -> MetricsStoreSetting | None:
    return await session.get(MetricsStoreSetting, 1)


async def save_store_setting(
    session: AsyncSession,
    *,
    config: dict[str, Any],
    secrets: bytes,
    service_id: uuid.UUID | None,
    configured_by: uuid.UUID | None,
) -> MetricsStoreSetting:
    """Write the one row, replacing whatever was there. Not committed."""
    setting = await store_setting(session)
    if setting is None:
        setting = MetricsStoreSetting(id=1, config=config, secrets=secrets)
    setting.config = config
    setting.secrets = secrets
    setting.service_id = service_id
    setting.configured_by = configured_by
    setting.configured_at = datetime.now(UTC)
    session.add(setting)
    return setting


async def create_agent(
    session: AsyncSession, *, owner_id: uuid.UUID, name: str, key: str
) -> MetricsAgent:
    agent = MetricsAgent(
        owner_id=owner_id,
        name=name,
        key_fingerprint=keys.fingerprint(key),
        key_sealed=keys.seal(key),
    )
    session.add(agent)
    await session.commit()
    await session.refresh(agent)
    return agent


async def agents_of(session: AsyncSession, owner_id: uuid.UUID) -> list[MetricsAgent]:
    statement = (
        select(MetricsAgent)
        .where(MetricsAgent.owner_id == owner_id)
        .order_by(col(MetricsAgent.created_at))
    )
    return list((await session.exec(statement)).all())


async def agent_of(
    session: AsyncSession, agent_id: uuid.UUID, owner_id: uuid.UUID
) -> MetricsAgent | None:
    """One agent of this owner. Somebody else's is not found, not refused."""
    agent = await session.get(MetricsAgent, agent_id)
    if agent is None or agent.owner_id != owner_id:
        return None
    return agent


async def agent_by_key(session: AsyncSession, key: str) -> MetricsAgent | None:
    statement = select(MetricsAgent).where(
        MetricsAgent.key_fingerprint == keys.fingerprint(key)
    )
    return (await session.exec(statement)).first()


async def key_fingerprints(session: AsyncSession) -> dict[str, uuid.UUID]:
    """Every key the collector accepts, as fingerprint to agent."""
    statement = select(MetricsAgent.key_fingerprint, MetricsAgent.id)
    return dict((await session.exec(statement)).all())


async def rotate_key(session: AsyncSession, agent: MetricsAgent, key: str) -> MetricsAgent:
    agent.key_fingerprint = keys.fingerprint(key)
    agent.key_sealed = keys.seal(key)
    agent.key_issued_at = datetime.now(UTC)
    session.add(agent)
    await session.commit()
    await session.refresh(agent)
    return agent


async def dashboards_of(session: AsyncSession, owner_id: uuid.UUID) -> list[Dashboard]:
    statement = (
        select(Dashboard)
        .where(Dashboard.owner_id == owner_id)
        .order_by(col(Dashboard.created_at))
    )
    return list((await session.exec(statement)).all())
