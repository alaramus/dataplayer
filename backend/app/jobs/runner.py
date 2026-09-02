"""Carrying out an accepted job, and picking up after a restart.

The request that accepted a job has answered long ago; everything here runs in
a task with a session of its own. Nothing waits for a pull, and nothing about
the outcome is kept in memory — a job's state is its row, so another process
can read it and a restart can end it honestly (D81).
"""

import asyncio
import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Protocol, cast, runtime_checkable

from fastapi import Depends, Request
from sqlmodel import col, select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import async_session_maker
from app.jobs.models import TERMINAL, Job, JobKind, JobState
from app.jobs.topic import JobEvent, announce
from app.realtime.topics import TopicSet

logger = logging.getLogger(__name__)


class JobFailed(Exception):
    """What a handler raises when the work cannot be done.

    Its message is shown to the owner, so it is the handler's own sentence
    about the situation and never a daemon's — an engine's error text names
    paths, sockets and image digests of the machine this runs on.
    """


@runtime_checkable
class JobHandler(Protocol):
    """What one kind of work is: its steps, and how to do them.

    A protocol rather than a base class, and one object per kind rather than a
    branch inside the runner: adding a kind of work is a new handler and a line
    of assembly, not an edit to the thing that runs everything.
    """

    # Read-only members, so a handler may declare them as class constants —
    # which is what they are. A protocol whose attributes are settable would
    # demand that every handler be able to change its own kind.
    @property
    def kind(self) -> JobKind: ...

    # The steps this kind of work goes through, in order, in the words a
    # person reads. Declared so that progress is a position in a list somebody
    # wrote rather than a number somebody made up.
    @property
    def steps(self) -> tuple[str, ...]: ...

    async def carry_out(self, job: Job, progress: Progress) -> str: ...


