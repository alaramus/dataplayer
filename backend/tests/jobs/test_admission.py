"""One job at a time per subject, admitted atomically (D81, D123)."""

import asyncio
import uuid
from collections.abc import AsyncGenerator

import pytest
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import async_session_maker
from app.jobs import crud
from app.jobs.models import Job, JobKind
from app.users import crud as user_crud
from app.users.models import User

EXCLUSIVE: tuple[JobKind, ...] = ("source.operation", "backup.restore")


@pytest.fixture
async def owner(db: AsyncSession) -> User:
    user = await user_crud.get_user_by_email(session=db, email=settings.FIRST_SUPERUSER)
    assert user is not None
    return user


@pytest.fixture(autouse=True)
async def without_jobs() -> AsyncGenerator[None]:
    async with async_session_maker() as session:
        await session.exec(delete(Job))
        await session.commit()
    yield


async def _admit(owner: User, subject: uuid.UUID, kind: JobKind = "source.operation") -> Job:
    async with async_session_maker() as session:
        return await crud.admit_exclusive(
            session, owner_id=owner.id, kind=kind, subject_id=subject,
            excluding=EXCLUSIVE, step_count=3,
        )


async def _existing(owner: User, subject: uuid.UUID, kind: JobKind, state: str) -> Job:
    async with async_session_maker() as session:
        job = await crud.create(
            session, owner_id=owner.id, kind=kind, subject_id=subject, step_count=1,
        )
        job.state = state
        session.add(job)
        await session.commit()
        return job


async def test_only_one_of_two_concurrent_admissions_is_recorded(owner: User) -> None:
    subject = uuid.uuid4()
    results = await asyncio.gather(_admit(owner, subject), _admit(owner, subject), return_exceptions=True)
    admitted = [result for result in results if isinstance(result, Job)]
    refused = [result for result in results if isinstance(result, crud.SubjectBusy)]
    assert len(admitted) == 1 and len(refused) == 1
    assert refused[0].job_id == admitted[0].id


@pytest.mark.parametrize("kind", ["source.operation", "backup.restore"])
async def test_an_unfinished_excluded_job_refuses_with_its_id(owner: User, kind: JobKind) -> None:
    subject = uuid.uuid4()
    running = await _existing(owner, subject, kind, "running")
    with pytest.raises(crud.SubjectBusy) as busy:
        await _admit(owner, subject)
    assert busy.value.job_id == running.id


async def test_kinds_not_excluded_and_finished_jobs_do_not_block(owner: User) -> None:
    subject = uuid.uuid4()
    await _existing(owner, subject, "backup.create", "running")
    await _existing(owner, subject, "source.operation", "interrupted")
    admitted = await _admit(owner, subject)
    assert admitted.state == "queued" and admitted.subject_id == subject


async def test_alone_refuses_a_second_of_the_kind_for_the_subject_within_the_limit(owner: User) -> None:
    subject = uuid.uuid4()

    async def within() -> Job:
        async with async_session_maker() as session:
            return await crud.admit_within(
                session, owner_id=owner.id, kind="pipeline.run", limit=3,
                subject_id=subject, step_count=2, alone=True,
            )

    results = await asyncio.gather(within(), within(), return_exceptions=True)
    admitted = [result for result in results if isinstance(result, Job)]
    refused = [result for result in results if isinstance(result, crud.SubjectBusy)]
    assert len(admitted) == 1 and len(refused) == 1
    assert refused[0].job_id == admitted[0].id
    async with async_session_maker() as session:
        ended = await session.get(Job, admitted[0].id)
        assert ended is not None
        ended.state = "succeeded"
        session.add(ended)
        await session.commit()
    assert (await within()).state == "queued"


async def test_another_subject_is_not_blocked(owner: User) -> None:
    await _existing(owner, uuid.uuid4(), "source.operation", "running")
    assert (await _admit(owner, uuid.uuid4())).state == "queued"
