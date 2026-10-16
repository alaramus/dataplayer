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
from app.core.access import Access
from app.core.config import settings
from app.core.db import SessionDep
from app.core.problems import Problem, ProblemCode
from app.core.schemas import Message
from app.jobs.runner import JobRunnerDep
from app.metrics import access, crud, history, keys, restarts, setup
from app.metrics.dashboards import (
    Dashboard,
    DashboardContent,
    DashboardCreate,
    DashboardGrantPublic,
    DashboardGrantWrite,
    DashboardPublic,
    DashboardSave,
    hosts_of,
    owner_named,
    series_of,
)
from app.metrics.dashboards import public as dashboard_public
from app.metrics.holder import StoreHolder, StoreHolderDep
from app.metrics.models import (
    AgentCreate,
    AgentHost,
    AgentKey,
    AgentPublic,
    AgentSources,
    AgentUpdate,
    ConnectorReporting,
    ConnectorSources,
    HistoryAnswer,
    HistoryRequest,
    HostInfo,
    HostRestarts,
    MetricInfo,
    MetricsAgent,
    MetricsCatalog,
    MetricsConnector,
    ProcessInfo,
    ProcessTable,
    ReportingUpdate,
    RestartsAnswer,
    SeriesHistory,
    SeriesInfo,
    StoreConnect,
    StoreStatus,
    StoreUsage,
)
from app.metrics.presets import AGENT_PRESETS, Preset, ResolvedPreset, resolve
from app.metrics.store import (
    HostRow,
    MetricsStore,
    ProcessSort,
    Source,
    StoredSeries,
    StoreUnavailable,
)
from app.realtime.topics import TopicsDep
from app.services.engine import ServiceEngineDep
from app.users.deps import CurrentUser, get_current_active_superuser, get_current_user
from app.users.models import User

router = APIRouter(
    prefix="/metrics", tags=["metrics"], dependencies=[Depends(get_current_user)]
)

MAX_PROCESS_ROWS = 200

# One code per level rather than the level as a parameter (D225).
DASHBOARD_NEEDS: dict[Access, ProblemCode] = {
    "read": "metrics.dashboard_needs_read",
    "write": "metrics.dashboard_needs_write",
    "structure": "metrics.dashboard_needs_structure",
    "own": "metrics.dashboard_needs_own",
}


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


@router.get(
    "/store/usage",
    response_model=StoreUsage,
    dependencies=[Depends(get_current_active_superuser)],
)
async def read_store_usage(session: SessionDep, holder: StoreHolderDep) -> Any:
    """Where the store is, what it takes, and how long it keeps what."""
    try:
        return await setup.usage(session, holder)
    except setup.SetupRefused as refusal:
        raise HTTPException(refusal.status_code, detail={"message": refusal.message}) from None


@router.delete(
    "/store",
    response_model=Message,
    dependencies=[Depends(get_current_active_superuser)],
)
async def remove_store(
    session: SessionDep,
    current_user: CurrentUser,
    holder: StoreHolderDep,
    runner: JobRunnerDep,
    topics: TopicsDep,
) -> Any:
    """Stop using the metrics store and take every person's samples with it (D126)."""
    try:
        message = await setup.remove(session, holder, runner, topics, current_user)
    except setup.SetupRefused as refusal:
        raise HTTPException(refusal.status_code, detail={"message": refusal.message}) from None
    return Message(message=message)


@router.get("/restarts", response_model=RestartsAnswer)
async def read_restarts(
    session: SessionDep, current_user: CurrentUser, holder: StoreHolderDep
) -> Any:
    """Hosts of the caller's agents that restarted again and again lately.

    Nothing rather than a refusal when there is no store to ask: this feeds a
    list of what needs a person, and a store not set up is not such a thing.
    """
    answer = RestartsAnswer(window_seconds=restarts.WINDOW_SECONDS, hosts=[])
    agents = {agent.id: agent for agent in await crud.agents_of(session, current_user.id)}
    if not agents:
        return answer
    now = int(datetime.now(UTC).timestamp())
    try:
        store = await holder.get(session)
        if store is None:
            return answer
        found = await store.restarts_since(list(agents), now - restarts.WINDOW_SECONDS)
    except StoreUnavailable:
        return answer
    answer.hosts = [
        HostRestarts(
            agent_id=one.source_id,
            agent_name=agents[one.source_id].name,
            host=one.host,
            count=one.count,
            first_at=datetime.fromtimestamp(one.first, UTC),
            last_at=datetime.fromtimestamp(one.last, UTC),
            cause=one.cause,
        )
        for one in restarts.repeated(found, now)
    ]
    return answer


