import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import SessionDep
from app.core.schemas import Message
from app.jobs.runner import JobRunnerDep
from app.metrics import access, crud, history, keys, setup
from app.metrics.dashboards import (
    Dashboard,
    DashboardContent,
    DashboardCreate,
    DashboardPublic,
    DashboardSave,
    series_of,
)
from app.metrics.dashboards import public as dashboard_public
from app.metrics.holder import StoreHolder, StoreHolderDep
from app.metrics.models import (
    AgentCreate,
    AgentKey,
    AgentPublic,
    AgentSources,
    AgentUpdate,
    HistoryAnswer,
    HistoryRequest,
    HostInfo,
    MetricInfo,
    MetricsAgent,
    MetricsCatalog,
    SeriesHistory,
    SeriesInfo,
    StoreConnect,
    StoreStatus,
)
from app.metrics.store import MetricsStore, Source, StoredSeries, StoreUnavailable
from app.realtime.topics import TopicsDep
from app.services.engine import ServiceEngineDep
from app.users.deps import CurrentUser, get_current_active_superuser, get_current_user

router = APIRouter(
    prefix="/metrics", tags=["metrics"], dependencies=[Depends(get_current_user)]
)

NOT_SET_UP = "Dashboards are not set up yet"


@router.get("/store", response_model=StoreStatus)
async def read_store_status(
    session: SessionDep,
    current_user: CurrentUser,
    holder: StoreHolderDep,
    engine: ServiceEngineDep,
) -> Any:
    """Whether the store is there, and for a superuser how it could be."""
    return await setup.status(session, holder, current_user, engine)


@router.post(
    "/store/start",
    response_model=StoreStatus,
    dependencies=[Depends(get_current_active_superuser)],
)
async def start_store(
    session: SessionDep,
    current_user: CurrentUser,
    holder: StoreHolderDep,
    runner: JobRunnerDep,
    topics: TopicsDep,
    engine: ServiceEngineDep,
) -> Any:
    """Start TimescaleDB on this server as the metrics store (D126)."""
    try:
        await setup.start(session, runner, topics, engine, current_user)
    except setup.SetupRefused as refusal:
        raise HTTPException(refusal.status_code, detail={"message": refusal.message}) from None
    return await setup.status(session, holder, current_user, engine)


@router.post(
    "/store/connect",
    response_model=StoreStatus,
    dependencies=[Depends(get_current_active_superuser)],
)
async def connect_store(
    session: SessionDep,
    current_user: CurrentUser,
    holder: StoreHolderDep,
    engine: ServiceEngineDep,
    body: StoreConnect,
) -> Any:
    """Use an existing TimescaleDB as the metrics store (D126)."""
    try:
        await setup.connect(session, current_user, body.options)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", "options", *error["loc"]],
                    "msg": error["msg"],
                    "type": error["type"],
                }
                for error in exc.errors()
            ],
        ) from None
    except setup.SetupRefused as refusal:
        raise HTTPException(refusal.status_code, detail={"message": refusal.message}) from None
    return await setup.status(session, holder, current_user, engine)


@router.get("/agents", response_model=list[AgentPublic])
async def read_agents(
    session: SessionDep, current_user: CurrentUser, holder: StoreHolderDep
) -> Any:
    agents = await crud.agents_of(session, current_user.id)
    heard = await _last_heard(session, holder, agents)
    return [_public(agent, heard) for agent in agents]


@router.post("/agents", response_model=AgentKey)
async def create_agent(
    session: SessionDep, current_user: CurrentUser, body: AgentCreate
) -> Any:
    """Register an agent. The answer carries the key it reports under."""
    key = keys.issue()
    agent = await crud.create_agent(
        session, owner_id=current_user.id, name=body.name, key=key
    )
    return _key_answer(agent, key)


@router.patch("/agents/{agent_id}", response_model=AgentPublic)
async def rename_agent(
    session: SessionDep, current_user: CurrentUser, agent_id: uuid.UUID, body: AgentUpdate
) -> Any:
    agent = await _own_agent(session, agent_id, current_user.id)
    agent.name = body.name
    session.add(agent)
    await session.commit()
    await session.refresh(agent)
    return _public(agent, {})


@router.get("/agents/{agent_id}/key", response_model=AgentKey)
async def read_agent_key(
    session: SessionDep, current_user: CurrentUser, agent_id: uuid.UUID
) -> Any:
    """The key again, for its owner to configure another agent with it."""
    agent = await _own_agent(session, agent_id, current_user.id)
    return _key_answer(agent, keys.unseal(agent.key_sealed))


