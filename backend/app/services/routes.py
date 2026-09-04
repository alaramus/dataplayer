import uuid
from collections.abc import Mapping
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters import registry
from app.adapters.cache import DataCache, DataCacheDep
from app.adapters.protocol import DescribesDraft, SupportsSampleData
from app.adapters.registry import AdapterType
from app.connectors import crud as connector_crud
from app.connectors.models import Connector
from app.core import crypto
from app.core.config import settings
from app.core.db import SessionDep, async_session_maker
from app.core.schemas import Message
from app.jobs import crud as job_crud
from app.jobs.models import Job, JobKind
from app.jobs.models import public as job_public
from app.jobs.runner import JobRunner, JobRunnerDep
from app.realtime.topics import TopicsDep, TopicSet
from app.services import crud, templates
from app.services.engine import (
    Availability,
    ContainerStatus,
    EngineError,
    ServiceEngine,
    ServiceEngineDep,
)
from app.services.models import (
    BUSY_STATES,
    UNUSABLE_PASSWORD,
    ChosenPassword,
    ChosenStart,
    ContainerReport,
    ManagedService,
    NoPassword,
    PasswordMode,
    ServiceAccepted,
    ServiceCredentials,
    ServicePublic,
    ServiceRequest,
    ServiceState,
    StartRequest,
    password_survives_where_it_goes,
)
from app.services.plan import Placement, settled_names
from app.services.templates import (
    DATABASE,
    PASSWORD,
    USER,
    UnknownServiceTemplate,
)
from app.users.deps import (
    CurrentUser,
    get_current_active_superuser,
    get_current_user,
)

# Authentication on the router, as `adapter-types` declares it: the template
# listing does not use the user, and an unused argument is a lint error.
#
# The tag has no hyphen for the same reason that one does not: the client
# generator cuts the method name at the first hyphen of the operation id.
router = APIRouter(
    prefix="/services",
    tags=["services"],
    dependencies=[Depends(get_current_user)],
)


class ServiceTemplateInfo(BaseModel):
    """One service this server may be asked to start.

    What a client is allowed to know: which key names it, what will run, and
    what it becomes. Not the container it would create — that is decided by
    the server and is nothing a request may steer, so publishing it would only
    invite the belief that it can.
    """

    key: str
    title: str
    description: str
    # The exact image, so somebody deciding whether to press the button can
    # see what would be pulled onto the machine.
    image: str
    container_port: int
    # What the ready service becomes, in both the name routes use and the
    # words the adapter calls itself by. Sent rather than joined on the client
    # against the adapter-types list: one name for a source type, and it is
    # the server's.
    adapter_type: str
    adapter_title: str
    # Which credentials this server makes up. A statement about what a person
    # will not be asked for, which is the whole difference from the old form.
    generated: list[templates.CredentialSlot]
    # And which of them a person may name themselves when they want to. The
    # form that asks is built from this, so a template that opens a slot gains
    # a field without the client being changed.
    choosable: list[templates.CredentialSlot]
    # Whether this one runs without a password at all as an ordinary
    # configuration. Read off the template, so the form offers the choice
    # exactly where the server would accept it (D82's rule about offers).
    optional_password: bool
    # Whether this server has anything to put in one of these worth looking
    # at. Read off the driver, so a type that cannot be filled does not offer
    # to be.
    offers_sample_data: bool
    # Whether this server could actually start one now, and why not when it
    # could not. Said where the offer is made rather than only when the button
    # is pressed: a screen that offers what will be refused is a screen that
    # lies (D82).
    available: bool
    unavailable_reason: str | None = None


class UnclaimedContainer(BaseModel):
    """A container this installation made that no row claims any more."""

    name: str
    state: str
    service_id: str | None


class ServiceLogs(BaseModel):
    """The tail of one service's own output."""

    lines: list[str]


