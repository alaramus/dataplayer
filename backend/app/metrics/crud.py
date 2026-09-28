"""Application-database access for metrics, and nothing else."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors.models import Connector
from app.core.access import Access
from app.metrics import keys
from app.metrics.dashboards import (
    AnyWidget,
    Dashboard,
    DashboardContent,
    DashboardGrant,
    DashboardGrantLevel,
    ProcessesWidget,
)
from app.metrics.models import MetricsAgent, MetricsConnector, MetricsStoreSetting
from app.users.models import User


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


async def agent_keys(session: AsyncSession) -> list[tuple[uuid.UUID, str, bytes]]:
    """Every key the collector accepts: agent, fingerprint, and the key sealed."""
    statement = select(MetricsAgent.id, MetricsAgent.key_fingerprint, MetricsAgent.key_sealed)
    return [(agent_id, fingerprint, sealed) for agent_id, fingerprint, sealed in (await session.exec(statement)).all()]


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


async def empty_dashboard_of(session: AsyncSession, owner_id: uuid.UUID) -> Dashboard | None:
    """The owner's first dashboard with no widget on it. Read from the stored
    content, so one that no longer validates but holds widgets is not empty."""
    return next(
        (dashboard for dashboard in await dashboards_of(session, owner_id) if not dashboard.content.get("widgets")),
        None,
    )


async def visible_dashboards(
    session: AsyncSession, user_id: uuid.UUID
) -> list[tuple[Dashboard, Access, User | None]]:
    """The user's own dashboards, then those shared with them, each with the
    caller's standing and, for a shared one, its owner."""
    own: list[tuple[Dashboard, Access, User | None]] = [
        (dashboard, "own", None) for dashboard in await dashboards_of(session, user_id)
    ]
    statement = (
        select(Dashboard, DashboardGrant, User)
        .join(DashboardGrant, col(DashboardGrant.dashboard_id) == col(Dashboard.id))
        .join(User, col(User.id) == col(Dashboard.owner_id))
        .where(DashboardGrant.user_id == user_id)
        .order_by(col(Dashboard.name))
    )
    shared: list[tuple[Dashboard, Access, User | None]] = [
        (dashboard, grant.access, owner)
        for dashboard, grant, owner in (await session.exec(statement)).all()
    ]
    return own + shared


async def dashboard_standing(
    session: AsyncSession, dashboard: Dashboard, user_id: uuid.UUID
) -> Access | None:
    if dashboard.owner_id == user_id:
        return "own"
    grant = await session.get(DashboardGrant, (dashboard.id, user_id))
    return grant.access if grant is not None else None


async def dashboard_grants(
    session: AsyncSession, dashboard_id: uuid.UUID
) -> list[tuple[DashboardGrant, User]]:
    statement = (
        select(DashboardGrant, User)
        .join(User, col(User.id) == col(DashboardGrant.user_id))
        .where(DashboardGrant.dashboard_id == dashboard_id)
        .order_by(col(User.email))
    )
    return [(grant, user) for grant, user in (await session.exec(statement)).all()]


async def set_dashboard_grant(
    session: AsyncSession, dashboard_id: uuid.UUID, user_id: uuid.UUID, access: DashboardGrantLevel
) -> DashboardGrant:
    grant = await session.get(DashboardGrant, (dashboard_id, user_id))
    if grant is None:
        grant = DashboardGrant(dashboard_id=dashboard_id, user_id=user_id, access=access)
    grant.access = access
    session.add(grant)
    await session.commit()
    await session.refresh(grant)
    return grant


async def remove_dashboard_grant(
    session: AsyncSession, dashboard_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    grant = await session.get(DashboardGrant, (dashboard_id, user_id))
    if grant is None:
        return False
    await session.delete(grant)
    await session.commit()
    return True


async def writers_of(session: AsyncSession, dashboard: Dashboard) -> list[uuid.UUID]:
    """Everybody who may put a series on a dashboard: its owner and its editors."""
    statement = select(DashboardGrant.user_id).where(
        DashboardGrant.dashboard_id == dashboard.id, DashboardGrant.access == "write"
    )
    return [dashboard.owner_id, *(await session.exec(statement)).all()]


async def forget_series(session: AsyncSession) -> None:
    """Take every widget naming a series off every dashboard. Not committed.

    What a widget names is an id in one store; a process table names an agent
    and a host, and stays. A dashboard that cannot be read is left as it is.
    """
    for dashboard in (await session.exec(select(Dashboard))).all():
        try:
            content = DashboardContent.model_validate(dashboard.content)
        except ValueError:
            continue
        kept: list[AnyWidget] = [
            widget for widget in content.widgets if isinstance(widget, ProcessesWidget)
        ]
        if len(kept) == len(content.widgets):
            continue
        dashboard.content = DashboardContent(options=content.options, widgets=kept).model_dump(mode="json")
        dashboard.version += 1
        dashboard.updated_at = datetime.now(UTC)
        session.add(dashboard)


async def reporting_of(
    session: AsyncSession, connector_ids: list[uuid.UUID]
) -> dict[uuid.UUID, MetricsConnector]:
    if not connector_ids:
        return {}
    statement = select(MetricsConnector).where(col(MetricsConnector.connector_id).in_(connector_ids))
    return {row.connector_id: row for row in (await session.exec(statement)).all()}


async def reporting_connectors(session: AsyncSession) -> list[tuple[Connector, MetricsConnector]]:
    """Every switched-on connection whose owner switched reporting on."""
    statement = (
        select(Connector, MetricsConnector)
        .join(MetricsConnector, col(MetricsConnector.connector_id) == col(Connector.id))
        .where(col(MetricsConnector.enabled).is_(True), col(Connector.enabled).is_(True))
    )
    return [(connector, row) for connector, row in (await session.exec(statement)).all()]
