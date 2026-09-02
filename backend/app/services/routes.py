import uuid
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters import registry
from app.core.db import SessionDep
from app.jobs import crud as job_crud
from app.jobs.models import Job, JobKind
from app.jobs.models import public as job_public
from app.jobs.runner import JobRunner, JobRunnerDep
from app.realtime.topics import TopicsDep, TopicSet
from app.services import crud, templates
from app.services.engine import Availability, ServiceEngineDep
from app.services.models import (
    BUSY_STATES,
    ManagedService,
    ServiceAccepted,
    ServicePublic,
    ServiceRequest,
    ServiceState,
)
from app.services.templates import UnknownServiceTemplate
from app.users.deps import CurrentUser, get_current_user

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
    # Whether this server could actually start one now, and why not when it
    # could not. Said where the offer is made rather than only when the button
    # is pressed: a screen that offers what will be refused is a screen that
    # lies (D82).
    available: bool
    unavailable_reason: str | None = None


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
    runtime = await engine.availability()
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
    _refuse_without_a_runtime(await engine.availability())
    service = await crud.create(session, owner_id=current_user.id, template=template)
    job = await _accept(session, runner, topics, service, "service.create")
    return ServiceAccepted(service=_public(service, job), job=job_public(job))


@router.get("/", response_model=list[ServicePublic])
async def read_services(session: SessionDep, current_user: CurrentUser) -> Any:
    """
    The services this user has asked this server to run.
    """
    services = await crud.list_for_owner(session, current_user.id)
    return [
        _public(service, await _latest_job(session, service)) for service in services
    ]


@router.get("/{service_id}", response_model=ServicePublic)
async def read_service(
    session: SessionDep, current_user: CurrentUser, service_id: uuid.UUID
) -> Any:
    """
    One service, with the last thing that happened to it.
    """
    service = await _own_or_404(session, service_id, current_user.id)
    return _public(service, await _latest_job(session, service))


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
    service_id: uuid.UUID,
) -> Any:
    """
    Remove a service and the data it kept.

    Destructive, and meant to be: the volume was made for this service and
    belongs to nothing else. The service is not gone when this answers — the
    job is what removes it, and the row stays until the container is gone so
    that a failure leaves something a person can see.
    """
    service = await _own_or_404(session, service_id, current_user.id)
    # Not `_refuse_if_busy`: removal is the way out of every state, including
    # the `creating` a job that never finished left behind.
    await _refuse_if_working(session, service)
    await crud.set_state(session, service, "removing")
    job = await _accept(session, runner, topics, service, "service.delete")
    return ServiceAccepted(service=_public(service, job), job=job_public(job))


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
    return ServiceAccepted(service=_public(service, job), job=job_public(job))


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


async def _latest_job(session: AsyncSession, service: ManagedService) -> Job | None:
    jobs = await job_crud.for_subject(session, service.id, limit=1)
    return jobs[0] if jobs else None


def _public(service: ManagedService, job: Job | None) -> ServicePublic:
    return ServicePublic(
        id=service.id,
        template_key=service.template_key,
        title=_title_of(service.template_key),
        # A column is a string, and these are the only values written to
        # it: every write goes through this package.
        state=cast(ServiceState, service.state),
        container_name=service.container_name,
        published_port=service.published_port,
        created_at=service.created_at,
        job=job_public(job) if job is not None else None,
    )


def _title_of(template_key: str) -> str:
    """What this kind of service is called, or the key if it is no longer one.

    A template can be taken out of the code while a service made from it is
    still running, and a screen still has to name it.
    """
    try:
        return templates.template_for(template_key).title
    except UnknownServiceTemplate:
        return template_key