# Declared before "/{service_id}": a path that is a fixed word must be matched
# before one that is a parameter, whatever the parameter's type would do.
@router.get("/templates", response_model=list[ServiceTemplateInfo])
async def read_service_templates(engine: ServiceEngineDep) -> Any:
    """
    List the services this server can start, and what each one becomes.

    A closed set written in code. A client picks a key from it; nothing about
    the container is a request's to choose (D80). Every entry also says
    whether it could be started now, because the runtime is a property of the
    server rather than of the template and can be gone while the server runs.
    """
    runtime = await _offer(engine)
    return [
        ServiceTemplateInfo(
            key=template.key,
            title=template.title,
            description=template.description,
            image=template.image,
            container_port=template.container_port,
            adapter_type=template.adapter_type,
            adapter_title=registry.get(template.adapter_type).title,
            generated=list(templates.generated_slots(template)),
            choosable=list(templates.choosable_slots(template)),
            optional_password=templates.may_run_unprotected(template),
            offers_sample_data=issubclass(
                registry.get(template.adapter_type).adapter_class, SupportsSampleData
            ),
            available=runtime.available,
            unavailable_reason=runtime.reason,
        )
        for template in templates.all_templates()
    ]


@router.post("/", response_model=ServiceAccepted)
async def request_service(
    session: SessionDep,
    current_user: CurrentUser,
    runner: JobRunnerDep,
    topics: TopicsDep,
    engine: ServiceEngineDep,
    body: ServiceRequest,
) -> Any:
    """
    Ask for one of the approved services.

    The request writes the service down, accepts a job and answers. It does
    not wait: pulling an image is minutes of somebody else's network, and an
    HTTP request that waited for it would be a request that times out while
    the work carries on regardless (D81).
    """
    try:
        template = templates.template_for(body.template_key)
    except UnknownServiceTemplate:
        raise HTTPException(
            status_code=422,
            detail={"message": "This server does not offer that service"},
        ) from None
    if body.request_id is not None:
        already = await crud.by_request(
            session, owner_id=current_user.id, request_id=body.request_id
        )
        if already is not None:
            # The same request, asked again: a double press, or a POST the
            # network retried. One service, and the job that is making it.
            return await _already(session, already)
    _refuse_without_a_runtime(await _offer(engine))
    await _refuse_if_at_the_ceiling(session, current_user.id)
    chosen = _chosen_credentials(template, body.start)
    password_mode, chosen_password = _password_choice(template, body.start)
    service = await crud.create(
        session,
        owner_id=current_user.id,
        template=template,
        connector_name=await _name_for(session, current_user.id, template, body.start),
        placement=_placement(body.start),
        request_id=body.request_id,
        chosen_credentials=chosen,
        sample_data=_wants_sample_data(body.start),
        password_mode=password_mode,
        chosen_password=chosen_password,
    )
    job = await _accept(session, runner, topics, service, "service.create")
    return ServiceAccepted(
        service=_public(service, job, "unknown"), job=job_public(job)
    )


@router.get("/", response_model=list[ServicePublic])
async def read_services(
    session: SessionDep, current_user: CurrentUser, engine: ServiceEngineDep
) -> Any:
    """
    The services this user has asked this server to run.

    Each says what the runtime reports about it as well as what this
    application believes, because the two can differ: a container somebody
    removed by hand is `missing`, and a server that could not ask says
    `unknown` rather than guessing (D84).
    """
    services = await crud.list_for_owner(session, current_user.id)
    found = await _managed(engine)
    reported = _by_name(found)
    return [
        _public(
            service,
            await _latest_job(session, service),
            _reported_state(reported, service.container_name, asked=found is not None),
        )
        for service in services
    ]


@router.get(
    "/unclaimed",
    response_model=list[UnclaimedContainer],
    dependencies=[Depends(get_current_active_superuser)],
)
async def read_unclaimed(engine: ServiceEngineDep) -> Any:
    """
    Containers this installation made that no service row claims any more.

    A machine-wide question, so an administrator's: what runs on the server is
    not one user's business, and what is found here may be anybody's. Matched
    by label rather than by name, because a name is for people to read (D80).
    """
    known = await _known_container_names()
    return [
        UnclaimedContainer(
            name=one.name, state=one.state, service_id=one.service_id
        )
        for one in (await _managed(engine) or [])
        if one.name not in known
    ]


