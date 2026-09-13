import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters import registry
from app.adapters.metrics import SupportsMetrics
from app.adapters.registry import UnknownAdapterType
from app.connectors.access import get_or_404
from app.connectors.models import Connector
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
    agents_of,
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
    ConnectorReporting,
    ConnectorSources,
    HistoryAnswer,
    HistoryRequest,
    HostInfo,
    MetricInfo,
    MetricsAgent,
    MetricsCatalog,
    MetricsConnector,
    ProcessInfo,
    ProcessTable,
    ReportingUpdate,
    SeriesHistory,
    SeriesInfo,
    StoreConnect,
    StoreStatus,
)
from app.metrics.presets import AGENT_PRESETS, Preset, ResolvedPreset, resolve
from app.metrics.store import (
    MetricsStore,
    ProcessSort,
    Source,
    StoredSeries,
    StoreUnavailable,
)
from app.realtime.topics import TopicsDep
from app.services.engine import ServiceEngineDep
from app.users.deps import CurrentUser, get_current_active_superuser, get_current_user

router = APIRouter(
    prefix="/metrics", tags=["metrics"], dependencies=[Depends(get_current_user)]
)

MAX_PROCESS_ROWS = 200
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
    """Agents and the hosts they reported, and connections that reported about
    themselves, each with their metrics and series."""
    store = await _store(session, holder)
    agents = await crud.agents_of(session, current_user.id)
    connectors = await access.readable_connectors(session, current_user.id)
    ids = [agent.id for agent in agents]
    try:
        stored = await store.catalog([*ids, *(connector.id for connector in connectors)])
        processes = await store.process_hosts(ids)
    except StoreUnavailable:
        raise _unavailable() from None
    return MetricsCatalog(
        agents=[_sources_of(agent, stored, processes) for agent in agents],
        connectors=[
            reported
            for connector in sorted(connectors, key=lambda one: one.name.lower())
            if (reported := _connector_sources(connector, stored)) is not None
        ],
    )


@router.get("/connectors", response_model=list[ConnectorReporting])
async def read_reporting(
    session: SessionDep, current_user: CurrentUser, holder: StoreHolderDep
) -> Any:
    """Connections this user may see whose type reports metrics, and whether each does."""
    connectors = [
        connector
        for connector in await access.readable_connectors(session, current_user.id)
        if _reports_metrics(connector)
    ]
    settings_by_id = await crud.reporting_of(session, [connector.id for connector in connectors])
    heard: dict[uuid.UUID, datetime] = {}
    try:
        store = await holder.get(session)
        if store is not None:
            heard = await store.last_heard([connector.id for connector in connectors])
    except StoreUnavailable:
        heard = {}
    return [
        _reporting(connector, settings_by_id.get(connector.id), current_user.id, heard)
        for connector in sorted(connectors, key=lambda one: one.name.lower())
    ]


@router.put("/connectors/{connector_id}", response_model=ConnectorReporting)
async def update_reporting(
    session: SessionDep,
    current_user: CurrentUser,
    connector_id: uuid.UUID,
    body: ReportingUpdate,
) -> Any:
    """Switch a connection's reporting on or off. Its owner's decision alone:
    reporting is this server polling their database."""
    connector = await get_or_404(session, connector_id, current_user, requires="own")
    if not _reports_metrics(connector):
        raise HTTPException(
            501, detail={"message": "This kind of source does not report metrics"}
        )
    row = await session.get(MetricsConnector, connector.id) or MetricsConnector(connector_id=connector.id)
    row.enabled = body.enabled
    row.interval_seconds = body.interval_seconds
    row.changed_at = datetime.now(UTC)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _reporting(connector, row, current_user.id, {})


@router.get("/processes", response_model=ProcessTable)
async def read_processes(
    session: SessionDep,
    current_user: CurrentUser,
    holder: StoreHolderDep,
    agent_id: uuid.UUID,
    host: str,
    sort: ProcessSort = "pcpu",
    # A number rather than the widget's closed set: a query string is text,
    # and a Literal of integers does not read one.
    limit: Annotated[int, Query(ge=1, le=MAX_PROCESS_ROWS)] = 20,
) -> Any:
    """The newest process table one host sent in the last hour."""
    try:
        await access.require_agent(session, current_user, agent_id)
    except access.AgentNotReadable:
        raise HTTPException(404, detail={"message": "No such agent"}) from None
    store = await _store(session, holder)
    try:
        ts, rows = await store.latest_processes(agent_id, host, sort, limit)
    except StoreUnavailable:
        raise _unavailable() from None
    return ProcessTable(
        ts=ts,
        rows=[
            ProcessInfo(
                pid=row.pid,
                ppid=row.ppid,
                user=row.user,
                command=row.command,
                pcpu=row.pcpu,
                pmem=row.pmem,
                elapsed=row.elapsed,
            )
            for row in rows
        ],
    )


