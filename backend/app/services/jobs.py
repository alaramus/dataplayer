"""The five things that can happen to a service, each as one owned job.

One handler per kind rather than one function with five branches: a kind of
work is a thing with its own steps, and the steps are what a person watching
sees. Every handler here reads the service row it is about, asks the engine,
and writes down what the service has become — in that order, so a job that
dies between the two leaves a service whose state is the last thing anybody
actually observed.
"""

import uuid
from contextlib import suppress
from datetime import UTC, datetime
from typing import ClassVar

from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters import registry
from app.adapters.registry import AdapterType
from app.connectors import crud as connector_crud
from app.connectors.service import split_options
from app.jobs.models import Job, JobKind
from app.jobs.runner import JobFailed, JobHandler, Progress
from app.services.engine import ServiceEngine
from app.services.models import ManagedService
from app.services.plan import (
    Endpoint,
    Placement,
    ServicePlan,
    build_plan,
    connector_options,
)
from app.services.readiness import ReadinessProbe, wait_until_ready
from app.services.templates import (
    ServiceTemplate,
    UnknownServiceTemplate,
    template_for,
)
from app.users import storage


class _ServiceJob:
    """What every one of them needs: the engine, and the service in question."""

    def __init__(
        self, engine: ServiceEngine, probe: ReadinessProbe = wait_until_ready
    ) -> None:
        self._engine = engine
        self._probe = probe

    async def _service(self, session: AsyncSession, job: Job) -> ManagedService:
        if job.subject_id is None:
            raise JobFailed("This job names no service")
        service = await session.get(ManagedService, job.subject_id)
        if service is None:
            # The row went away while the job waited. Said as a failure rather
            # than as a crash: it is a thing that can happen, not a defect.
            raise JobFailed("That service is no longer here")
        return service

    async def _settle(
        self, session: AsyncSession, service: ManagedService, state: str
    ) -> None:
        service.state = state
        service.updated_at = datetime.now(UTC)
        session.add(service)
        await session.commit()


class CreateService(_ServiceJob):
    """Make the container, start it, wait for it, and save the connection.

    The image is pulled as a step of its own because it is the slow one: a
    hundreds-of-megabytes download is exactly what no HTTP request may wait
    for, and it is what a person watching wants named. Waiting for the service
    to answer is a step for the same reason — a database initialises its data
    directory on first start, and the port answers before the server does.

    The connector is saved last and from the same plan the container was
    started with, so the credentials in it are the credentials the service
    has (D83). Nothing else in this application knows them: a creation that
    does not reach this step leaves a container nobody can use, which is why
    it is then taken away.
    """

    kind: ClassVar[JobKind] = "service.create"
    steps: ClassVar[tuple[str, ...]] = (
        "pulling the image",
        "creating the container",
        "starting the container",
        "waiting for it to answer",
        "saving the connection",
    )

    async def carry_out(self, job: Job, progress: Progress) -> str:
        session = progress.session
        service = await self._service(session, job)
        template = _template_of(service)
        plan = build_plan(
            template,
            service_id=service.id,
            owner_id=service.owner_id,
            placement=Placement(
                network=service.network, published_port=service.published_port
            ),
        )
        try:
            await progress.reached("pulling the image")
            await self._engine.pull(plan.container.image)
            await progress.reached("creating the container")
            await self._engine.create(plan.container)
            await progress.reached("starting the container")
            await self._engine.start(plan.container.name)
            await progress.reached("waiting for it to answer")
            options = connector_options(plan, _endpoint_of(plan))
            if not await self._probe(
                template.adapter_type,
                options,
                home_dir=storage.home_dir(service.owner_id),
                timeout_seconds=template.startup_timeout_seconds,
            ):
                raise JobFailed(
                    f"{template.title} started but did not answer in time"
                )
            await progress.reached("saving the connection")
            connector_id = await self._save_connector(session, service, plan, options)
        except JobFailed:
            await self._settle(session, service, "failed")
            raise
        service.connector_id = connector_id
        await self._settle(session, service, "running")
        return f"{template.title} is ready"

    async def _save_connector(
        self,
        session: AsyncSession,
        service: ManagedService,
        plan: ServicePlan,
        options: dict[str, str | int],
    ) -> uuid.UUID:
        """Write the connection down, through the ordinary connector path.

        The same validation, the same split into configuration and encrypted
        secrets (D4), the same table. A connector made from a service is a
        connector, and nothing downstream can tell where it came from — which
        is what stops this becoming a second kind of connection with rules of
        its own.
        """
        kind: AdapterType = registry.get(plan.template.adapter_type)
        config, secrets = split_options(kind, dict(options))
        connector = await connector_crud.create(
            session,
            name=service.connector_name,
            adapter_type=kind.name,
            config=config,
            secrets=secrets,
            owner_id=service.owner_id,
        )
        return connector.id