@router.delete(
    "/unclaimed/{container_name}",
    response_model=Message,
    dependencies=[Depends(get_current_active_superuser)],
)
async def remove_unclaimed(engine: ServiceEngineDep, container_name: str) -> Any:
    """
    Take away a container this installation made and nothing claims.

    Straight to the runtime rather than through a job: there is no row to give
    the work to, and nothing to report progress about. The volume goes with
    it, because a volume made for a container nothing claims is claimed by
    nothing either.
    """
    known = await _known_container_names()
    if container_name in known:
        raise HTTPException(
            status_code=409,
            detail={"message": "A service still claims that container"},
        )
    if container_name not in {one.name for one in (await _managed(engine) or [])}:
        raise HTTPException(status_code=404, detail={"message": "No such container"})
    await engine.remove(container_name, volume=f"{container_name}-data")
    return Message(message=f"{container_name} was removed")


@router.get("/{service_id}", response_model=ServicePublic)
async def read_service(
    session: SessionDep,
    current_user: CurrentUser,
    engine: ServiceEngineDep,
    service_id: uuid.UUID,
) -> Any:
    """
    One service, with the last thing that happened to it.
    """
    service = await _own_or_404(session, service_id, current_user.id)
    found = await _managed(engine)
    return _public(
        service,
        await _latest_job(session, service),
        _reported_state(
            _by_name(found), service.container_name, asked=found is not None
        ),
    )


@router.get("/{service_id}/credentials", response_model=ServiceCredentials)
async def read_service_credentials(
    session: SessionDep, current_user: CurrentUser, service_id: uuid.UUID
) -> Any:
    """
    Where a service listens, and under what names, as often as it is asked.

    A service is used through the connection it became, and this application
    never needs any of this. It is here because somebody who started a
    database usually wants to point their own tools at it too, and the address
    it answers on is not the one the connector holds — that is a container
    name on a network only this server is on.

    Never the password. It is encrypted in the connector and stays there
    (D4); somebody who needs to know a service's password starts one with a
    password of their own. That is what makes this answerable more than once,
    and what makes it answerable at all for a service whose connection its
    owner has since deleted.
    """
    service = await _own_or_404(session, service_id, current_user.id)
    if service.connected_at is None:
        raise HTTPException(
            status_code=409,
            detail={"message": "This service has no connection yet"},
        )
    return _credentials_of(service)


@router.get("/{service_id}/logs", response_model=ServiceLogs)
async def read_service_logs(
    session: SessionDep,
    current_user: CurrentUser,
    engine: ServiceEngineDep,
    service_id: uuid.UUID,
    tail: int = 200,
) -> Any:
    """
    The last lines this service printed.

    What a person reads when something did not start. Its own output and
    nothing else: this application's log is not a user's to read, and the
    runtime's words about the machine are not either (D84).
    """
    service = await _own_or_404(session, service_id, current_user.id)
    try:
        found = await engine.logs(service.container_name, tail=max(1, min(tail, 500)))
    except EngineError as refusal:
        raise HTTPException(status_code=409, detail={"message": str(refusal)}) from None
    return ServiceLogs(lines=found.lines)


@router.post("/{service_id}/retry", response_model=ServiceAccepted)
async def retry_service(
    session: SessionDep,
    current_user: CurrentUser,
    runner: JobRunnerDep,
    topics: TopicsDep,
    engine: ServiceEngineDep,
    service_id: uuid.UUID,
) -> Any:
    """
    Make it again, from the beginning.

    Not "carry on where it stopped": a password this server made up is settled
    once per attempt and lives only in the connector that attempt would have
    saved, so whatever a failed one left behind has a password nobody knows.
    Starting over is the only honest meaning of retry here, and it takes the
    earlier container and its data with it (D84). A password somebody typed is
    the exception that proves it — it is still on the row, encrypted, because
    no connector took it over, so the second attempt uses the same one.

    A service that ever became a connection is refused: that one is finished,
    and remaking it would destroy a database somebody is using. Asked of the
    stamp rather than of `connector_id`, which goes null again when somebody
    deletes the connection — the database is still there, and offering to
    start over would offer to destroy it (D84).
    """
    service = await _own_or_404(session, service_id, current_user.id)
    if service.connected_at is not None:
        raise HTTPException(
            status_code=409,
            detail={"message": "This service is already made; remove it instead"},
        )
    await _refuse_if_working(session, service)
    _refuse_without_a_runtime(await _offer(engine))
    await crud.set_state(session, service, "creating")
    job = await _accept(session, runner, topics, service, "service.create")
    return ServiceAccepted(service=_public(service, job, "unknown"), job=job_public(job))