@router.post("/agents/{agent_id}/key", response_model=AgentKey)
async def rotate_agent_key(
    session: SessionDep, current_user: CurrentUser, agent_id: uuid.UUID
) -> Any:
    """Issue a new key. Packets under the old one are dropped from now on."""
    agent = await _own_agent(session, agent_id, current_user.id)
    key = keys.issue()
    agent = await crud.rotate_key(session, agent, key)
    return _key_answer(agent, key)


@router.delete("/agents/{agent_id}", response_model=Message)
async def delete_agent(
    session: SessionDep, current_user: CurrentUser, agent_id: uuid.UUID
) -> Any:
    """Forget the agent. Its samples stay until retention removes them."""
    agent = await _own_agent(session, agent_id, current_user.id)
    await session.delete(agent)
    await session.commit()
    return Message(message=f"{agent.name} was removed")


@router.post("/agents/{agent_id}/purge", response_model=Message)
async def purge_agent(
    session: SessionDep,
    current_user: CurrentUser,
    holder: StoreHolderDep,
    agent_id: uuid.UUID,
) -> Any:
    """Delete every sample the agent sent, and keep the agent."""
    agent = await _own_agent(session, agent_id, current_user.id)
    store = await _store(session, holder)
    try:
        await store.purge(Source(kind="agent", id=agent.id))
    except StoreUnavailable:
        raise _unavailable() from None
    return Message(message=f"The samples of {agent.name} were deleted")


@router.get("/catalog", response_model=MetricsCatalog)
async def read_catalog(
    session: SessionDep, current_user: CurrentUser, holder: StoreHolderDep
) -> Any:
    """Agents, the hosts they reported, their metrics and series."""
    store = await _store(session, holder)
    agents = await crud.agents_of(session, current_user.id)
    try:
        stored = await store.catalog([agent.id for agent in agents])
    except StoreUnavailable:
        raise _unavailable() from None
    return MetricsCatalog(agents=[_sources_of(agent, stored) for agent in agents])


@router.post("/history", response_model=HistoryAnswer)
async def read_history(
    session: SessionDep,
    current_user: CurrentUser,
    holder: StoreHolderDep,
    body: HistoryRequest,
) -> Any:
    """Points of the asked series over a range, raw or bucketed to fit."""
    try:
        history.check_range(body.start, body.end)
    except history.RangeRefused as refusal:
        raise HTTPException(422, detail={"message": str(refusal)}) from None
    store = await _store(session, holder)
    ids = sorted(set(body.series_ids))
    try:
        await access.require_readable(session, store, current_user, ids)
        densest = await store.densest(ids, body.start, body.end)
        width = history.bucket_seconds(body.start, body.end, body.max_points, densest)
        points = (
            await store.raw_points(ids, body.start, body.end)
            if width is None
            else await store.bucketed_points(ids, body.start, body.end, width)
        )
    except access.SeriesNotReadable:
        raise HTTPException(404, detail={"message": "No such series"}) from None
    except StoreUnavailable:
        raise _unavailable() from None
    return HistoryAnswer(
        start=body.start,
        end=body.end,
        bucket_seconds=width,
        series=[SeriesHistory(series_id=i, points=points.get(i, [])) for i in ids],
    )


@router.get("/dashboards", response_model=list[DashboardPublic])
async def read_dashboards(session: SessionDep, current_user: CurrentUser) -> Any:
    return [dashboard_public(one) for one in await crud.dashboards_of(session, current_user.id)]


@router.post("/dashboards", response_model=DashboardPublic)
async def create_dashboard(
    session: SessionDep, current_user: CurrentUser, body: DashboardCreate
) -> Any:
    dashboard = Dashboard(
        owner_id=current_user.id,
        name=body.name,
        content=DashboardContent().model_dump(mode="json"),
    )
    session.add(dashboard)
    await session.commit()
    await session.refresh(dashboard)
    return dashboard_public(dashboard)


@router.get("/dashboards/{dashboard_id}", response_model=DashboardPublic)
async def read_dashboard(
    session: SessionDep, current_user: CurrentUser, dashboard_id: uuid.UUID
) -> Any:
    return dashboard_public(await _own_dashboard(session, dashboard_id, current_user.id))


