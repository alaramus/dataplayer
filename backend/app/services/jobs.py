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
from app.adapters.credentials import KeyAccess
from app.adapters.registry import AdapterType
from app.connectors import crud as connector_crud
from app.connectors import ssh_keys
from app.connectors.service import split_options
from app.connectors.ssh_keys import OwnerKeys
from app.core import crypto
from app.core.translation import N_, say
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
from app.services.readiness import (
    ReadinessProbe,
    SampleDataFiller,
    install_sample_data,
    wait_until_ready,
)
from app.services.templates import (
    CREDENTIAL_SLOTS,
    KEY_ID,
    PASSWORD,
    PUBLIC_KEY,
    CredentialSlot,
    ServiceTemplate,
    UnknownServiceTemplate,
    template_for,
)
from app.users import storage


class _ServiceJob:
    """What every one of them needs: the engine, and the service in question."""

    def __init__(
        self,
        engine: ServiceEngine,
        probe: ReadinessProbe = wait_until_ready,
        filler: SampleDataFiller = install_sample_data,
    ) -> None:
        self._engine = engine
        self._probe = probe
        self._filler = filler

    async def _service(self, session: AsyncSession, job: Job) -> ManagedService:
        if job.subject_id is None:
            raise JobFailed(say("This job names no service"))
        service = await session.get(ManagedService, job.subject_id)
        if service is None:
            # The row went away while the job waited. Said as a failure rather
            # than as a crash: it is a thing that can happen, not a defect.
            raise JobFailed(say("That service is no longer here"))
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
        N_("clearing an earlier attempt"),
        N_("pulling the image"),
        N_("creating the container"),
        N_("starting the container"),
        N_("waiting for it to answer"),
        N_("putting sample data in it"),
        N_("saving the connection"),
    )

    async def carry_out(self, job: Job, progress: Progress) -> str:
        session = progress.session
        service = await self._service(session, job)
        template = _template_of(service)
        chosen = _chosen_of(service)
        if service.password_mode == "key":
            try:
                chosen[PUBLIC_KEY] = await _public_key_of(session, service)
            except JobFailed:
                await self._settle(session, service, "failed")
                raise
        plan = build_plan(
            template,
            service_id=service.id,
            owner_id=service.owner_id,
            placement=Placement(
                network=service.network,
                publish=service.publish,
                host_port=service.requested_port,
            ),
            chosen=chosen,
            protected=service.password_mode != "none",
            keyed=service.password_mode == "key",
        )
        # The owner's keys, for a server signed into with one of them (D154):
        # the job asks it whether it answers, and fills it, as the owner.
        keys = OwnerKeys(service.owner_id)
        try:
            await self._clear_earlier_attempt(service, progress)
            await progress.reached("pulling the image")
            await self._engine.pull(plan.container.image)
            await progress.reached("creating the container")
            await self._engine.create(plan.container)
            await progress.reached("starting the container")
            await self._start_it(service, plan.container.name)
            await self._record_published_port(session, service)
            await progress.reached("waiting for it to answer")
            # What it answered to, which is what the connector keeps: a server
            # that proves itself with a key is trusted by that key (D153).
            options = await self._probe(
                template.adapter_type,
                connector_options(plan, _endpoint_of(plan)),
                home_dir=storage.home_dir(service.owner_id),
                timeout_seconds=template.startup_timeout_seconds,
                keys=keys,
            )
            if options is None:
                raise JobFailed(
                    say("{service} started but did not answer in time", service=say(template.title))
                )
            await self._fill_it(service, template, options, progress, keys)
            await progress.reached(self.steps[-1])
            await self._deliver(session, service, plan, options)
        except JobFailed:
            await self._settle(session, service, "failed")
            raise
        await self._settle(session, service, "running")
        return say("{service} is ready", service=say(template.title))

    async def _deliver(
        self,
        session: AsyncSession,
        service: ManagedService,
        plan: ServicePlan,
        options: dict[str, str | int],
    ) -> None:
        """Hand the ready service to whoever it was made for: a connection.

        The last step, and the one a service made for another purpose replaces
        (D126). Changes to the row are committed by the settling that follows.
        """
        service.connector_id = await self._save_connector(
            session, service, plan, options
        )
        # Stamped rather than derived from `connector_id`, which goes null
        # again if somebody deletes the connection: this is what tells a
        # service that never got this far from one whose connection is gone
        # but whose database is still running (D84).
        service.connected_at = datetime.now(UTC)
        # The connector holds the password now, encrypted, so the copy that
        # carried it from the request to here has nothing left to do. One home
        # again (D4).
        service.chosen_password = None

    async def _start_it(self, service: ManagedService, container: str) -> None:
        """Start it, and name the likeliest reason when it will not.

        A container asked for a particular port on the host is the one that
        fails for a reason the person who asked can act on — something else is
        already listening there. The daemon says which port and which address,
        and its words do not cross (D82), so the sentence is this
        repository's own and names the number the request carried.
        """
        try:
            await self._engine.start(container)
        except JobFailed:
            if service.requested_port is None:
                raise
            raise JobFailed(
                say(
                    "It could not start. Port {port} may already be in use on this "
                    "machine; leave the port at 0 to have one picked.",
                    port=service.requested_port,
                )
            ) from None

    async def _record_published_port(
        self, session: AsyncSession, service: ManagedService
    ) -> None:
        """Ask what port the runtime gave it, and write that down.

        Asked rather than chosen: this application would have to bind a socket
        to find a free port and then race whoever took it in between, so the
        runtime picks and this reads back. A container that was not published
        answers with nothing, which is the same as not asking.
        """
        if not service.publish:
            return
        status = await self._engine.status(service.container_name)
        if status.published_port is None:
            return
        service.published_port = status.published_port
        session.add(service)
        await session.commit()

    async def _fill_it(
        self,
        service: ManagedService,
        template: ServiceTemplate,
        options: dict[str, str | int],
        progress: Progress,
        keys: KeyAccess,
    ) -> None:
        """Put something worth looking at into a server that has nothing.

        Only when it was asked for, and only where the source can: a type
        that does not implement the capability is skipped rather than refused,
        because the person asked for a database and this is the part of the
        answer that source cannot give (D2).

        The step is reached rather than announced, like the clearing one: a
        service started without it never shows a step nothing happened in.
        """
        if not service.sample_data:
            return
        await progress.reached("putting sample data in it")
        try:
            await self._filler(
                template.adapter_type,
                options,
                home_dir=storage.home_dir(service.owner_id),
                keys=keys,
            )
        except Exception as failure:
            # The database is up and usable; only the demonstration content
            # is missing. Said as a failure of the creation all the same,
            # because a person who asked for something to look at and got an
            # empty server would otherwise have to work out why themselves.
            raise JobFailed(say("The sample data could not be loaded")) from failure

    async def _clear_earlier_attempt(
        self, service: ManagedService, progress: Progress
    ) -> None:
        """Take away whatever a previous attempt left, before making it again.

        This is what makes creation something that can be tried again. A
        password this server made up is settled once per attempt and lives
        only in the connector the attempt would have saved, so a container
        left by a failed one has a password nobody knows — starting it again
        would produce a service nobody can open. The data in its volume is a
        database initialised with that unknown password, so it goes too. A
        password somebody typed survives on the row and would still open the
        old container; it is cleared anyway, because a half-initialised data
        directory is not something to carry into a second attempt.

        A first attempt finds nothing and skips the step, which is why the
        step is reached rather than announced up front.
        """
        status = await self._engine.status(service.container_name)
        if status.state == "missing":
            return
        await progress.reached("clearing an earlier attempt")
        await self._engine.remove(service.container_name, volume=service.volume_name)

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


