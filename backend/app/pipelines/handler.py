"""Carrying out a pipeline's run: its links one after another (D177).

Each step is the Paste its link stands for, both ends opened again as the
owner stands now: rows are pasted here, and a transfer is carried out on the
transfers' own slots and threads, reporting as a transfer job does. The first
step that fails stops the run, and the steps after it are not run. A step
reading what an earlier one makes reads the node made in this run (D178).
"""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import ClassVar

from fastapi import HTTPException
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.cache import DataCache
from app.adapters.protocol import AdapterError, DataAdapter
from app.adapters.resources import ResourceStore
from app.connectors.access import adapter_for
from app.connectors.paste.kinds import PastesAsJob, PastesNow
from app.connectors.paste.registry import kind_named
from app.core.access import Access
from app.core.db import async_session_maker
from app.core.translation import N_, say
from app.jobs.models import TERMINAL, Job, JobKind
from app.jobs.runner import JobFailed, JobHandler, Progress
from app.pipelines.record import STEP_SAYS, RunRecord, RunStep, clipped
from app.pipelines.runs import KIND
from app.transfers.handler import WAITING, RunTransfer
from app.transfers.run import as_job, paste_now, planned
from app.users.models import User

RUNNING = N_("running its links")

# An end the owner can no longer open, by what the one door answered.
_REFUSED = {
    404: N_("{name} is gone, or no longer shared with you"),
    409: N_("{name} is switched off"),
}
_CANNOT_OPEN = N_("{name} can no longer be opened")
# The access is a word, so each level is a sentence of its own.
_LOST_ACCESS: dict[Access, str] = {
    "read": N_("You no longer have read access to {name}"),
    "write": N_("You no longer have write access to {name}"),
    "structure": N_("You no longer have structure access to {name}"),
    "own": N_("You no longer have own access to {name}"),
}