@router.put("/dashboards/{dashboard_id}", response_model=DashboardPublic)
async def save_dashboard(
    session: SessionDep,
    current_user: CurrentUser,
    holder: StoreHolderDep,
    dashboard_id: uuid.UUID,
    body: DashboardSave,
) -> Any:
    """Replace the name, options and widgets, if nobody saved in between.

    A widget naming a series the saver cannot read is refused: a stored
    dashboard must not become a way of reading somebody else's data (D129).
    """
    dashboard = await _own_dashboard(session, dashboard_id, current_user.id)
    if body.version != dashboard.version:
        raise HTTPException(
            409,
            detail={"message": "This dashboard was changed somewhere else; reload it"},
        )
    wanted = sorted({series for widget in body.widgets for series in series_of(widget)})
    if wanted:
        store = await _store(session, holder)
        try:
            await access.require_readable(session, store, current_user, wanted)
        except access.SeriesNotReadable:
            raise HTTPException(422, detail={"message": "A widget names a series you cannot read"}) from None
        except StoreUnavailable:
            raise _unavailable() from None
    content = DashboardContent(options=body.options, widgets=body.widgets)
    dashboard.name = body.name
    dashboard.content = content.model_dump(mode="json")
    dashboard.version += 1
    dashboard.updated_at = datetime.now(UTC)
    session.add(dashboard)
    await session.commit()
    await session.refresh(dashboard)
    return dashboard_public(dashboard)


@router.delete("/dashboards/{dashboard_id}", response_model=Message)
async def delete_dashboard(
    session: SessionDep, current_user: CurrentUser, dashboard_id: uuid.UUID
) -> Any:
    dashboard = await _own_dashboard(session, dashboard_id, current_user.id)
    await session.delete(dashboard)
    await session.commit()
    return Message(message=f"{dashboard.name} was removed")


async def _own_dashboard(
    session: AsyncSession, dashboard_id: uuid.UUID, owner_id: uuid.UUID
) -> Dashboard:
    dashboard = await session.get(Dashboard, dashboard_id)
    if dashboard is None or dashboard.owner_id != owner_id:
        raise HTTPException(404, detail={"message": "No such dashboard"})
    return dashboard


async def _store(session: AsyncSession, holder: StoreHolder) -> MetricsStore:
    try:
        store = await holder.get(session)
    except StoreUnavailable:
        raise _unavailable() from None
    if store is None:
        raise HTTPException(409, detail={"message": NOT_SET_UP})
    return store


def _unavailable() -> HTTPException:
    return HTTPException(503, detail={"message": setup.NOT_ANSWERING})


async def _own_agent(
    session: AsyncSession, agent_id: uuid.UUID, owner_id: uuid.UUID
) -> MetricsAgent:
    agent = await crud.agent_of(session, agent_id, owner_id)
    if agent is None:
        raise HTTPException(404, detail={"message": "No such agent"})
    return agent


async def _last_heard(
    session: AsyncSession, holder: StoreHolder, agents: list[MetricsAgent]
) -> dict[uuid.UUID, Any]:
    """When each agent was last heard from. Nothing, when the store cannot say."""
    if not agents:
        return {}
    try:
        store = await holder.get(session)
        if store is None:
            return {}
        return await store.last_heard([agent.id for agent in agents])
    except StoreUnavailable:
        return {}


def _public(agent: MetricsAgent, heard: dict[uuid.UUID, Any]) -> AgentPublic:
    return AgentPublic(
        id=agent.id,
        name=agent.name,
        created_at=agent.created_at,
        key_issued_at=agent.key_issued_at,
        last_heard_at=heard.get(agent.id),
    )


def _key_answer(agent: MetricsAgent, key: str) -> AgentKey:
    return AgentKey(agent=_public(agent, {}), key=key, udp_port=settings.METRICS_UDP_PORT)


def _natural(text: str) -> tuple[tuple[int, int | str], ...]:
    """`cpu2` before `cpu10`."""
    parts: list[tuple[int, int | str]] = []
    number = ""
    word = ""
    for character in text:
        if character.isdigit():
            if word:
                parts.append((1, word))
                word = ""
            number += character
        else:
            if number:
                parts.append((0, int(number)))
                number = ""
            word += character
    if number:
        parts.append((0, int(number)))
    if word:
        parts.append((1, word))
    return tuple(parts)


def _sources_of(agent: MetricsAgent, stored: list[StoredSeries]) -> AgentSources:
    by_host: dict[str, dict[str, list[StoredSeries]]] = defaultdict(lambda: defaultdict(list))
    for series in stored:
        if series.source.id == agent.id:
            by_host[series.host][series.metric].append(series)
    hosts = [
        HostInfo(
            host=host,
            last_seen=max(s.last_seen for group in metrics.values() for s in group),
            metrics=[
                MetricInfo(
                    metric=metric,
                    series=[
                        SeriesInfo(
                            id=s.id,
                            field=s.field,
                            label=s.label,
                            unit=s.unit,
                            first_seen=s.first_seen,
                            last_seen=s.last_seen,
                        )
                        for s in sorted(
                            group, key=lambda s: (_natural(s.field), _natural(s.label))
                        )
                    ],
                )
                for metric, group in sorted(metrics.items())
            ],
        )
        for host, metrics in sorted(by_host.items())
    ]
    return AgentSources(agent_id=agent.id, name=agent.name, hosts=hosts)
