"""Carrying out an admitted source operation, one target at a time (D123).

The job row holds the fixed targets and their outcomes; the source carries out
a unit and says what it did. The connection and the owner's access are read
again from a fresh session before every unit after the first: rows this job's
own session loaded are not re-read by it.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable
from typing import ClassVar

from pydantic import ValidationError

from app.adapters import registry
from app.adapters.actions import ActionRefused, SupportsActions, UnknownAction
from app.adapters.cache import DataCache
from app.adapters.operations import ProducesJob
from app.adapters.protocol import AdapterError, DataAdapter
from app.adapters.registry import UnknownAdapterType
from app.connectors import crud as connector_crud
from app.connectors.access import context_for
from app.connectors.models import Connector
from app.connectors.service import build_adapter, merge_options
from app.core.access import at_least
from app.core.db import async_session_maker
from app.jobs.models import Job, JobKind
from app.jobs.runner import JobFailed, JobHandler, Progress
from app.source_operations.models import SourceOperation, TargetRecord
from app.users.models import User

logger = logging.getLogger(__name__)

KIND: JobKind = "source.operation"
# What a source operation may not run beside on the same connection: a second
# one might touch the same targets, and a restore rewrites them underneath.
EXCLUSIVE_WITH: tuple[JobKind, ...] = ("source.operation", "backup.restore")

VALIDATING = "checking the connection and the reviewed plan"
EXECUTING = "carrying out the reviewed plan"
RECONCILING = "reading the outcome back from the source"

AdapterBuilder = Callable[[Connector], DataAdapter]


def revision_of(connector: Connector) -> str | None:
    """The server-maintained revision a job is bound to; every edit changes it."""
    return connector.updated_at.isoformat() if connector.updated_at is not None else None


def live_adapter(connector: Connector) -> DataAdapter:
    return build_adapter(
        registry.get(connector.adapter_type),
        merge_options(connector.config, connector.secrets),
        context_for(connector.owner_id),
    )


class RunSourceOperation:
    kind: ClassVar[JobKind] = KIND
    steps: ClassVar[tuple[str, ...]] = (VALIDATING, EXECUTING, RECONCILING)

    def __init__(self, cache: DataCache, build: AdapterBuilder = live_adapter) -> None:
        self._cache = cache
        self._build = build

    async def carry_out(self, job: Job, progress: Progress) -> str:
        operation = _loaded(job)
        await progress.reached(VALIDATING)
        refusal = await _standing(job, operation)
        if refusal is not None:
            raise JobFailed(f"{refusal}; nothing was changed")
        action = await self._action(job, operation)
        revoked: str | None = None
        failed = False
        for index, record in enumerate(operation.targets):
            if index > 0 and (revoked := await _standing(job, operation)) is not None:
                break
            if not await self._unit(job, progress, operation, action, record):
                failed = True
                break
        # A revoked owner is not read for any more, even to report.
        if revoked is None:
            await progress.reached(RECONCILING)
            await self._observe(operation, action)
        await _save(progress, job, operation)
        if revoked is not None:
            raise JobFailed(operation.told(
                f"{revoked}; it stopped before the next target, and what was done stays done",
            ))
        if failed:
            raise JobFailed(operation.told("It stopped at the first target that did not complete"))
        return operation.told()

    async def _action(self, job: Job, operation: SourceOperation) -> ProducesJob:
        async with async_session_maker() as session:
            connector = await session.get(Connector, _connector_id(job))
        if connector is None:
            raise JobFailed("That connection is no longer here; nothing was changed")
        try:
            adapter = self._build(connector)
        except (UnknownAdapterType, ValueError):
            raise JobFailed("This connection can no longer be opened; nothing was changed") from None
        if not isinstance(adapter, SupportsActions):
            raise JobFailed("This connection no longer takes actions; nothing was changed")
        try:
            action = adapter.action(operation.action)
        except UnknownAction:
            raise JobFailed("This connection no longer offers that action; nothing was changed") from None
        if not isinstance(action, ProducesJob):
            raise JobFailed("That action is no longer carried out as a job; nothing was changed")
        return action

    async def _unit(
        self, job: Job, progress: Progress, operation: SourceOperation, action: ProducesJob,
        record: TargetRecord,
    ) -> bool:
        """Carry out one target; False when the job must stop at it."""
        record.outcome = "running"
        await _announce(progress, job, operation)
        try:
            record.outcome = await action.run_unit(
                operation.node_id, operation.params, operation.unit_fingerprint, record.target,
            )
        except ActionRefused as refusal:
            record.outcome, record.message = "refused", refusal.message
        except AdapterError as failure:
            record.outcome, record.message = "unknown", failure.message
        except asyncio.CancelledError:
            await self._after_cancellation(job, progress, operation, action, record)
            raise
        except Exception:
            record.outcome, record.message = "unknown", "This target's outcome is unknown"
            await self._settle(job, progress, operation)
            raise
        await self._settle(job, progress, operation)
        return record.outcome in {"completed", "already"}

    async def _settle(self, job: Job, progress: Progress, operation: SourceOperation) -> None:
        # Invalidated after every unit whatever its outcome, and before the
        # announcement that makes a client read again.
        await self._cache.invalidate_connector(_connector_id(job))
        await _announce(progress, job, operation)

    async def _after_cancellation(
        self, job: Job, progress: Progress, operation: SourceOperation, action: ProducesJob,
        record: TargetRecord,
    ) -> None:
        """Stopped mid-unit, after the driver cancelled and rolled back: read what the source holds."""
        record.outcome = "unknown"
        record.message = "Stopped while this target was in progress; its outcome is unknown"
        try:
            async with asyncio.timeout(5):
                observed = await action.observe(operation.node_id, operation.params, [record.target])
        except Exception:
            logger.exception("Reading back a cancelled target failed")
            observed = []
        if len(observed) == 1:
            record.observed = observed[0]
            if observed[0] == "unchanged":
                record.outcome = "rolled_back"
                record.message = "Stopped while this target was in progress; it was rolled back"
            elif observed[0] == "as_requested":
                record.outcome, record.message = "completed", None
        await self._cache.invalidate_connector(_connector_id(job))
        await _save(progress, job, operation)

    async def _observe(self, operation: SourceOperation, action: ProducesJob) -> None:
        """Read every target back once; a failed read leaves them unobserved."""
        try:
            async with asyncio.timeout(10):
                observed = await action.observe(
                    operation.node_id, operation.params, [record.target for record in operation.targets],
                )
        except Exception:
            logger.exception("Reading back a source operation failed")
            return
        if len(observed) != len(operation.targets):
            return
        for record, state in zip(operation.targets, observed, strict=True):
            record.observed = state


def _loaded(job: Job) -> SourceOperation:
    try:
        return SourceOperation.model_validate(job.parameters)
    except ValidationError:
        raise JobFailed("This job's plan could not be read; nothing was changed") from None


def _connector_id(job: Job) -> uuid.UUID:
    if job.subject_id is None:
        raise JobFailed("This job names no connection")
    return job.subject_id


async def _standing(job: Job, operation: SourceOperation) -> str | None:
    """Why this job may no longer act on the connection for its owner, or nothing."""
    async with async_session_maker() as session:
        connector = await session.get(Connector, _connector_id(job))
        owner = await session.get(User, job.owner_id)
        if connector is None or owner is None:
            return "The connection is no longer here"
        if not connector.enabled:
            return "The connection was disabled"
        if revision_of(connector) != operation.connector_revision:
            return "The connection was edited after this job was accepted"
        found = await connector_crud.get_with_access(session, connector_id=connector.id, user=owner)
        if found is None or not at_least(found[1], operation.requires):
            return "Access to the connection changed"
    return None


async def _save(progress: Progress, job: Job, operation: SourceOperation) -> None:
    job.parameters = operation.model_dump(mode="json")
    progress.session.add(job)
    await progress.session.commit()


async def _announce(progress: Progress, job: Job, operation: SourceOperation) -> None:
    # The same step again: the row is written and a listening owner is told,
    # so each target's outcome reaches the screen as it lands.
    job.parameters = operation.model_dump(mode="json")
    await progress.reached(EXECUTING)


def handlers(cache: DataCache) -> dict[str, JobHandler]:
    handler: JobHandler = RunSourceOperation(cache)
    return {handler.kind: handler}