@router.get("/presets", response_model=list[ResolvedPreset])
async def read_presets(
    session: SessionDep,
    current_user: CurrentUser,
    holder: StoreHolderDep,
    agent_id: uuid.UUID | None = None,
    host: str | None = None,
    connector_id: uuid.UUID | None = None,
) -> Any:
    """The ready-made dashboards for one host of an agent, or for one
    connection, as it can fill them. A connection's type declares its own."""
    if connector_id is not None and agent_id is None and host is None:
        connector = await get_or_404(session, connector_id, current_user, requires="read")
        presets = _presets_of(connector)
        source_id, source_host, processes_known = connector.id, "", False
    elif agent_id is not None and host is not None and connector_id is None:
        try:
            await access.require_agent(session, current_user, agent_id)
        except access.AgentNotReadable:
            raise HTTPException(404, detail={"message": "No such agent"}) from None
        presets = AGENT_PRESETS
        source_id, source_host, processes_known = agent_id, host, True
    else:
        raise HTTPException(
            422, detail={"message": "Name an agent and a host, or a connection"}
        )
    store = await _store(session, holder)
    try:
        stored = await store.catalog([source_id])
        processes = await store.process_hosts([source_id]) if processes_known else {}
    except StoreUnavailable:
        raise _unavailable() from None
    return [
        resolve(
            preset,
            source_id=source_id,
            host=source_host,
            series=stored,
            reports_processes=(source_id, source_host) in processes,
        )
        for preset in presets
    ]


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
    for agent_id in {agent for widget in body.widgets for agent in agents_of(widget)}:
        try:
            await access.require_agent(session, current_user, agent_id)
        except access.AgentNotReadable:
            raise HTTPException(422, detail={"message": "A widget names an agent you cannot read"}) from None
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


def _reports_metrics(connector: Connector) -> bool:
    try:
        return issubclass(registry.get(connector.adapter_type).adapter_class, SupportsMetrics)
    except UnknownAdapterType:
        return False


def _presets_of(connector: Connector) -> tuple[Preset, ...]:
    try:
        driver = registry.get(connector.adapter_type).adapter_class
    except UnknownAdapterType:
        return ()
    return driver.metric_presets() if issubclass(driver, SupportsMetrics) else ()


def _reporting(
    connector: Connector,
    row: MetricsConnector | None,
    user_id: uuid.UUID,
    heard: dict[uuid.UUID, datetime],
) -> ConnectorReporting:
    interval = row.interval_seconds if row is not None else 30
    return ConnectorReporting(
        connector_id=connector.id,
        name=connector.name,
        adapter_type=connector.adapter_type,
        enabled=row.enabled if row is not None else False,
        interval_seconds=interval if interval in (15, 30, 60, 300) else 30,  # type: ignore[arg-type]  # a stored number outside the set reads as the default
        may_change=connector.owner_id == user_id,
        last_heard_at=heard.get(connector.id),
    )


def _connector_sources(connector: Connector, stored: list[StoredSeries]) -> ConnectorSources | None:
    """What one connection reported, or None when it never reported anything."""
    mine: dict[str, list[StoredSeries]] = defaultdict(list)
    for series in stored:
        if series.source.id == connector.id:
            mine[series.metric].append(series)
    if not mine:
        return None
    return ConnectorSources(
        connector_id=connector.id,
        name=connector.name,
        adapter_type=connector.adapter_type,
        last_seen=max(s.last_seen for group in mine.values() for s in group),
        metrics=_metric_infos(mine),
    )


def _metric_infos(metrics: dict[str, list[StoredSeries]]) -> list[MetricInfo]:
    return [
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
                for s in sorted(group, key=lambda s: (_natural(s.field), _natural(s.label)))
            ],
        )
        for metric, group in sorted(metrics.items())
    ]


def _sources_of(
    agent: MetricsAgent,
    stored: list[StoredSeries],
    processes: dict[tuple[uuid.UUID, str], datetime],
) -> AgentSources:
    by_host: dict[str, dict[str, list[StoredSeries]]] = defaultdict(lambda: defaultdict(list))
    for series in stored:
        if series.source.id == agent.id:
            by_host[series.host][series.metric].append(series)
    # A host that sends only its process table is a host all the same.
    for source_id, host in processes:
        if source_id == agent.id:
            by_host.setdefault(host, defaultdict(list))
    hosts = [
        HostInfo(
            host=host,
            last_seen=max(
                [s.last_seen for group in metrics.values() for s in group]
                + ([processes[(agent.id, host)]] if (agent.id, host) in processes else [])
            ),
            processes=(agent.id, host) in processes,
            metrics=_metric_infos(metrics),
        )
        for host, metrics in sorted(by_host.items())
    ]
    return AgentSources(agent_id=agent.id, name=agent.name, hosts=hosts)