@router.get("/hosts", response_model=list[AgentHost])
async def read_hosts(
    session: SessionDep, current_user: CurrentUser, holder: StoreHolderDep
) -> Any:
    """The hosts the caller's agents report, with what each host is."""
    agents = {agent.id: agent for agent in await crud.agents_of(session, current_user.id)}
    if not agents:
        return []
    store = await _store(session, holder)
    try:
        found = await store.hosts(list(agents))
    except StoreUnavailable:
        raise _unavailable() from None
    return [
        _host(row, agents[row.run.source_id].name)
        for row in sorted(found, key=lambda one: (agents[one.run.source_id].name.lower(), one.run.host))
    ]


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
    """Issue a new key. Datagrams signed with the old one are dropped from now on."""
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
        raise Problem(501, "metrics.no_metrics", error_kind="config")
    row = await session.get(MetricsConnector, connector.id) or MetricsConnector(connector_id=connector.id)
    row.enabled = body.enabled
    row.interval_seconds = body.interval_seconds
    row.changed_at = datetime.now(UTC)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _reporting(connector, row, current_user.id, {})


@router.post("/connectors/{connector_id}/purge", response_model=Message)
async def purge_connector(
    session: SessionDep,
    current_user: CurrentUser,
    holder: StoreHolderDep,
    connector_id: uuid.UUID,
) -> Any:
    """Delete every sample the server collected from this connection. Its
    owner's decision alone, like switching reporting: the polling is this
    server reading their database."""
    connector = await get_or_404(session, connector_id, current_user, requires="own")
    if not _reports_metrics(connector):
        raise Problem(501, "metrics.no_metrics", error_kind="config")
    store = await _store(session, holder)
    try:
        await store.purge(Source(kind="connector", id=connector.id))
    except StoreUnavailable:
        raise _unavailable() from None
    return Message(message=f"The samples of {connector.name} were deleted")


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
    dashboard_id: uuid.UUID | None = None,
) -> Any:
    """The newest process table one host sent in the last hour, of an agent
    of the caller's or of a host on a dashboard they may read."""
    through = (
        None if dashboard_id is None
        else (await _dashboard(session, current_user, dashboard_id, requires="read"))[0]
    )
    try:
        await access.require_agent(session, current_user, agent_id, host, through=through)
    except access.AgentNotReadable:
        raise Problem(404, "metrics.agent_not_found") from None
    store = await _store(session, holder)
    try:
        latest = await store.latest_processes(agent_id, host, sort, limit)
    except StoreUnavailable:
        raise _unavailable() from None
    if latest is None:
        return ProcessTable(ts=None, rows=[])
    return ProcessTable(
        ts=latest.ts,
        total=latest.total,
        rows=[
            ProcessInfo(
                pid=row.pid,
                ppid=row.ppid,
                user=row.user,
                state=row.state,
                pcpu=row.pcpu,
                pmem=row.pmem,
                rss_bytes=row.rss,
                started_at=datetime.fromtimestamp(row.started, UTC),
                name=row.name,
                command=row.command,
            )
            for row in latest.rows
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
            raise Problem(404, "metrics.agent_not_found") from None
        presets = AGENT_PRESETS
        source_id, source_host, processes_known = agent_id, host, True
    else:
        raise Problem(422, "metrics.agent_or_connection_required")
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
    """Points of the asked series over a range, raw or bucketed to fit. Series
    on a dashboard the caller may read are asked through it."""
    try:
        history.check_range(body.start, body.end)
    except history.RangeRefused as refusal:
        raise HTTPException(422, detail={"message": str(refusal)}) from None
    through = (
        None if body.dashboard_id is None
        else (await _dashboard(session, current_user, body.dashboard_id, requires="read"))[0]
    )
    store = await _store(session, holder)
    ids = sorted(set(body.series_ids))
    try:
        await access.require_readable(session, store, current_user, ids, through=through)
        now = int(datetime.now(UTC).timestamp())
        densest = (
            await store.densest(ids, body.start, body.end, cap=body.max_points + 1)
            if history.raw_reaches(body.start, now)
            else None
        )
        density = history.density(body.start, body.end, body.max_points, densest, now)
        width = density.bucket_seconds
        points = (
            await store.raw_points(ids, body.start, body.end)
            if width is None
            else await store.bucketed_points(ids, body.start, body.end, width, density.tier)
        )
    except access.SeriesNotReadable:
        raise Problem(404, "metrics.series_not_found") from None
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
    """The caller's own dashboards, then those shared with them."""
    return [
        dashboard_public(dashboard, held, None if owner is None else owner_named(owner))
        for dashboard, held, owner in await crud.visible_dashboards(session, current_user.id)
    ]


@router.post("/dashboards", response_model=DashboardPublic)
async def create_dashboard(
    session: SessionDep, current_user: CurrentUser, body: DashboardCreate
) -> Any:
    """A new dashboard, unless the caller already owns an empty one: that one
    is given back instead, so pressing New again does not stack up empties."""
    waiting = await crud.empty_dashboard_of(session, current_user.id)
    if waiting is not None:
        return dashboard_public(waiting)
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
    """One dashboard. Its address is its link: somebody without standing on it
    is told it does not exist (D33)."""
    dashboard, held = await _dashboard(session, current_user, dashboard_id, requires="read")
    return await _public_dashboard(session, dashboard, held)


@router.get("/dashboards/{dashboard_id}/catalog", response_model=MetricsCatalog)
async def read_dashboard_catalog(
    session: SessionDep,
    current_user: CurrentUser,
    holder: StoreHolderDep,
    dashboard_id: uuid.UUID,
) -> Any:
    """What the series and process tables on one dashboard are, as far as the
    caller may read them through it: the names its widgets are drawn with."""
    dashboard, _ = await _dashboard(session, current_user, dashboard_id, requires="read")
    wanted = sorted(access.series_on(dashboard))
    hosts = access.hosts_on(dashboard)
    store = await _store(session, holder)
    try:
        found = await store.series(wanted)
        processes = await store.process_hosts(sorted({agent for agent, _ in hosts}))
    except StoreUnavailable:
        raise _unavailable() from None
    direct = await access.readable_sources(session, current_user.id)
    via = await access.sources_through(session, dashboard)
    readable = [series for series in found if series.source.id in direct or series.source.id in via]
    agent_ids = {series.source.id for series in readable if series.source.kind == "agent"}
    agent_ids |= {agent for agent, _ in hosts if agent in direct or agent in via}
    agents = [agent for agent_id in sorted(agent_ids) if (agent := await session.get(MetricsAgent, agent_id))]
    connectors = [
        connector
        for connector_id in sorted({s.source.id for s in readable if s.source.kind == "connector"})
        if (connector := await session.get(Connector, connector_id)) is not None
    ]
    shown_processes = {key: seen for key, seen in processes.items() if key in hosts}
    return MetricsCatalog(
        agents=[_sources_of(agent, readable, shown_processes) for agent in agents],
        connectors=[
            reported
            for connector in connectors
            if (reported := _connector_sources(connector, readable)) is not None
        ],
    )


@router.put("/dashboards/{dashboard_id}", response_model=DashboardPublic)
async def save_dashboard(
    session: SessionDep,
    current_user: CurrentUser,
    holder: StoreHolderDep,
    dashboard_id: uuid.UUID,
    body: DashboardSave,
) -> Any:
    """Replace the name, options and widgets, if nobody saved in between.

    What was already on the dashboard stays. What is added must be readable by
    whoever adds it, directly: a stored dashboard must not become a way of
    reading somebody else's data, and an editor is not given the owner's
    agents by being given the dashboard (D129).
    """
    dashboard, held = await _dashboard(session, current_user, dashboard_id, requires="write")
    if body.version != dashboard.version:
        raise Problem(409, "metrics.dashboard_changed")
    known_hosts = access.hosts_on(dashboard)
    for agent_id, host in {h for widget in body.widgets for h in hosts_of(widget)} - known_hosts:
        try:
            await access.require_agent(session, current_user, agent_id, host)
        except access.AgentNotReadable:
            raise Problem(422, "metrics.widget_agent_unreadable") from None
    added = sorted({s for widget in body.widgets for s in series_of(widget)} - access.series_on(dashboard))
    if added:
        store = await _store(session, holder)
        try:
            await access.require_readable(session, store, current_user, added)
        except access.SeriesNotReadable:
            raise Problem(422, "metrics.widget_series_unreadable") from None
        except StoreUnavailable:
            raise _unavailable() from None
    content = DashboardContent(options=body.options, widgets=body.widgets)
    dashboard.name = body.name
    dashboard.color = body.color
    dashboard.content = content.model_dump(mode="json")
    dashboard.version += 1
    dashboard.updated_at = datetime.now(UTC)
    session.add(dashboard)
    await session.commit()
    await session.refresh(dashboard)
    return await _public_dashboard(session, dashboard, held)


@router.delete("/dashboards/{dashboard_id}", response_model=Message)
async def delete_dashboard(
    session: SessionDep, current_user: CurrentUser, dashboard_id: uuid.UUID
) -> Any:
    dashboard, _ = await _dashboard(session, current_user, dashboard_id, requires="own")
    await session.delete(dashboard)
    await session.commit()
    return Message(message=f"{dashboard.name} was removed")


@router.get("/dashboards/{dashboard_id}/grants", response_model=list[DashboardGrantPublic])
async def read_dashboard_grants(
    session: SessionDep, current_user: CurrentUser, dashboard_id: uuid.UUID
) -> Any:
    """Who else may see this dashboard, and whether they may change it. The
    owner's business alone, as a connection's grants are."""
    await _dashboard(session, current_user, dashboard_id, requires="own")
    return [
        DashboardGrantPublic(user_id=user.id, email=user.email, full_name=user.full_name, access=grant.access)
        for grant, user in await crud.dashboard_grants(session, dashboard_id)
    ]


@router.put("/dashboards/{dashboard_id}/grants", response_model=DashboardGrantPublic)
async def write_dashboard_grant(
    session: SessionDep,
    current_user: CurrentUser,
    dashboard_id: uuid.UUID,
    body: DashboardGrantWrite,
) -> Any:
    """Give somebody a level on this dashboard, or change the one they have."""
    await _dashboard(session, current_user, dashboard_id, requires="own")
    if body.user_id == current_user.id:
        raise HTTPException(
            422,
            detail=[{"loc": ["body", "user_id"], "msg": "You already own this dashboard", "type": "value_error"}],
        )
    user = await session.get(User, body.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            422, detail=[{"loc": ["body", "user_id"], "msg": "No such user", "type": "value_error"}]
        )
    grant = await crud.set_dashboard_grant(session, dashboard_id, user.id, body.access)
    return DashboardGrantPublic(user_id=user.id, email=user.email, full_name=user.full_name, access=grant.access)


@router.delete("/dashboards/{dashboard_id}/grants/{user_id}", response_model=Message)
async def revoke_dashboard_grant(
    session: SessionDep, current_user: CurrentUser, dashboard_id: uuid.UUID, user_id: uuid.UUID
) -> Any:
    """Take a level away. What the person already has on screen goes at their
    next read."""
    await _dashboard(session, current_user, dashboard_id, requires="own")
    if not await crud.remove_dashboard_grant(session, dashboard_id, user_id):
        raise Problem(404, "metrics.grant_not_found")
    return Message(message="Access revoked")


async def _dashboard(
    session: AsyncSession, user: User, dashboard_id: uuid.UUID, *, requires: Access
) -> tuple[Dashboard, Access]:
    try:
        return await access.resolve_dashboard(session, user, dashboard_id, requires=requires)
    except access.DashboardNotFound:
        raise Problem(404, "metrics.dashboard_not_found") from None
    except access.DashboardRefused as refusal:
        raise Problem(403, DASHBOARD_NEEDS[refusal.required]) from None


async def _public_dashboard(session: AsyncSession, dashboard: Dashboard, held: Access) -> DashboardPublic:
    owner = None if held == "own" else await session.get(User, dashboard.owner_id)
    return dashboard_public(dashboard, held, None if owner is None else owner_named(owner))


async def _store(session: AsyncSession, holder: StoreHolder) -> MetricsStore:
    try:
        store = await holder.get(session)
    except StoreUnavailable:
        raise _unavailable() from None
    if store is None:
        raise Problem(409, "metrics.not_set_up")
    return store


def _unavailable() -> HTTPException:
    return Problem(503, "metrics.store_not_answering")


async def _own_agent(
    session: AsyncSession, agent_id: uuid.UUID, owner_id: uuid.UUID
) -> MetricsAgent:
    agent = await crud.agent_of(session, agent_id, owner_id)
    if agent is None:
        raise Problem(404, "metrics.agent_not_found")
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


def _host(row: HostRow, agent_name: str) -> AgentHost:
    host = AgentHost(
        agent_id=row.run.source_id,
        agent_name=agent_name,
        host=row.run.host,
        agent_version=row.run.version,
        agent_started=datetime.fromtimestamp(row.run.started, UTC),
        last_seen=row.last_seen,
    )
    if row.info is None:
        return host
    return host.model_copy(
        update={
            "os": row.info.os,
            "kernel": row.info.kernel,
            "arch": row.info.arch,
            "cpus": row.info.cpus,
            "cpu_model": row.info.cpu_model,
            "memory_bytes": row.info.memory,
            "booted_at": datetime.fromtimestamp(row.info.boot_time, UTC),
            "collectors": dict(row.info.collectors),
        }
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
