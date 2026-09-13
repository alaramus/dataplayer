"""Who may read which series and which dashboards. The one place that answers it (D129).

A series is readable directly by the owner of the agent that reported it, or by
anybody who may see the connection that reported it (D33). Through a dashboard
the caller has standing on, a series on it is readable too — as long as
somebody who may put series on that dashboard, its owner or an editor, can
still read it directly. A grant taken from them is taken from everybody reading
through them.
"""

import uuid
from collections.abc import Sequence

from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors import crud as connector_crud
from app.connectors.models import Connector
from app.core.access import Access, at_least
from app.metrics import crud
from app.metrics.dashboards import (
    Dashboard,
    DashboardContent,
    hosts_of,
    series_of,
)
from app.metrics.store import MetricsStore, StoredSeries
from app.users.models import User


class SeriesNotReadable(Exception):
    """Some series does not exist or is not the caller's. The two look alike."""


class AgentNotReadable(Exception):
    """The agent does not exist or is not the caller's. The two look alike."""


class DashboardNotFound(Exception):
    """No such dashboard, or no standing on it. The two look alike (D33)."""


class DashboardRefused(Exception):
    """Standing on the dashboard, below what was asked."""

    def __init__(self, required: Access, held: Access) -> None:
        super().__init__(f"This needs {required} access to the dashboard")
        self.required = required
        self.held = held


async def resolve_dashboard(
    session: AsyncSession, user: User, dashboard_id: uuid.UUID, *, requires: Access
) -> tuple[Dashboard, Access]:
    """The dashboard and the caller's standing. `requires` has no default, as
    the connection funnel's has none."""
    dashboard = await session.get(Dashboard, dashboard_id)
    if dashboard is None:
        raise DashboardNotFound
    held = await crud.dashboard_standing(session, dashboard, user.id)
    if held is None:
        raise DashboardNotFound
    if not at_least(held, requires):
        raise DashboardRefused(requires, held)
    return dashboard, held


def content_of(dashboard: Dashboard) -> DashboardContent:
    """What is on a dashboard; nothing, when the stored row cannot be read."""
    try:
        return DashboardContent.model_validate(dashboard.content)
    except ValueError:
        return DashboardContent()


def series_on(dashboard: Dashboard) -> set[int]:
    return {series for widget in content_of(dashboard).widgets for series in series_of(widget)}


def hosts_on(dashboard: Dashboard) -> set[tuple[uuid.UUID, str]]:
    return {host for widget in content_of(dashboard).widgets for host in hosts_of(widget)}


async def require_agent(
    session: AsyncSession, user: User, agent_id: uuid.UUID, host: str | None = None,
    *, through: Dashboard | None = None,
) -> None:
    """Whether this user may read what an agent reported beyond its series —
    its process tables — directly, or through a dashboard naming that host."""
    if agent_id in await readable_agents(session, user):
        return
    if through is not None and host is not None and (agent_id, host) in hosts_on(through):
        for writer in await crud.writers_of(session, through):
            if agent_id in [agent.id for agent in await crud.agents_of(session, writer)]:
                return
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


async def sources_through(session: AsyncSession, dashboard: Dashboard) -> set[uuid.UUID]:
    """Sources a series on this dashboard may come from and still be read
    through it: those its owner or one of its editors reads directly."""
    sources: set[uuid.UUID] = set()
    for writer in await crud.writers_of(session, dashboard):
        sources |= await readable_sources(session, writer)
    return sources


async def require_readable(
    session: AsyncSession,
    store: MetricsStore,
    user: User,
    series_ids: Sequence[int],
    *,
    through: Dashboard | None = None,
) -> list[StoredSeries]:
    """The series, when every one is readable directly or through `through`,
    which the caller has already been found to have standing on."""
    wanted = set(series_ids)
    found = await store.series(sorted(wanted))
    sources = await readable_sources(session, user.id)
    readable = [series for series in found if series.source.id in sources]
    if len(readable) != len(wanted) and through is not None:
        on_it = series_on(through)
        via = await sources_through(session, through)
        readable = [
            series
            for series in found
            if series.source.id in sources or (series.id in on_it and series.source.id in via)
        ]
    if len(readable) != len(wanted):
        raise SeriesNotReadable
    return readable


async def live_series(
    session: AsyncSession, store: MetricsStore, user_id: uuid.UUID, direct: set[uuid.UUID]
) -> set[int]:
    """Series this user reads only through dashboards: what the live topic adds
    to the sources it already watches."""
    extra: set[int] = set()
    for dashboard, _, _ in await crud.visible_dashboards(session, user_id):
        on_it = series_on(dashboard)
        if not on_it:
            continue
        via = await sources_through(session, dashboard)
        extra |= {
            series.id
            for series in await store.series(sorted(on_it))
            if series.source.id not in direct and series.source.id in via
        }
    return extra