@router.post("/{service_id}/start", response_model=ServiceAccepted)
async def start_service(
    session: SessionDep,
    current_user: CurrentUser,
    runner: JobRunnerDep,
    topics: TopicsDep,
    service_id: uuid.UUID,
) -> Any:
    """
    Start a service that is not running.
    """
    return await _command(session, runner, topics, service_id, current_user.id, "service.start")


@router.post("/{service_id}/stop", response_model=ServiceAccepted)
async def stop_service(
    session: SessionDep,
    current_user: CurrentUser,
    runner: JobRunnerDep,
    topics: TopicsDep,
    service_id: uuid.UUID,
) -> Any:
    """
    Stop a running service, keeping its data.
    """
    return await _command(session, runner, topics, service_id, current_user.id, "service.stop")


@router.post("/{service_id}/restart", response_model=ServiceAccepted)
async def restart_service(
    session: SessionDep,
    current_user: CurrentUser,
    runner: JobRunnerDep,
    topics: TopicsDep,
    service_id: uuid.UUID,
) -> Any:
    """
    Restart a service.
    """
    return await _command(
        session, runner, topics, service_id, current_user.id, "service.restart"
    )


@router.delete("/{service_id}", response_model=ServiceAccepted)
async def delete_service(
    session: SessionDep,
    current_user: CurrentUser,
    runner: JobRunnerDep,
    topics: TopicsDep,
    data_cache: DataCacheDep,
    service_id: uuid.UUID,
    delete_connector: bool = False,
) -> Any:
    """
    Remove a service and the data it kept, and its connection when asked.

    Destructive, and meant to be: the volume was made for this service and
    belongs to nothing else. The service is not gone when this answers — the
    job is what removes it, and the row stays until the container is gone so
    that a failure leaves something a person can see.

    The connection is a separate decision, which is why it is a separate
    answer rather than something this route assumes either way. It may be
    shared and it may be named in somebody's query history, so it goes only
    when its owner says so — and it goes here rather than in the job, through
    the same path a connection deleted from its own screen takes: deleting a
    row of this application is not minutes of work to watch.
    """
    service = await _own_or_404(session, service_id, current_user.id)
    # Not `_refuse_if_busy`: removal is the way out of every state, including
    # the `creating` a job that never finished left behind.
    await _refuse_if_working(session, service)
    if delete_connector:
        await _delete_the_connection(session, data_cache, service)
    await crud.set_state(session, service, "removing")
    job = await _accept(session, runner, topics, service, "service.delete")
    return ServiceAccepted(
        service=_public(service, job, "unknown"), job=job_public(job)
    )


async def _delete_the_connection(
    session: AsyncSession, data_cache: DataCache, service: ManagedService
) -> None:
    """Take the connector this service made, if it still has one.

    Through the connector's own deletion so that what happens is exactly what
    happens when somebody deletes it from its own screen, cached pool
    included. It never reaches a container or a volume — that is this
    command's other half, and it is the job's (D84).
    """
    if service.connector_id is None:
        return
    connector = await session.get(Connector, service.connector_id)
    if connector is None:
        return
    await connector_crud.delete(session, connector=connector)
    await data_cache.invalidate_connector(connector.id)
    await session.refresh(service)


