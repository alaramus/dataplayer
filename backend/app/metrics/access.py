"""Who may read which series. The one place that answers it (D129).

A series is readable by the owner of the agent that reported it, or by anybody
who may see the connection that reported it (D33). Dashboard grants add answers
here, not beside it.
"""

import uuid
from collections.abc import Sequence

from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors import crud as connector_crud
from app.connectors.models import Connector
from app.metrics import crud
from app.metrics.store import MetricsStore, StoredSeries
from app.users.models import User


class SeriesNotReadable(Exception):
    """Some series does not exist or is not the caller's. The two look alike."""


class AgentNotReadable(Exception):
    """The agent does not exist or is not the caller's. The two look alike."""


async def require_agent(session: AsyncSession, user: User, agent_id: uuid.UUID) -> None:
    """Whether this user may read what an agent reported beyond its series:
    its process tables."""
    if agent_id not in await readable_agents(session, user):
        raise AgentNotReadable


async def readable_agents(session: AsyncSession, user: User) -> list[uuid.UUID]:
    return [agent.id for agent in await crud.agents_of(session, user.id)]


async def readable_connectors(session: AsyncSession, user_id: uuid.UUID) -> list[Connector]:
    """Connections whose series this user may read: any they may see (D33)."""
    return await connector_crud.visible_of(session, user_id=user_id)


async def readable_sources(session: AsyncSession, user_id: uuid.UUID) -> set[uuid.UUID]:
    agents = [agent.id for agent in await crud.agents_of(session, user_id)]
    connectors = [connector.id for connector in await readable_connectors(session, user_id)]
    return {*agents, *connectors}


async def require_readable(
    session: AsyncSession, store: MetricsStore, user: User, series_ids: Sequence[int]
) -> list[StoredSeries]:
    wanted = set(series_ids)
    found = await store.series(sorted(wanted))
    sources = await readable_sources(session, user.id)
    readable = [series for series in found if series.source.id in sources]
    if len(readable) != len(wanted):
        raise SeriesNotReadable
    return readable