class Progress:
    """How a handler says where it has got to.

    Writes the step to the row before announcing it, so a client that arrives
    by polling and a client that arrives by socket are told the same thing.
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        job: Job,
        topics: TopicSet | None,
        steps: tuple[str, ...],
    ) -> None:
        # Public: the handler writes its own rows in the same session and in
        # the same transaction as the progress it reports, so a step that was
        # announced and a change that was not cannot come apart.
        self.session = session
        self._job = job
        self._topics = topics
        self._steps = steps

    async def reached(self, step: str) -> None:
        """Say which declared step is being done now.

        A step the handler did not declare is a mistake in the handler, and
        raising here is better than quietly showing a person a step that is
        not in the list they were promised.
        """
        if step not in self._steps:
            raise ValueError(f"{step!r} is not a step of {self._job.kind}")
        self._job.step = step
        self._job.step_index = self._steps.index(step) + 1
        self._job.step_count = len(self._steps)
        self.session.add(self._job)
        await self.session.commit()
        await self._announce()

    async def _announce(self) -> None:
        if self._topics is None:
            return
        await announce(self._topics, self._job.owner_id, _event(self._job))


def _event(job: Job) -> JobEvent:
    # The two columns are strings, and every value written to them comes from
    # the two closed sets above: nothing outside this package writes a job.
    return JobEvent(
        job_id=job.id,
        kind=cast(JobKind, job.kind),
        subject_id=job.subject_id,
        state=cast(JobState, job.state),
        step=job.step,
        step_index=job.step_index,
        step_count=job.step_count,
        message=job.message,
    )


@dataclass
class _Active:
    task: asyncio.Task[None]
    owner_id: uuid.UUID


class JobRunner:
    """The jobs this process is carrying out.

    Process-local, like the query runner and for the same reason: a task does
    not cross a process. What crosses is the row.
    """

    def __init__(self, handlers: Mapping[str, JobHandler]) -> None:
        self._handlers = dict(handlers)
        self._active: dict[uuid.UUID, _Active] = {}
        self._lock = asyncio.Lock()

    def handler_for(self, kind: JobKind) -> JobHandler:
        """The one object that knows how to do this kind of work.

        A missing handler is a programming error rather than a client's: the
        kinds are a closed set, and the assembly names one object for each.
        """
        try:
            return self._handlers[kind]
        except KeyError:
            raise RuntimeError(f"No handler for job kind: {kind}") from None

    def steps_of(self, kind: JobKind) -> tuple[str, ...]:
        return self.handler_for(kind).steps

    async def launch(self, job: Job, topics: TopicSet | None = None) -> None:
        """Start carrying out a job that has already been written down."""
        task = asyncio.create_task(self._carry_out(job.id, job.kind, topics))
        async with self._lock:
            self._active[job.id] = _Active(task=task, owner_id=job.owner_id)

    async def active_count(self, owner_id: uuid.UUID) -> int:
        async with self._lock:
            return sum(1 for job in self._active.values() if job.owner_id == owner_id)

    async def wait_for(self, job_id: uuid.UUID) -> None:
        """Wait for one job this process started. For tests and for shutdown."""
        async with self._lock:
            active = self._active.get(job_id)
        if active is not None:
            await asyncio.shield(active.task)

    async def aclose(self) -> None:
        async with self._lock:
            active = list(self._active.values())
        for job in active:
            job.task.cancel()
        for job in active:
            try:
                await job.task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                # Shutting down. Whatever could not end tidily is left to the
                # startup sweep, which marks it interrupted.
                continue

    async def _carry_out(
        self, job_id: uuid.UUID, kind: str, topics: TopicSet | None
    ) -> None:
        handler = self._handlers.get(kind)
        async with async_session_maker() as session:
            job = await session.get(Job, job_id)
            if job is None:
                return
            if handler is None:
                # Nothing can do this work in this process. Said as a failure
                # rather than left queued for ever.
                await self._settle(
                    session, job, "failed", "This server cannot carry out that job",
                    topics,
                )
                return
            await self._begin(session, job, handler, topics)
            progress = Progress(
                session=session, job=job, topics=topics, steps=handler.steps
            )
            try:
                message = await handler.carry_out(job, progress)
            except JobFailed as refusal:
                await self._settle(session, job, "failed", str(refusal), topics)
            except asyncio.CancelledError:
                # The process is going away; the row stays non-terminal and the
                # next startup calls it interrupted.
                raise
            except Exception:
                # Whatever this was, its text belongs in the log and not in an
                # answer: an engine names sockets and paths of this machine.
                logger.exception("Job %s (%s) failed", job_id, kind)
                await self._settle(
                    session, job, "failed", "The job could not be completed", topics
                )
            else:
                await self._settle(session, job, "succeeded", message, topics)
        async with self._lock:
            self._active.pop(job_id, None)

    async def _begin(
        self,
        session: AsyncSession,
        job: Job,
        handler: JobHandler,
        topics: TopicSet | None,
    ) -> None:
        job.state = "running"
        job.started_at = datetime.now(UTC)
        job.step_count = len(handler.steps)
        session.add(job)
        await session.commit()
        await session.refresh(job)
        if topics is not None:
            await announce(topics, job.owner_id, _event(job))

    async def _settle(
        self,
        session: AsyncSession,
        job: Job,
        state: str,
        message: str | None,
        topics: TopicSet | None,
    ) -> None:
        job.state = state
        job.message = message
        job.finished_at = datetime.now(UTC)
        if state == "succeeded":
            job.step_index = job.step_count
        session.add(job)
        await session.commit()
        await session.refresh(job)
        if topics is not None:
            await announce(topics, job.owner_id, _event(job))


async def recover_interrupted(session: AsyncSession) -> int:
    """End what a stopped process left running.

    A job whose row says `running` while nothing is running it is a lie a
    client would wait on for ever. Nothing is replayed: what a half-finished
    create left behind is a question for whoever looks at the service, and
    starting it again by ourselves is how one container becomes two.
    """
    statement = select(Job).where(col(Job.state).not_in(TERMINAL))
    stranded = list((await session.exec(statement)).all())
    if not stranded:
        return 0
    await session.exec(
        update(Job)
        .where(col(Job.id).in_([job.id for job in stranded]))
        .values(
            state="interrupted",
            message="The server stopped while this was running",
            finished_at=datetime.now(UTC),
        )
    )
    await session.commit()
    return len(stranded)


def get_runner(request: Request) -> JobRunner:
    """The runner of the running application.

    Through the application rather than a module global, for the same reason
    the resource store is: what outlives a request belongs to the application.
    """
    runner = request.app.state.job_runner
    if not isinstance(runner, JobRunner):
        raise RuntimeError("The application has no job runner; is the lifespan running?")
    return runner


JobRunnerDep = Annotated[JobRunner, Depends(get_runner)]