async def _command(
    session: AsyncSession,
    runner: JobRunner,
    topics: TopicSet,
    service_id: uuid.UUID,
    owner_id: uuid.UUID,
    kind: JobKind,
) -> ServiceAccepted:
    """One lifecycle command: the same three checks, then a job.

    The checks are here rather than in each route because they are one rule —
    it is yours, it is not busy, and nothing else is already doing something
    to it — and three copies of a rule is how one of them comes to differ.
    """
    service = await _own_or_404(session, service_id, owner_id)
    # What is happening now is asked first: it is the more useful refusal,
    # because it names the job to watch rather than only the state it left.
    await _refuse_if_working(session, service)
    _refuse_if_busy(service)
    job = await _accept(session, runner, topics, service, kind)
    return ServiceAccepted(
        service=_public(service, job, "unknown"), job=job_public(job)
    )


async def _accept(
    session: AsyncSession,
    runner: JobRunner,
    topics: TopicSet,
    service: ManagedService,
    kind: JobKind,
) -> Job:
    """Write the job down, then start carrying it out.

    In that order: a job that exists only as a task is a job a restart loses
    silently, which is what the old application had.
    """
    job = await job_crud.create(
        session,
        owner_id=service.owner_id,
        kind=kind,
        subject_id=service.id,
        step_count=len(runner.steps_of(kind)),
    )
    await runner.launch(job, topics)
    return job


async def _own_or_404(
    session: AsyncSession, service_id: uuid.UUID, owner_id: uuid.UUID
) -> ManagedService:
    service = await crud.get_for_owner(session, service_id, owner_id)
    if service is None:
        raise HTTPException(status_code=404, detail={"message": "No such service"})
    return service


# What a server without a network can say. Reaching a service is reaching a
# container by name, and a name resolves only on a network they share, so a
# service that could be started and not reached is not offered at all.
NO_NETWORK_MESSAGE = "This server has no network to put a service on"


def _placement(start: StartRequest) -> Placement:
    """Where a service goes: the configured network, and a port on the machine.

    The network is how this server reaches it — by container name, which
    resolves only on a network they share. A port on the host is a second
    thing and a different audience: it is what lets the person who started it
    open it in their own tools, and it is bound to the loopback address (D86).

    Every service published, in both modes, because a database nobody can
    open in their own tools was a choice that only ever produced a service
    somebody then had to remake. Which port is still the runtime's answer
    unless a person named one, and a named one is the only number about a
    container a request may carry.
    """
    return Placement(
        network=settings.SERVICE_NETWORK or None,
        publish=True,
        host_port=start.port or None if isinstance(start, ChosenStart) else None,
    )


def _chosen_credentials(
    template: templates.ServiceTemplate, start: StartRequest
) -> dict[str, str]:
    """What the requester named, checked against what the template opened.

    A value for a slot this template does not call choosable is refused rather
    than dropped: silently ignoring it would let somebody believe they had
    named the role of a Redis server.

    The password is not among these. It goes to the row encrypted, and this
    dictionary is a JSON column anybody with the database can read.
    """
    if not isinstance(start, ChosenStart):
        return {}
    named = {"user": start.user, "database": start.database}
    chosen: dict[str, str] = {}
    for slot, value in named.items():
        if value is None:
            continue
        if slot not in template.choosable:
            raise HTTPException(
                status_code=422,
                detail={"message": f"This service has no {slot} to name"},
            )
        chosen[slot] = value
    return chosen


def _password_choice(
    template: templates.ServiceTemplate, start: StartRequest
) -> tuple[str, bytes | None]:
    """How this service's password was decided, and the typed one encrypted.

    Three answers, and the refusals are what makes them three rather than a
    field left empty. A template with nothing to protect cannot be given a
    password, and one that has no unprotected shape cannot be asked to run
    without one: a PostgreSQL that trusts every connection is not a service
    this server will start.

    A typed password is encrypted here, at the edge, so that nothing between
    this function and the database holds it in the clear. It is a connector
    secret that has not reached its connector yet, so it is encrypted under
    the connector key (D4).
    """
    if not isinstance(start, ChosenStart):
        return "generated", None
    choice = start.password
    if isinstance(choice, NoPassword):
        if not templates.may_run_unprotected(template):
            raise HTTPException(
                status_code=422,
                detail={"message": "This service cannot run without a password"},
            )
        return "none", None
    if isinstance(choice, ChosenPassword):
        if PASSWORD not in template.choosable:
            raise HTTPException(
                status_code=422,
                detail={"message": "This service has no password to name"},
            )
        plain = choice.value.get_secret_value()
        if not password_survives_where_it_goes(plain):
            # Refused here rather than by a constraint on the field: a failed
            # constraint puts the value it rejected into the validation error,
            # and a 422 body echoing somebody's password is the thing
            # `SecretStr` is there to prevent.
            raise HTTPException(
                status_code=422, detail={"message": UNUSABLE_PASSWORD}
            )
        return "chosen", crypto.encrypt(plain.encode(), purpose="connector")
    return "generated", None


