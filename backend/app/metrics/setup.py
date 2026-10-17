"""Setting the store up on first entry, by a superuser, one of two ways (D126),
and taking it away."""

import uuid
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters import registry
from app.adapters.features import SupportsSourceFeatures
from app.adapters.protocol import AdapterError
from app.connectors.access import context_for
from app.connectors.service import build_adapter, split_options
from app.core.config import settings
from app.core.translation import N_, say
from app.jobs import crud as job_crud
from app.jobs.models import JobKind
from app.jobs.models import public as job_public
from app.jobs.runner import JobRunner
from app.metrics import crud
from app.metrics.history import TIERS
from app.metrics.holder import StoreHolder, options_of
from app.metrics.models import StartOffer, StoreStatus, StoreUsage, TierInfo
from app.metrics.store import MetricsStore, StoreUnavailable, store_url
from app.realtime.topics import TopicSet
from app.services import crud as service_crud
from app.services import templates
from app.services.engine import ServiceEngine, service_offer
from app.services.models import ManagedService
from app.services.plan import Placement
from app.users.models import User

STORE_TEMPLATE_KEY = "timescaledb"
STORE_ADAPTER_TYPE = "postgres"
STORE_SERVICE_NAME = "Metrics store"

NOT_ANSWERING = N_("The metrics store is not answering")
NOT_SET_UP = N_("Dashboards are not set up yet")


