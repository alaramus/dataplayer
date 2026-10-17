"""Copying a source out, and putting it back, as jobs the server owns.

Neither is a request that waits: a dump of anything real is minutes, and a
task nobody holds with a boolean in a process is lost on a restart (D81). So
both are jobs, with the same
durable state, the same named steps and the same socket.

Where a backup goes is deliberately not a new place: it is a file in the
owner's personal storage, which they already list, download, rename and delete
through the file source. A backup that needed a table of its own would be a
second file system with a worse browser (D87).
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import ClassVar

from anyio import to_thread
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters import registry
from app.adapters.protocol import BackupProgram, SupportsBackup
from app.connectors.access import context_for
from app.connectors.models import Connector
from app.connectors.service import build_adapter, merge_options
from app.core.config import settings
from app.core.translation import N_, say
from app.jobs.models import Job, JobKind
from app.jobs.runner import JobFailed, JobHandler, Progress
from app.services.engine import ServiceEngine
from app.services.plan import OWNER_LABEL, TOOL_LABEL
from app.services.restore_files import snapshot
from app.services.tools import Mount, ToolResult, ToolRun
from app.users import storage

# Where in a person's storage backups land. One folder, named for what is in
# it, because a person looking for last week's dump should not have to
# remember what they called it.
BACKUP_FOLDER = "backups"

# What the file is called. The connection's name and the moment, which is what
# a person would have written themselves.
TIMESTAMP_FORMAT = "%Y-%m-%d-%H%M%S"

# Where the storage volume is mounted inside the program's container. The same
# path this application uses, so a file written there is at the path the file
# source will list it under.
STORAGE_MOUNT = "/data/users"


class BackupUnavailable(JobFailed):
    """This server cannot run a backup, and the reason is not the source's."""


def storage_volume_reason() -> str | None:
    """Why backups are not offered here, or nothing when they are.

    A program that writes into somebody's storage needs that storage to be a
    named volume it can mount. A deployment that keeps it somewhere else has
    not said where, and a backup written into a container that is then thrown
    away is worse than a refusal.
    """
    if not settings.SERVICE_STORAGE_VOLUME:
        return say("This server has nowhere to write a backup")
    return None


def backup_filename(connector_name: str, when: datetime) -> str:
    """A name a person recognises, made of what they already know.

    Everything but letters, digits and a few separators is replaced: this
    becomes a file name, and a connection may be called anything at all.
    """
    safe = "".join(
        character if character.isalnum() or character in "-_" else "-"
        for character in connector_name
    ).strip("-")
    stamp = when.strftime(TIMESTAMP_FORMAT)
    return f"{safe or 'backup'}-{stamp}.dump"


def backup_source(connector: Connector) -> SupportsBackup:
    options = merge_options(connector.config, connector.secrets)
    adapter = build_adapter(
        registry.get(connector.adapter_type),
        options,
        context_for(connector.owner_id),
    )
    if not isinstance(adapter, SupportsBackup):
        raise ValueError(say("This kind of connection cannot be backed up"))
    return adapter


class _BackupJob:
    """What both of them need: the engine, and the connection in question."""

    def __init__(self, engine: ServiceEngine) -> None:
        self._engine = engine

    async def _connector(self, session: AsyncSession, job: Job) -> Connector:
        if job.subject_id is None:
            raise JobFailed(say("This job names no connection"))
        connector = await session.get(Connector, job.subject_id)
        if connector is None:
            raise JobFailed(say("That connection is no longer here"))
        await session.refresh(connector)
        if connector.owner_id != job.owner_id:
            raise JobFailed(say("This connection no longer belongs to the job owner"))
        if not connector.enabled:
            raise JobFailed(say("This connection is disabled"))
        return connector

    def _source(self, connector: Connector) -> SupportsBackup:
        """The adapter, if it is one that can be copied out.

        Checked here rather than assumed: a source that cannot say what
        program would dump it does not implement the capability, and the
        answer is a refusal rather than a guess (D2d).
        """
        try:
            return backup_source(connector)
        except ValueError as exc:
            raise JobFailed(str(exc)) from None

    async def _run(
        self,
        program: BackupProgram,
        *,
        owner_id: uuid.UUID,
        what: str,
        writes: bool,
        inventory: bool = False,
    ) -> ToolResult:
        """Run the program the source named, in a container of its own."""
        reason = storage_volume_reason()
        if reason is not None:
            raise BackupUnavailable(reason)
        run = ToolRun(
            name=f"dataplayer-{what}-{uuid.uuid4().hex[:12]}",
            image=program.image,
            argv=program.argv,
            environment=program.environment,
            mounts=(
                Mount(
                    volume=settings.SERVICE_STORAGE_VOLUME,
                    path=STORAGE_MOUNT,
                    # A restore reads the dump and writes to the database; it
                    # has no business writing to somebody's storage.
                    read_only=not writes,
                ),
            ),
            network=settings.SERVICE_NETWORK or None,
            labels={TOOL_LABEL: what, OWNER_LABEL: str(owner_id)},
            full_output=inventory,
            timeout_seconds=30.0 if inventory else 3600.0,
        )
        return await self._engine.run_once(run)