class _StepFailed(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _said(refused: HTTPException) -> str:
    detail = refused.detail
    if isinstance(detail, dict) and isinstance(detail.get("message"), str):
        return str(detail["message"])
    return say("The link could not run")


def _now() -> datetime:
    return datetime.now(UTC)


class RunPipeline:
    kind: ClassVar[JobKind] = KIND
    steps: ClassVar[tuple[str, ...]] = (RUNNING, WAITING)

    def __init__(
        self, cache: DataCache, resources: ResourceStore | None, transfers: RunTransfer
    ) -> None:
        self._cache = cache
        self._resources = resources
        # A transfer step takes one of the server's transfer slots, as a
        # transfer job does, so a run cannot move more at once than they may.
        self._transfers = transfers

    async def carry_out(self, job: Job, progress: Progress) -> str:
        record = _loaded(job)
        at = 0
        try:
            for at, step in enumerate(record.steps):
                unmade = _fed(record, step)
                if unmade is not None:
                    # Never what an earlier run left under that name.
                    step.outcome, step.finished_at = "not_run", _now()
                    step.message = clipped(
                        say("{link} made nothing in this run", link=unmade), STEP_SAYS
                    )
                    await _kept(job, record, progress, RUNNING)
                    continue
                step.outcome, step.started_at = "running", _now()
                await _kept(job, record, progress, RUNNING)
                try:
                    message = await self._carried(job, record, step, progress)
                except _StepFailed as failed:
                    step.outcome, step.finished_at = "failed", _now()
                    step.message = clipped(failed.message, STEP_SAYS)
                    record.not_run_after(at)
                    await _kept(job, record, progress, RUNNING)
                    raise JobFailed(record.failed_at(at)) from None
                step.outcome, step.finished_at = "done", _now()
                step.message = clipped(message, STEP_SAYS)
            await _kept(job, record, progress, RUNNING)
        except asyncio.CancelledError:
            step = record.steps[at]
            if step.outcome == "running":
                step.outcome, step.finished_at = "failed", _now()
                step.message = clipped(_stopped_words(step), STEP_SAYS)
            record.not_run_after(at)
            await _abandoned(job.id, record)
            raise
        return record.ran()

    def stopped_message(self, job: Job) -> str | None:
        try:
            return RunRecord.model_validate(job.parameters).stopped()
        except ValidationError:
            return None

    async def _carried(
        self, job: Job, record: RunRecord, step: RunStep, progress: Progress
    ) -> str:
        """Carry one step out; its sentence, or `_StepFailed` with why not."""
        kind = kind_named(step.paste.kind)
        async with async_session_maker() as session:
            owner = await session.get(User, job.owner_id)
            if owner is None:
                raise _StepFailed(say("Its owner is no longer here"))
            source = await self._end(
                session, owner, step.paste.source_connector_id, kind.source_requires,
                step.source_connection,
            )
            destination = await self._end(
                session, owner, step.destination_connector_id, kind.destination_requires,
                step.destination_connection,
            )
            if not kind.serves(source, destination):
                raise _StepFailed(
                    say("{kind} is not possible between these connections", kind=say(kind.title))
                )
            if isinstance(kind, PastesAsJob):
                try:
                    if await as_job(kind, source, step.paste):
                        step.transfer = await planned(
                            session, kind, source, destination, step.destination_connector_id,
                            step.paste,
                        )
                except HTTPException as refused:
                    raise _StepFailed(_said(refused)) from None
        if isinstance(kind, PastesAsJob) and step.transfer is not None:
            transfer = step.transfer
            keeper = _StepKeeper(job, record, progress)
            async with self._transfers.slot(keeper) as threads:
                await keeper.kept(RUNNING)
                stopped = await self._transfers.transferred(
                    kind, source, destination, transfer, keeper, threads
                )
            message = kind.told(transfer, stopped)
            if stopped is not None or any(item.outcome != "done" for item in transfer.items):
                raise _StepFailed(message)
            # One node on the clipboard, one item: what it arrived as.
            item = transfer.items[0]
            step.made, step.made_name = item.published_id, item.published_as or item.name
            return message
        if isinstance(kind, PastesNow):
            try:
                result = await paste_now(
                    self._cache, kind, source, destination, step.destination_connector_id, step.paste
                )
            except HTTPException as refused:
                raise _StepFailed(_said(refused)) from None
            if result.made_node_id is not None:
                step.made, step.made_name = result.made_node_id, result.name
            return result.message
        raise _StepFailed(say("{kind} cannot run", kind=say(kind.title)))

    async def _end(
        self,
        session: AsyncSession,
        owner: User,
        connector_id: uuid.UUID,
        requires: Access,
        name: str,
    ) -> DataAdapter:
        """One end, through the one door to a source, said by its name."""
        try:
            return await adapter_for(session, connector_id, owner, self._resources, requires=requires)
        except HTTPException as refused:
            if refused.status_code == 403:
                raise _StepFailed(say(_LOST_ACCESS[requires], name=name)) from None
            wording = _REFUSED.get(refused.status_code, _CANNOT_OPEN)
            raise _StepFailed(say(wording, name=name)) from None
        except (ValueError, AdapterError):
            raise _StepFailed(say(_CANNOT_OPEN, name=name)) from None


class _StepKeeper:
    """A transfer step's payload is kept in the run's record, on the job's row."""

    def __init__(self, job: Job, record: RunRecord, progress: Progress) -> None:
        self._job = job
        self._record = record
        self._progress = progress

    async def waiting(self) -> None:
        await _kept(self._job, self._record, self._progress, WAITING)

    async def kept(self, step: str) -> None:
        del step  # a run shows its own step, whatever the transfer's
        await _kept(self._job, self._record, self._progress, RUNNING)

    async def abandoned(self) -> None:
        # The run writes its record as it stopped, the step's outcome with it.
        return None


def _fed(record: RunRecord, step: RunStep) -> str | None:
    """Put in the nodes earlier steps made that this one reads or writes into;
    the title of a link that made nothing, if one did (D178)."""
    for maker_id, into in ((step.reads, False), (step.writes_into, True)):
        if maker_id is None:
            continue
        maker = record.step_of(maker_id)
        if maker is None or maker.made is None:
            return maker.title if maker is not None else say("The link it reads")
        update = (
            {"destination_node_id": maker.made, "target_node_id": maker.made}
            if into
            else {"source_node_ids": [maker.made]}
        )
        step.paste = step.paste.model_copy(update=update)
    return None


def _stopped_words(step: RunStep) -> str:
    if step.transfer is not None:
        kind = kind_named(step.transfer.kind)
        if isinstance(kind, PastesAsJob):
            return kind.told(step.transfer)
    return say("Stopped before it finished")


async def _kept(job: Job, record: RunRecord, progress: Progress, at: str) -> None:
    job.parameters = record.model_dump(mode="json")
    await progress.reached(at)


def _loaded(job: Job) -> RunRecord:
    try:
        return RunRecord.model_validate(job.parameters)
    except ValidationError:
        raise JobFailed(say("This run could not be read; nothing ran")) from None


async def _abandoned(job_id: uuid.UUID, record: RunRecord) -> None:
    """The record as it stood when stopped, through a session of its own: the
    job's may have been cut off mid-write."""
    async with async_session_maker() as session:
        job = await session.get(Job, job_id)
        if job is not None and job.state not in TERMINAL:
            job.parameters = record.model_dump(mode="json")
            session.add(job)
            await session.commit()


def handlers(
    cache: DataCache, resources: ResourceStore | None, transfers: RunTransfer
) -> dict[str, JobHandler]:
    handler: JobHandler = RunPipeline(cache, resources, transfers)
    return {handler.kind: handler}