class SetupRefused(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


async def status(
    session: AsyncSession, holder: StoreHolder, user: User, engine: ServiceEngine
) -> StoreStatus:
    may_set_up = user.is_superuser
    start: StartOffer | None = None
    if may_set_up:
        offer = await service_offer(engine)
        start = StartOffer(available=offer.available, reason=offer.reason)
    if await crud.store_setting(session) is not None:
        try:
            store = await holder.get(session)
            answering = store is not None and await store.ping()
        except StoreUnavailable:
            answering = False
        return StoreStatus(
            state="ready" if answering else "unreachable",
            may_set_up=may_set_up,
            start=start,
            message=None if answering else say(NOT_ANSWERING),
        )
    service = await service_crud.metrics_store_service(session)
    if service is None or service.state not in {"creating", "failed"}:
        return StoreStatus(state="not_configured", may_set_up=may_set_up, start=start)
    jobs = await job_crud.for_subject(session, service.id, limit=1)
    job = job_public(jobs[0]) if jobs else None
    return StoreStatus(
        state="starting" if service.state == "creating" else "failed",
        may_set_up=may_set_up,
        start=start,
        job=job,
        message=job.message if job is not None and service.state == "failed" else None,
    )


async def start(
    session: AsyncSession,
    runner: JobRunner,
    topics: TopicSet,
    engine: ServiceEngine,
    user: User,
) -> None:
    """Start TimescaleDB here. Asking again while it starts is asking once."""
    if await crud.store_setting(session) is not None:
        raise SetupRefused(409, say("Dashboards are already set up"))
    service = await service_crud.metrics_store_service(session)
    if service is not None and service.state == "creating":
        return
    offer = await service_offer(engine)
    if not offer.available:
        raise SetupRefused(503, offer.reason or say("This server cannot run services"))
    if service is not None and service.state == "failed":
        # Starting over, as a service retry does (D84).
        await service_crud.set_state(session, service, "creating")
    else:
        service = await service_crud.create(
            session,
            owner_id=user.id,
            template=templates.template_for(STORE_TEMPLATE_KEY),
            connector_name=STORE_SERVICE_NAME,
            placement=Placement(
                network=settings.SERVICE_NETWORK or None, publish=False, host_port=None
            ),
            purpose="metrics_store",
        )
    kind: JobKind = "metrics.store.create"
    job = await job_crud.create(
        session,
        owner_id=service.owner_id,
        kind=kind,
        subject_id=service.id,
        step_count=len(runner.steps_of(kind)),
    )
    await runner.launch(job, topics)


async def connect(session: AsyncSession, user: User, options: dict[str, Any]) -> None:
    """Use an existing TimescaleDB, once it answers and can hold the schema.

    Raises `pydantic.ValidationError` for options that are not the adapter's.
    """
    if await crud.store_setting(session) is not None:
        raise SetupRefused(409, say("Dashboards are already set up"))
    kind = registry.get(STORE_ADAPTER_TYPE)
    adapter = build_adapter(kind, options, context_for(user.id))
    check = await adapter.check_connection()
    if not check.ok:
        raise SetupRefused(422, check.message)
    if isinstance(adapter, SupportsSourceFeatures):
        try:
            features = await adapter.source_features()
        except (AdapterError, ValueError):
            features = None
        timescale = next(
            (item for item in features.features if item.code == "timescaledb"), None
        ) if features is not None else None
        if timescale is not None and timescale.state in {"unsupported", "unavailable"}:
            raise SetupRefused(422, timescale.reason or say("TimescaleDB cannot be used there"))
    config, secrets = split_options(kind, options)
    store = MetricsStore(store_url(options))
    try:
        await store.migrate()
    except StoreUnavailable:
        raise SetupRefused(
            422,
            say(
                "TimescaleDB could not be prepared in that database: it is not "
                "installed there, or this role may not create it"
            ),
        ) from None
    finally:
        await store.aclose()
    await crud.save_store_setting(
        session, config=config, secrets=secrets, service_id=None, configured_by=user.id
    )
    await session.commit()


async def usage(session: AsyncSession, holder: StoreHolder) -> StoreUsage:
    """Where the store is, what it takes and how long it keeps what."""
    setting = await crud.store_setting(session)
    if setting is None:
        raise SetupRefused(409, say(NOT_SET_UP))
    measured = None
    try:
        store = await holder.get(session)
        measured = await store.usage() if store is not None else None
    except StoreUnavailable:
        measured = None
    config = setting.config
    return StoreUsage(
        origin="connected" if await _service_of(session, setting.service_id) is None else "started",
        address=f"{config.get('host')}:{config.get('port')}/{config.get('database')}",
        bytes=measured.bytes if measured is not None else None,
        series=measured.series if measured is not None else None,
        tiers=[
            TierInfo(name=tier.name, width_seconds=tier.width, kept_seconds=tier.kept)
            for tier in TIERS
        ],
    )


async def remove(
    session: AsyncSession,
    holder: StoreHolder,
    runner: JobRunner,
    topics: TopicSet,
    user: User,
) -> str:
    """Stop using the store, and take every sample with it.

    Started here, the service is removed with its volume by the job that
    removes any service. Connected, the database stays its owner's and the
    tables the migrations made in it are dropped. Either way the setting goes
    first, so nothing prepares the schema again in between, and every widget
    naming a series is taken off its dashboard: a new store numbers its series
    from one again, and an old id would draw somebody else's host.
    """
    setting = await crud.store_setting(session)
    if setting is None:
        raise SetupRefused(409, say(NOT_SET_UP))
    service = await _service_of(session, setting.service_id)
    options = options_of(setting)
    await session.delete(setting)
    await crud.forget_series(session)
    await session.commit()
    await holder.aclose()
    if service is not None:
        await service_crud.set_state(session, service, "removing")
        kind: JobKind = "service.delete"
        job = await job_crud.create(
            session,
            owner_id=user.id,
            kind=kind,
            subject_id=service.id,
            step_count=len(runner.steps_of(kind)),
        )
        await runner.launch(job, topics)
        return say("The metrics store is being removed with every sample in it")
    store = MetricsStore(store_url(options))
    try:
        await store.drop_schema()
    except StoreUnavailable:
        return say(
            "Dashboards no longer use that database. It did not answer, so the "
            "tables they kept there are still in it"
        )
    finally:
        await store.aclose()
    return say("Dashboards no longer use that database, and the tables they kept there were dropped")


async def _service_of(
    session: AsyncSession, service_id: uuid.UUID | None
) -> ManagedService | None:
    """The service a store was started as, while its row is still there."""
    if service_id is None:
        return None
    return await session.get(ManagedService, service_id)