def _wants_sample_data(start: StartRequest) -> bool:
    """An automatic start is a demonstration, so it fills what it starts."""
    return start.sample_data if isinstance(start, ChosenStart) else True


async def _name_for(
    session: AsyncSession,
    owner_id: uuid.UUID,
    template: templates.ServiceTemplate,
    start: StartRequest,
) -> str:
    """What the connection will be called.

    A chosen start says. An automatic one is not asked — somebody who has not
    been asked for a name has not got one in mind — so the server makes one
    the same way a person would: what it is, and which one of them it is.
    """
    if isinstance(start, ChosenStart):
        return start.name
    taken = await crud.names_taken(session, owner_id)
    number = 1
    while f"{template.title} {number}" in taken:
        number += 1
    return f"{template.title} {number}"


async def _offer(engine: ServiceEngine) -> Availability:
    """Whether a service could be started here and then used.

    The runtime first, because it is the more fundamental answer, and the
    network second: a server that cannot reach what it starts is offering
    something nobody could open.
    """
    runtime = await engine.availability()
    if not runtime.available:
        return runtime
    if not settings.SERVICE_NETWORK:
        return Availability(available=False, reason=NO_NETWORK_MESSAGE)
    return runtime


def _refuse_without_a_runtime(runtime: Availability) -> None:
    """Refuse before a service exists rather than after a job fails.

    A job would fail with the same sentence — the engine refuses every verb —
    but a row and a failed job are a mess left behind by a question that could
    have been answered. The job is still the authority if the runtime goes
    away between this and the pull.
    """
    if not runtime.available:
        raise HTTPException(
            status_code=503,
            detail={"message": runtime.reason or "This server cannot run services"},
        )


async def _refuse_if_at_the_ceiling(
    session: AsyncSession, owner_id: uuid.UUID
) -> None:
    """One person may hold only so much of the machine at once (D86).

    Not a quota system: a number that turns "somebody left a loop running"
    into a refusal they can read instead of an outage everybody meets. What
    they already have is theirs to remove.
    """
    held = await crud.count_for_owner(session, owner_id)
    if held >= settings.SERVICE_MAX_PER_USER:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    f"You already have {held} services on this server; "
                    "remove one before starting another"
                )
            },
        )


def _refuse_if_busy(service: ManagedService) -> None:
    if service.state in BUSY_STATES:
        raise HTTPException(
            status_code=409,
            detail={"message": f"This service is {service.state}"},
        )


async def _refuse_if_working(session: AsyncSession, service: ManagedService) -> None:
    """One job at a time per service.

    Two at once would be two processes telling one container what to do, and
    the second would report the outcome of a race rather than of a command.
    """
    working = await job_crud.unfinished_for_subject(session, service.id)
    if working is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Something is already happening to this service",
                "job_id": str(working.id),
            },
        )


async def _already(session: AsyncSession, service: ManagedService) -> ServiceAccepted:
    """The answer to a request that was already answered once."""
    job = await _latest_job(session, service)
    if job is None:
        raise HTTPException(
            status_code=409,
            detail={"message": "That request made a service with no job"},
        )
    return ServiceAccepted(service=_public(service, job, "unknown"), job=job_public(job))


async def _managed(engine: ServiceEngine) -> list[ContainerStatus] | None:
    """Every container this installation made, or nothing when it cannot ask.

    `None` rather than an empty list, because the two mean opposite things: a
    runtime holding nothing says every service is missing, and a runtime that
    could not be reached says nothing about any of them.
    """
    try:
        return await engine.managed()
    except EngineError:
        return None


