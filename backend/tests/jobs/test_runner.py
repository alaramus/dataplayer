
"""Work the server owns: how it moves, what it says, and how it ends (D81)."""

import asyncio
import re
import uuid
from collections.abc import AsyncGenerator
from typing import ClassVar

import pytest
from sqlmodel import col, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import async_session_maker
from app.jobs import crud
from app.jobs.models import Job, JobKind
from app.jobs.runner import (
    JobFailed,
    JobHandler,
    JobRunner,
    Progress,
    recover_interrupted,
)
from app.jobs.topic import JobEvent, JobsTopic
from app.realtime.topics import TopicSet
from app.users import crud as user_crud
from app.users.models import User


class _Recording:
    """A handler that reports each of its steps and then succeeds."""

    kind: ClassVar[JobKind] = "service.start"
    steps: ClassVar[tuple[str, ...]] = ("first", "second")

    def __init__(self) -> None:
        self.done: list[str] = []

    async def carry_out(self, job: Job, progress: Progress) -> str:
        for step in self.steps:
            await progress.reached(step)
            self.done.append(step)
        return "all of it"


class _Refusing:
    kind: ClassVar[JobKind] = "service.stop"
    steps: ClassVar[tuple[str, ...]] = ("trying",)

    async def carry_out(self, job: Job, progress: Progress) -> str:
        await progress.reached("trying")
        raise JobFailed("The engine would not")


class _Bursting:
    """A handler that fails the way code fails, rather than the way work does."""

    kind: ClassVar[JobKind] = "service.restart"
    steps: ClassVar[tuple[str, ...]] = ("trying",)

    async def carry_out(self, job: Job, progress: Progress) -> str:
        raise RuntimeError("connect /var/run/docker.sock: permission denied")


class _Undeclared:
    kind: ClassVar[JobKind] = "service.delete"
    steps: ClassVar[tuple[str, ...]] = ("declared",)

    async def carry_out(self, job: Job, progress: Progress) -> str:
        await progress.reached("something else entirely")
        return "never"


def _runner(*handlers: JobHandler) -> JobRunner:
    return JobRunner({handler.kind: handler for handler in handlers})


@pytest.fixture
async def owner(db: AsyncSession) -> User:
    from app.core.config import settings

    user = await user_crud.get_user_by_email(
        session=db, email=settings.FIRST_SUPERUSER
    )
    assert user is not None
    return user


@pytest.fixture(autouse=True)
async def without_jobs() -> AsyncGenerator[None]:
    """Every test here reads "the jobs there are", so it starts with none."""
    async with async_session_maker() as session:
        await session.exec(delete(Job))
        await session.commit()
    yield


async def _accepted(
    owner: User, runner: JobRunner, kind: JobKind, subject_id: uuid.UUID | None = None
) -> Job:
    async with async_session_maker() as session:
        return await crud.create(
            session,
            owner_id=owner.id,
            kind=kind,
            subject_id=subject_id,
            step_count=len(runner.steps_of(kind)),
        )


async def _read(job_id: uuid.UUID) -> Job:
    async with async_session_maker() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        return job


async def test_an_accepted_job_is_a_row_before_anything_runs(owner: User) -> None:
    """The whole difference from a task and a dictionary: it exists."""
    runner = _runner(_Recording())

    job = await _accepted(owner, runner, "service.start")

    assert job.state == "queued"
    assert job.step_count == 2
    assert job.started_at is None


async def test_cancellation_immediately_after_launch_settles_the_row(owner: User) -> None:
    handler = _Recording()
    runner = _runner(handler)
    job = await _accepted(owner, runner, handler.kind)
    await runner.launch(job)
    assert await runner.cancel(job.id)
    await runner.wait_for(job.id)
    settled = await _read(job.id)
    assert settled.state == "cancelled"
    assert settled.finished_at is not None
    assert handler.done == []
    assert await runner.active_count(owner.id) == 0


