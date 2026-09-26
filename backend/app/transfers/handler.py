"""Carrying out a paste that moves bytes, as an owned job (D168).

The kind does the work and writes each item's outcome into the payload; this
handler finds both connections again as their owner sees them now, gives the
kind threads of its own and writes down what it reports.
"""

import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import ClassVar, Protocol

from anyio import CapacityLimiter
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters import registry
from app.adapters.cache import DataCache
from app.adapters.protocol import AdapterError, DataAdapter
from app.adapters.registry import UnknownAdapterType
from app.adapters.resources import Pooling, ResourceStore
from app.connectors import crud as connector_crud
from app.connectors.access import context_for
from app.connectors.paste.kinds import PastesAsJob
from app.connectors.paste.registry import kind_named
from app.connectors.paste.transfer import Transfer, TransferStopped, in_worker
from app.connectors.service import build_adapter, merge_options
from app.connectors.tables import tables_of
from app.core.access import Access, at_least
from app.core.db import async_session_maker
from app.jobs.models import TERMINAL, Job, JobKind
from app.jobs.runner import JobFailed, JobHandler, Progress
from app.users.models import User

KIND: JobKind = "paste.transfer"

WAITING = "waiting for a free transfer slot"
CHECKING = "checking both connections"
TRANSFERRING = "transferring"
# A move, once everything is copied (D169).
REMOVING = "removing the sources"

# Transfers carried out at once across the server. Each has worker threads of
# its own: a copy of gigabytes holding a thread of the shared pool for twenty
# minutes would take it from every other blocking call (D168).
SLOTS = 8
# How often the payload reaches the row while it runs; a Stop and the end go
# at once. Ten thousand files written one by one would be gigabytes (D169).
PROGRESS_SECONDS = 1.0

NOTHING = "nothing was transferred"


class RunTransfer:
    kind: ClassVar[JobKind] = KIND
    steps: ClassVar[tuple[str, ...]] = (WAITING, CHECKING, TRANSFERRING, REMOVING)

    def __init__(self, cache: DataCache, resources: ResourceStore | None = None) -> None:
        self._cache = cache
        self._resources = resources
        # Made on first use, by the loop that runs the jobs: both belong to it.
        self._slots: asyncio.Semaphore | None = None
        self._threads: CapacityLimiter | None = None

    async def carry_out(self, job: Job, progress: Progress) -> str:
        transfer = _loaded(job)
        kind = _kind(transfer)
        keeper = _OwnJob(job, transfer, progress)
        async with self.slot(keeper) as threads:
            await progress.reached(CHECKING)
            source, destination = await self._ends(job, transfer, kind)
            stopped = await self.transferred(kind, source, destination, transfer, keeper, threads)
        message = kind.told(transfer, stopped)
        if stopped is not None or any(item.outcome != "done" for item in transfer.items):
            raise JobFailed(message)
        return message

    @asynccontextmanager
    async def slot(self, keeper: Keeper) -> AsyncIterator[CapacityLimiter]:
        """One of the server's transfer slots, and the threads of the slots."""
        slots, threads = self._pools()
        if slots.locked():
            await keeper.waiting()
        async with slots:
            yield threads

    async def transferred(
        self,
        kind: PastesAsJob,
        source: DataAdapter,
        destination: DataAdapter,
        transfer: Transfer,
        keeper: Keeper,
        threads: CapacityLimiter,
    ) -> str | None:
        """Carry a planned transfer out inside a slot; what stopped it, if anything.

        A job of its own and a step of a pipeline's run (D177) both come
        through here, so a transfer moves, reports and stops the same way.
        """
        touched = (transfer.destination_connector_id,) + (
            (transfer.source_connector_id,) if kind.changes_source else ()
        )
        report = _Report(keeper, transfer, threads, self._cache, touched)
        stopped: str | None = None
        try:
            await kind.transfer(source, destination, transfer, report)
        except asyncio.CancelledError:
            # The job's session may have been cut off mid-write; the runner
            # settles the row through a fresh one, and so does the keeper.
            await report.touch()
            await keeper.abandoned()
            raise
        except TransferStopped as stop:
            stopped = stop.message
        await report.touch()
        await report.written()
        return stopped

    def stopped_message(self, job: Job) -> str | None:
        try:
            transfer = _loaded(job)
            return _kind(transfer).told(transfer)
        except JobFailed:
            return None

    def _pools(self) -> tuple[asyncio.Semaphore, CapacityLimiter]:
        if self._slots is None or self._threads is None:
            self._slots = asyncio.Semaphore(SLOTS)
            self._threads = CapacityLimiter(SLOTS)
        return self._slots, self._threads

    async def _ends(
        self, job: Job, transfer: Transfer, kind: PastesAsJob
    ) -> tuple[DataAdapter, DataAdapter]:
        """Both connections, checked again: a grant may have gone since Paste."""
        async with async_session_maker() as session:
            owner = await session.get(User, job.owner_id)
            if owner is None:
                raise JobFailed(f"Its owner is no longer here; {NOTHING}")
            source = await self._opened(
                session,
                owner,
                transfer.source_connector_id,
                kind.source_requires,
                transfer.source_label,
            )
            destination = await self._opened(
                session,
                owner,
                transfer.destination_connector_id,
                kind.destination_requires,
                transfer.destination_label,
            )
        return source, destination

    async def _opened(
        self,
        session: AsyncSession,
        owner: User,
        connector_id: uuid.UUID,
        requires: Access,
        label: str,
    ) -> DataAdapter:
        found = await connector_crud.get_with_access(
            session, connector_id=connector_id, user=owner
        )
        if found is None:
            raise JobFailed(f"{label} is no longer available to you; {NOTHING}")
        connector, access = found
        if not at_least(access, requires):
            raise JobFailed(f"You no longer have {requires} access to {label}; {NOTHING}")
        if not connector.enabled:
            raise JobFailed(f"{label} was switched off; {NOTHING}")
        pooling = (
            Pooling(store=self._resources, connector_id=connector.id)
            if self._resources is not None
            else None
        )
        try:
            return build_adapter(
                registry.get(connector.adapter_type),
                merge_options(connector.config, connector.secrets),
                context_for(
                    connector.owner_id, pooling=pooling, tables=tables_of(connector)
                ),
            )
        except (UnknownAdapterType, ValueError, AdapterError):
            raise JobFailed(f"{label} can no longer be opened; {NOTHING}") from None


