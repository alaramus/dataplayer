"""Who may read which series. The one place that answers it (D129).

Today a series is readable by the owner of the agent that reported it.
Dashboard grants and connection series add answers here, not beside it.
"""

import uuid
from collections.abc import Sequence

from sqlmodel.ext.asyncio.session import AsyncSession

from app.metrics import crud
from app.metrics.store import MetricsStore, StoredSeries
from app.users.models import User


class SeriesNotReadable(Exception):
    """Some series does not exist or is not the caller's. The two look alike."""


async def readable_agents(session: AsyncSession, user: User) -> list[uuid.UUID]:
    return [agent.id for agent in await crud.agents_of(session, user.id)]


async def require_readable(
    session: AsyncSession, store: MetricsStore, user: User, series_ids: Sequence[int]
) -> list[StoredSeries]:
    wanted = set(series_ids)
    found = await store.series(sorted(wanted))
    agents = set(await readable_agents(session, user))
    readable = [
        series
        for series in found
        if series.source.kind == "agent" and series.source.id in agents
    ]
    if len(readable) != len(wanted):
        raise SeriesNotReadable
    return readable