async def test_repeated_cancel_does_not_interrupt_cleanup(owner: User) -> None:
    entered = asyncio.Event()
    cleaning = asyncio.Event()
    release = asyncio.Event()

    class _Cleanup:
        kind: ClassVar[JobKind] = "service.start"
        steps: ClassVar[tuple[str, ...]] = ("waiting",)

        async def carry_out(self, job: Job, progress: Progress) -> str:
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaning.set()
                await release.wait()
            return "done"

    handler = _Cleanup()
    runner = _runner(handler)
    job = await _accepted(owner, runner, handler.kind)
    await runner.launch(job)
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        assert await runner.cancel(job.id)
        await asyncio.wait_for(cleaning.wait(), timeout=5)
        assert await runner.cancel(job.id)
    finally:
        release.set()
        await runner.wait_for(job.id)
    assert (await _read(job.id)).state == "cancelled"
    assert await runner.active_count(owner.id) == 0


async def test_a_job_runs_its_declared_steps_and_ends_with_a_sentence(
    owner: User,
) -> None:
    handler = _Recording()
    runner = _runner(handler)
    job = await _accepted(owner, runner, "service.start")

    await runner.launch(job)
    await runner.wait_for(job.id)

    settled = await _read(job.id)
    assert handler.done == ["first", "second"]
    assert settled.state == "succeeded"
    assert settled.message == "all of it"
    assert settled.step_index == settled.step_count == 2
    assert settled.started_at is not None
    assert settled.finished_at is not None


async def test_the_row_says_where_the_work_is_while_it_is_working(
    owner: User,
) -> None:
    """Progress is written before it is announced, so a client that polls and
    a client that listens are told the same thing."""
    held = asyncio.Event()

    class _Waiting:
        kind: ClassVar[JobKind] = "service.start"
        steps: ClassVar[tuple[str, ...]] = ("first", "second")

        async def carry_out(self, job: Job, progress: Progress) -> str:
            await progress.reached("first")
            await held.wait()
            return "done"

    runner = _runner(_Waiting())
    job = await _accepted(owner, runner, "service.start")
    await runner.launch(job)

    for _ in range(100):
        mid = await _read(job.id)
        if mid.step == "first":
            break
        await asyncio.sleep(0.01)

    assert mid.state == "running"
    assert mid.step == "first"
    assert mid.step_index == 1
    assert mid.step_count == 2
    held.set()
    await runner.wait_for(job.id)


async def test_a_refusal_is_the_handler_s_own_sentence(owner: User) -> None:
    runner = _runner(_Refusing())
    job = await _accepted(owner, runner, "service.stop")

    await runner.launch(job)
    await runner.wait_for(job.id)

    settled = await _read(job.id)
    assert settled.state == "failed"
    assert settled.message == "The engine would not"


async def test_an_unexpected_failure_says_nothing_about_this_machine(
    owner: User,
) -> None:
    """An engine's text names sockets and paths of the server it runs on."""
    runner = _runner(_Bursting())
    job = await _accepted(owner, runner, "service.restart")

    await runner.launch(job)
    await runner.wait_for(job.id)

    settled = await _read(job.id)
    assert settled.state == "failed"
    # A sentence of this repository's, and the ref of the log entry that holds
    # the rest (D184).
    assert re.fullmatch(r"The job could not be completed · ref [A-Z2-9]{6}", settled.message or "")
    assert "docker.sock" not in (settled.message or "")


async def test_a_step_nobody_declared_is_a_mistake_rather_than_a_surprise(
    owner: User,
) -> None:
    """A person is promised a list of steps; showing them one that is not on
    it would be worse than failing."""
    runner = _runner(_Undeclared())
    job = await _accepted(owner, runner, "service.delete")

    await runner.launch(job)
    await runner.wait_for(job.id)

    settled = await _read(job.id)
    assert settled.state == "failed"


async def test_a_kind_this_process_cannot_do_fails_rather_than_waits(
    owner: User,
) -> None:
    runner = _runner(_Recording())
    job = await _accepted(owner, runner, "service.start")
    other = JobRunner({})

    await other.launch(job)
    await other.wait_for(job.id)

    settled = await _read(job.id)
    assert settled.state == "failed"