class Keeper(Protocol):
    """Where a transfer's payload is kept as it moves: the row of a job of its
    own, or a step of a pipeline's run (D177)."""

    async def waiting(self) -> None:
        """Every slot is taken; said before waiting for one."""
        ...

    async def kept(self, step: str) -> None:
        """Write the payload as it stands and tell its owner, at `step`."""
        ...

    async def abandoned(self) -> None:
        """Stopped: the payload as it stood, through a session of its own."""
        ...


class _OwnJob:
    """A transfer that is a job of its own: the payload is the job's parameters."""

    def __init__(self, job: Job, transfer: Transfer, progress: Progress) -> None:
        self._job = job
        self._transfer = transfer
        self._progress = progress

    async def waiting(self) -> None:
        await self._progress.reached(WAITING)

    async def kept(self, step: str) -> None:
        self._job.parameters = self._transfer.model_dump(mode="json")
        # The same step again: the row is written and a listening owner told.
        await self._progress.reached(step)

    async def abandoned(self) -> None:
        await _kept(self._job.id, self._transfer)


class _Report:
    """What a kind reports, handed to its keeper."""

    def __init__(
        self,
        keeper: Keeper,
        transfer: Transfer,
        threads: CapacityLimiter,
        cache: DataCache,
        touched: tuple[uuid.UUID, ...],
    ) -> None:
        self._keeper = keeper
        self._transfer = transfer
        self._threads = threads
        self._cache = cache
        self._touched = touched
        self._published = transfer.published
        self._last = 0.0
        self._step = TRANSFERRING

    async def in_thread[T](self, work: Callable[[], T]) -> T:
        return await in_worker(work, limiter=self._threads)

    async def progressed(self) -> None:
        if time.monotonic() - self._last >= PROGRESS_SECONDS:
            await self.written()

    async def removing(self) -> None:
        self._step = REMOVING
        await self.written()

    async def written(self) -> None:
        # A file that arrived is dropped from the read cache before anyone is
        # told, or the catalog that re-reads would be answered from before it.
        if self._transfer.published != self._published:
            self._published = self._transfer.published
            await self.touch()
        await self._keeper.kept(self._step)
        self._last = time.monotonic()

    async def touch(self) -> None:
        for connector_id in self._touched:
            await self._cache.invalidate_connector(connector_id)


def _loaded(job: Job) -> Transfer:
    try:
        return Transfer.model_validate(job.parameters)
    except ValidationError:
        raise JobFailed(f"This transfer could not be read; {NOTHING}") from None


def _kind(transfer: Transfer) -> PastesAsJob:
    kind = kind_named(transfer.kind)
    if not isinstance(kind, PastesAsJob):
        raise JobFailed(f"This server no longer transfers that; {NOTHING}")
    return kind


async def _kept(job_id: uuid.UUID, transfer: Transfer) -> None:
    """The outcomes as they stood when it was stopped."""
    async with async_session_maker() as session:
        job = await session.get(Job, job_id)
        if job is not None and job.state not in TERMINAL:
            job.parameters = transfer.model_dump(mode="json")
            session.add(job)
            await session.commit()


def handlers(transfers: RunTransfer) -> dict[str, JobHandler]:
    """One handler, made by the assembly: a pipeline's run (D177) shares its slots."""
    handler: JobHandler = transfers
    return {handler.kind: handler}