def _chosen_of(service: ManagedService) -> dict[CredentialSlot, str]:
    """What the requester named, read back off the row.

    The route checked these against the template before writing them down, so
    a value here is one the template opened; `settle_credentials` checks again
    rather than trusting that, because a row outlives the code that wrote it.

    The password is the one that is not in the JSON column: it comes out of
    the encrypted one beside it, which is where a typed password waits for the
    job that will start the container with it.
    """
    by_slot: dict[CredentialSlot, str] = {}
    for slot in CREDENTIAL_SLOTS:
        value = service.chosen_credentials.get(slot)
        if value is not None:
            by_slot[slot] = value
    typed = _typed_password(service)
    if typed is not None:
        by_slot[PASSWORD] = typed
    return by_slot


async def _public_key_of(session: AsyncSession, service: ManagedService) -> str:
    """The public half of the key a server is to trust, read out of the store.

    Read when the server is started rather than when it was asked for, so a
    retry starts it with the key as it is now — and one deleted in between is
    a failure that says so rather than a server nobody can sign into (D154).
    """
    named = service.chosen_credentials.get(KEY_ID)
    key = (
        None
        if named is None
        else await ssh_keys.get_own(session, uuid.UUID(named), service.owner_id)
    )
    if key is None:
        raise JobFailed(
            say(
                "The SSH key this server was to be signed into with is gone; "
                "start it again with another"
            )
        )
    return key.public_key