async def test_what_a_stopped_process_left_running_ends_as_interrupted(
    owner: User,
) -> None:
    """Nothing is replayed: one container becoming two is worse than a job
    somebody has to look at."""
    async with async_session_maker() as session:
        stranded = await crud.create(
            session,
            owner_id=owner.id,
            kind="service.create",
            subject_id=uuid.uuid4(),
            step_count=3,
        )
        stranded.state = "running"
        session.add(stranded)
        await session.commit()

        settled_count = await recover_interrupted(session)

    assert settled_count == 1
    after = await _read(stranded.id)
    assert after.state == "interrupted"
    assert after.finished_at is not None


async def test_a_terminal_job_is_left_alone_by_the_sweep(owner: User) -> None:
    async with async_session_maker() as session:
        done = await crud.create(
            session, owner_id=owner.id, kind="service.stop", subject_id=None, step_count=1
        )
        done.state = "succeeded"
        done.message = "kept"
        session.add(done)
        await session.commit()

        await recover_interrupted(session)

    after = await _read(done.id)
    assert after.state == "succeeded"
    assert after.message == "kept"


async def test_one_thing_at_a_time_is_a_question_the_rows_answer(
    owner: User,
) -> None:
    subject = uuid.uuid4()
    async with async_session_maker() as session:
        first = await crud.create(
            session,
            owner_id=owner.id,
            kind="service.start",
            subject_id=subject,
            step_count=1,
        )

        assert (await crud.unfinished_for_subject(session, subject)) is not None

        first.state = "succeeded"
        session.add(first)
        await session.commit()

        assert (await crud.unfinished_for_subject(session, subject)) is None


async def test_every_move_is_announced_to_the_owner_and_to_nobody_else(
    owner: User,
) -> None:
    """The socket is a courtesy; the row is the authority (D64 said the same
    about a run). This checks the courtesy arrives."""
    seen: list[JobEvent] = []

    class _Listener:
        user_id = owner.id

        async def deliver(self, topic: str, payload: object) -> None:
            assert isinstance(payload, JobEvent)
            seen.append(payload)

    topic = JobsTopic()
    await topic.subscribe(_Listener())  # type: ignore[arg-type]  # a subscriber is a protocol
    topics = TopicSet({"jobs": topic})
    runner = _runner(_Recording())
    job = await _accepted(owner, runner, "service.start")

    await runner.launch(job, topics)
    await runner.wait_for(job.id)

    # Starting is announced before any step has been reached, then each step,
    # then the outcome — which keeps the last step visible beside it.
    assert [(event.state, event.step) for event in seen] == [
        ("running", None),
        ("running", "first"),
        ("running", "second"),
        ("succeeded", "second"),
    ]
    assert seen[-1].message == "all of it"


async def test_a_job_belongs_to_its_owner(owner: User) -> None:
    runner = _runner(_Recording())
    job = await _accepted(owner, runner, "service.start")

    async with async_session_maker() as session:
        assert await crud.get_for_owner(session, job.id, owner.id) is not None
        assert await crud.get_for_owner(session, job.id, uuid.uuid4()) is None


async def test_jobs_about_one_thing_are_read_newest_first(owner: User) -> None:
    subject = uuid.uuid4()
    async with async_session_maker() as session:
        older = await crud.create(
            session,
            owner_id=owner.id,
            kind="service.start",
            subject_id=subject,
            step_count=1,
        )
        older.state = "succeeded"
        session.add(older)
        await session.commit()
        newer = await crud.create(
            session,
            owner_id=owner.id,
            kind="service.stop",
            subject_id=subject,
            step_count=1,
        )

        listed = await crud.for_subject(session, subject)

    assert [job.id for job in listed] == [newer.id, older.id]


async def test_the_jobs_of_one_subject_are_not_the_jobs_of_another(
    owner: User,
) -> None:
    async with async_session_maker() as session:
        await crud.create(
            session,
            owner_id=owner.id,
            kind="service.start",
            subject_id=uuid.uuid4(),
            step_count=1,
        )
        statement = select(Job).where(col(Job.subject_id) == uuid.uuid4())

        assert list((await session.exec(statement)).all()) == []