class BackUpConnector(_BackupJob):
    """Copy a source out into a file of its owner's own storage."""

    kind: ClassVar[JobKind] = "backup.create"
    steps: ClassVar[tuple[str, ...]] = (
        N_("asking the source what would copy it"),
        N_("fetching the tool"),
        N_("copying the database out"),
    )

    async def carry_out(self, job: Job, progress: Progress) -> str:
        session = progress.session
        connector = await self._connector(session, job)
        await progress.reached("asking the source what would copy it")
        source = self._source(connector)
        home = storage.home_dir(connector.owner_id)
        folder = home / BACKUP_FOLDER
        await to_thread.run_sync(_make_folder, folder)
        filename = backup_filename(connector.name, datetime.now(UTC))
        inside = PurePosixPath(STORAGE_MOUNT) / str(connector.owner_id)
        try:
            program = await source.backup_program(
                into=str(inside / BACKUP_FOLDER / filename)
            )
        except ValueError as exc:
            raise JobFailed(str(exc)) from None
        await progress.reached("fetching the tool")
        await self._engine.pull(program.image)
        source = self._source(await self._connector(session, job))
        try:
            current = await source.backup_program(into=str(inside / BACKUP_FOLDER / filename))
        except ValueError as exc:
            raise JobFailed(str(exc)) from None
        if current != program:
            raise JobFailed(say("The connection changed while the backup tool was being prepared"))
        await progress.reached("copying the database out")
        result = await self._run(
            program, owner_id=connector.owner_id, what="backup", writes=True
        )
        if not result.ok:
            raise JobFailed(_why(result, say("The database could not be copied out")))
        written = folder / filename
        if not await to_thread.run_sync(written.exists):
            raise JobFailed(say("The program finished but wrote nothing"))
        return say("{file} written to {folder}", file=filename, folder=BACKUP_FOLDER)

class RestoreConnector(_BackupJob):
    """Put a backup back into a source, over what is there.

    Destructive in a way nothing else in this application is: `pg_restore`
    drops every object in the dump from the target before writing it again.
    The route that starts this insists on being told so in as many words, and
    this handler does not check again — a job carries out what was decided,
    and deciding twice is how one of the two decisions comes to be wrong.
    """

    kind: ClassVar[JobKind] = "backup.restore"
    steps: ClassVar[tuple[str, ...]] = (
        N_("asking the source what would restore it"),
        N_("fetching the tool"),
        N_("inspecting the backup archive"),
        N_("writing the database back"),
    )

    async def carry_out(self, job: Job, progress: Progress) -> str:
        session = progress.session
        connector = await self._connector(session, job)
        await progress.reached("asking the source what would restore it")
        source = self._source(connector)
        name = _restore_filename(job)
        staged = await to_thread.run_sync(snapshot, connector.owner_id, name)
        try:
            return await self._restore(job, progress, connector, source, name, staged)
        finally:
            await to_thread.run_sync(staged.unlink, True)

    async def _restore(
        self, job: Job, progress: Progress, connector: Connector,
        source: SupportsBackup, name: str, staged: Path,
    ) -> str:
        archive = str(PurePosixPath(STORAGE_MOUNT) / staged.name)
        try:
            program = await source.restore_program(from_file=archive)
            inspection = await source.restore_inventory_program(from_file=archive)
        except ValueError as exc:
            raise JobFailed(str(exc)) from None
        if inspection.image != program.image:
            raise JobFailed(say("The connection changed while the archive tools were being prepared"))
        await progress.reached("fetching the tool")
        await self._engine.pull(program.image)
        await progress.reached("inspecting the backup archive")
        inventory = await self._run(
            inspection, owner_id=connector.owner_id, what="restore-inspection",
            writes=False, inventory=True,
        )
        if not inventory.ok or inventory.truncated:
            raise JobFailed(say("The backup inventory could not be read completely"))
        try:
            source.validate_restore_inventory(inventory.output)
        except ValueError as exc:
            raise JobFailed(str(exc)) from None
        source = self._source(await self._connector(progress.session, job))
        try:
            current = await source.restore_program(from_file=archive)
        except ValueError as exc:
            raise JobFailed(str(exc)) from None
        if current != program:
            raise JobFailed(say("The connection changed while the restore tool was being prepared"))
        await progress.reached("writing the database back")
        result = await self._run(
            program, owner_id=connector.owner_id, what="restore", writes=False
        )
        if not result.ok:
            raise JobFailed(_why(result, say("The backup could not be written back")))
        return say("{name} was restored from {file}", name=connector.name, file=name)


def _make_folder(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)


def _restore_filename(job: Job) -> str:
    """Which backup this job is about, out of what it was asked for."""
    name = (job.parameters or {}).get("filename")
    if not isinstance(name, str) or not name:
        raise JobFailed(say("This job does not say which backup to write back"))
    return name


def _why(result: ToolResult, fallback: str) -> str:
    """The program's own last word, when it said one.

    A failed `pg_dump` says why in one line, and that line is the difference
    between "it did not work" and something a person can act on. It is the
    program's words about a database rather than the daemon's about the
    machine, which is what makes it safe to pass on.
    """
    for line in reversed(list(result.output)):
        if line.strip():
            return line.strip()[:400]
    return fallback


def handlers(engine: ServiceEngine) -> dict[str, JobHandler]:
    """One handler per kind, built with the engine the application has."""
    made: tuple[JobHandler, ...] = (
        BackUpConnector(engine),
        RestoreConnector(engine),
    )
    return {handler.kind: handler for handler in made}