def _typed_password(service: ManagedService) -> str | None:
    """The password somebody typed, if this service was started with one.

    Under the connector key rather than a key of its own: it is a connector
    secret that has not reached its connector yet, and a second key would be a
    second thing to rotate (D4).
    """
    if service.password_mode != "chosen" or service.chosen_password is None:
        return None
    return crypto.decrypt(service.chosen_password, purpose="connector").decode()


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
    steps: ClassVar[tuple[str, ...]] = (N_("starting the container"),)

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
        return say("{service} is running", service=say(_template_of(service).title))


class StopService(_ServiceJob):
    kind: ClassVar[JobKind] = "service.stop"
    steps: ClassVar[tuple[str, ...]] = (N_("stopping the container"),)

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
        return say("{service} is stopped", service=say(_template_of(service).title))


class RestartService(_ServiceJob):
    kind: ClassVar[JobKind] = "service.restart"
    steps: ClassVar[tuple[str, ...]] = (N_("restarting the container"),)

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
        return say("{service} was restarted", service=say(_template_of(service).title))


class DeleteService(_ServiceJob):
    """Take the container away, and its data with it.

    Deleting a service is destructive and is meant to be: the volume was made
    for this service and belongs to nothing else. What happens to the
    connection it became is decided where connectors are, by the route that
    accepted this job: a connector is a row of this application, and taking it
    away is not minutes of work to watch.

    The row goes only once the engine has said the container is gone, so a
    failed removal leaves something a person can see and try again.
    """

    kind: ClassVar[JobKind] = "service.delete"
    steps: ClassVar[tuple[str, ...]] = (
        N_("stopping the container"),
        N_("removing the container and its data"),
    )

    async def carry_out(self, job: Job, progress: Progress) -> str:
        session = progress.session
        service = await self._service(session, job)
        title = say(_template_of(service).title)
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
        return say("{service} was removed", service=title)


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
            say("This service was made from something this server no longer offers")
        ) from None


def handlers(
    engine: ServiceEngine,
    probe: ReadinessProbe = wait_until_ready,
    filler: SampleDataFiller = install_sample_data,
) -> dict[str, JobHandler]:
    """One handler per kind, built with what this application has.

    Assembly in one place: the runner is handed its handlers rather than
    reaching for a registry, so what a job of some kind does is decided where
    the application is put together — and a test can put together the same
    handlers with a runtime and a source that are not there.
    """
    made: tuple[JobHandler, ...] = (
        CreateService(engine, probe, filler),
        StartService(engine, probe, filler),
        StopService(engine, probe, filler),
        RestartService(engine, probe, filler),
        DeleteService(engine, probe, filler),
    )
    return {handler.kind: handler for handler in made}