def _by_name(found: list[ContainerStatus] | None) -> dict[str, ContainerReport]:
    """What the runtime said, by container name.

    One question for the whole list rather than one per service: a listing
    that asked per row would cost a request per service, and the daemon can
    answer them all at once.
    """
    return {one.name: one.state for one in found or []}


def _reported_state(
    reported: Mapping[str, ContainerReport], name: str, *, asked: bool
) -> ContainerReport:
    if not asked:
        return "unknown"
    return reported.get(name, "missing")


async def _known_container_names() -> set[str]:
    """The containers some service row still claims.

    Its own session, because the question is about every owner's services
    rather than the caller's: a set filtered by caller would call another
    person's service an orphan.
    """
    async with async_session_maker() as session:
        return await crud.all_container_names(session)


async def _latest_job(session: AsyncSession, service: ManagedService) -> Job | None:
    jobs = await job_crud.for_subject(session, service.id, limit=1)
    return jobs[0] if jobs else None


def _public(
    service: ManagedService, job: Job | None, container_state: ContainerReport
) -> ServicePublic:
    return ServicePublic(
        id=service.id,
        template_key=service.template_key,
        title=_title_of(service.template_key),
        # A column is a string, and these are the only values written to
        # it: every write goes through this package.
        state=cast(ServiceState, service.state),
        container_state=container_state,
        container_name=service.container_name,
        published_port=service.published_port,
        connector_id=service.connector_id,
        connector_name=service.connector_name,
        was_connected=service.connected_at is not None,
        created_at=service.created_at,
        job=job_public(job) if job is not None else None,
    )


# Where a service published on this machine answers. The container is bound to
# the loopback address, so this is the only address that reaches it — and it is
# the address as seen from the machine the server runs on, which is what a
# person pasting it into their own tool needs.
PUBLISHED_HOST = "127.0.0.1"

# Why there is nothing to paste, when there is nothing.
NOT_PUBLISHED = (
    "This service has no port on the host, so only this application can reach it"
)


def _credentials_of(service: ManagedService) -> ServiceCredentials:
    """Where this service listens, and under what names.

    Off the row and its template rather than out of the connector. The
    connector would do while it exists, but it holds the container name on
    this server's own network — every value here would have to be replaced or
    ignored — and it is gone the moment its owner deletes it, which is exactly
    when somebody still wants to know where the container they still have is
    listening.

    Nothing secret is read, so nothing is decrypted: the names come from the
    template's constants and from what the requester chose, and the address
    from what the runtime reported.
    """
    template = templates.template_for(service.template_key)
    names = settled_names(template, service.chosen_credentials)
    published = service.published_port
    parts = {
        "host": PUBLISHED_HOST,
        "port": published,
        "user": names.get(USER),
        "database": names.get(DATABASE),
    }
    return ServiceCredentials(
        host=PUBLISHED_HOST if published is not None else None,
        port=published,
        user=names.get(USER),
        database=names.get(DATABASE),
        password_mode=cast(PasswordMode, service.password_mode),
        url=_url_of(registry.get(template.adapter_type), parts)
        if published is not None
        else None,
        unreachable_reason=None if published is not None else NOT_PUBLISHED,
    )


def _url_of(kind: AdapterType, parts: Mapping[str, Any]) -> str | None:
    """The one-line address, written by the source type that owns the grammar.

    `draft_connection_string` because that is the one that composes from loose
    values rather than from a built adapter — which is what this has: a
    published port on the host, not the container name the connector holds. It
    leaves the password out, as every address this application shows does. A
    type that cannot write one at all answers with nothing, and the window
    shows the parts alone.
    """
    driver = kind.adapter_class
    if not issubclass(driver, DescribesDraft):
        return None
    return driver.draft_connection_string(parts)




def _title_of(template_key: str) -> str:
    """What this kind of service is called, or the key if it is no longer one.

    A template can be taken out of the code while a service made from it is
    still running, and a screen still has to name it.
    """
    try:
        return templates.template_for(template_key).title
    except UnknownServiceTemplate:
        return template_key