def _endpoint_of(plan: ServicePlan) -> Endpoint:
    """Where the service will be reached: its container name, on the network.

    Not a published port on the host: what has to reach it is this server, and
    a name on a shared network is how one container reaches another. Whether a
    person's own machine can reach it too is a separate question, and one the
    threat model has to answer before it is offered.
    """
    return Endpoint(host=plan.container.name, port=plan.template.container_port)


class StartService(_ServiceJob):
    kind: ClassVar[JobKind] = "service.start"
    steps: ClassVar[tuple[str, ...]] = ("starting the container",)

    async def carry_out(self, job: Job, progress: Progress) -> str:
        session = progress.session
        service = await self._service(session, job)
        await progress.reached("starting the container")
        try:
            await self._engine.start(service.container_name)
        except JobFailed:
            await self._settle(session, service, "failed")
            raise
        await self._settle(session, service, "running")
        return f"{_template_of(service).title} is running"


class StopService(_ServiceJob):
    kind: ClassVar[JobKind] = "service.stop"
    steps: ClassVar[tuple[str, ...]] = ("stopping the container",)

    async def carry_out(self, job: Job, progress: Progress) -> str:
        session = progress.session
        service = await self._service(session, job)
        await progress.reached("stopping the container")
        try:
            await self._engine.stop(service.container_name)
        except JobFailed:
            await self._settle(session, service, "failed")
            raise
        await self._settle(session, service, "stopped")
        return f"{_template_of(service).title} is stopped"


class RestartService(_ServiceJob):
    kind: ClassVar[JobKind] = "service.restart"
    steps: ClassVar[tuple[str, ...]] = ("restarting the container",)

    async def carry_out(self, job: Job, progress: Progress) -> str:
        session = progress.session
        service = await self._service(session, job)
        await progress.reached("restarting the container")
        try:
            await self._engine.restart(service.container_name)
        except JobFailed:
            await self._settle(session, service, "failed")
            raise
        await self._settle(session, service, "running")
        return f"{_template_of(service).title} was restarted"


class DeleteService(_ServiceJob):
    """Take the container away, and its data with it.

    Deleting a service is destructive and is meant to be: the volume was made
    for this service and belongs to nothing else. What must not happen — a
    connector being deleted quietly taking a volume with it — is a different
    question, and it is answered where connectors are.

    The row goes only once the engine has said the container is gone, so a
    failed removal leaves something a person can see and try again.
    """

    kind: ClassVar[JobKind] = "service.delete"
    steps: ClassVar[tuple[str, ...]] = (
        "stopping the container",
        "removing the container and its data",
    )

    async def carry_out(self, job: Job, progress: Progress) -> str:
        session = progress.session
        service = await self._service(session, job)
        title = _template_of(service).title
        await progress.reached("stopping the container")
        # A container that will not stop may be one that is not running.
        # Removal is what decides, and it is asked next.
        with suppress(JobFailed):
            await self._engine.stop(service.container_name)
        await progress.reached("removing the container and its data")
        try:
            await self._engine.remove(
                service.container_name, volume=service.volume_name
            )
        except JobFailed:
            await self._settle(session, service, "failed")
            raise
        await session.delete(service)
        await session.commit()
        return f"{title} was removed"


def _template_of(service: ManagedService) -> ServiceTemplate:
    """The template a service was made from, or a refusal a person can read.

    A key that no longer names a template is possible — templates are code and
    code changes — and it is a state to report rather than an exception to let
    escape.
    """
    try:
        return template_for(service.template_key)
    except UnknownServiceTemplate:
        raise JobFailed(
            "This service was made from something this server no longer offers"
        ) from None


def handlers(
    engine: ServiceEngine, probe: ReadinessProbe = wait_until_ready
) -> dict[str, JobHandler]:
    """One handler per kind, built with what this application has.

    Assembly in one place: the runner is handed its handlers rather than
    reaching for a registry, so what a job of some kind does is decided where
    the application is put together — and a test can put together the same
    handlers with a runtime and a source that are not there.
    """
    made: tuple[JobHandler, ...] = (
        CreateService(engine, probe),
        StartService(engine, probe),
        StopService(engine, probe),
        RestartService(engine, probe),
        DeleteService(engine, probe),
    )
    return {handler.kind: handler for handler in made}
