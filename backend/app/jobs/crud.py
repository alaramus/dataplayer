"""Database access for jobs, and nothing else."""

import uuid
from collections.abc import Collection
from typing import Any

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.jobs.models import TERMINAL, Job, JobKind, JobsPublic, public


class TooManyActive(Exception):
    """The owner already has as many unfinished jobs of this kind as allowed."""


class SubjectBusy(Exception):
    """A job this one may not run beside is unfinished for the same subject."""

    def __init__(self, job_id: uuid.UUID) -> None:
        super().__init__(f"Job {job_id} is unfinished for this subject")
        self.job_id = job_id


async def for_owner(
    session: AsyncSession, owner_id: uuid.UUID, *, skip: int, limit: int
) -> JobsPublic:
    """Bounded history, with active work ahead of finished work (D95)."""
    owned = Job.owner_id == owner_id
    active = col(Job.state).not_in(TERMINAL)
    count = (await session.exec(select(func.count()).select_from(Job).where(owned))).one()
    active_count = (
        await session.exec(select(func.count()).select_from(Job).where(owned, active))
    ).one()
    rows = await session.exec(
        select(Job)
        .where(owned)
        .order_by(active.desc(), col(Job.created_at).desc(), col(Job.id).desc())
        .offset(skip)
        .limit(limit)
    )
    return JobsPublic(
        data=[public(job) for job in rows.all()], count=count, active_count=active_count
    )


async def create(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    kind: JobKind,
    subject_id: uuid.UUID | None,
    step_count: int,
    parameters: dict[str, Any] | None = None,
) -> Job:
    """Record a job as accepted. It is not running yet, and says so."""
    job = Job(
        owner_id=owner_id,
        kind=kind,
        subject_id=subject_id,
        step_count=step_count,
        parameters=parameters,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def admit_exclusive(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    kind: JobKind,
    subject_id: uuid.UUID,
    excluding: Collection[JobKind],
    step_count: int,
    parameters: dict[str, Any] | None = None,
) -> Job:
    """Record a job unless one of `excluding` is unfinished for the same subject.

    Checking and then creating lets two processes both see nothing and both
    create. A transaction-scoped advisory lock on the subject serialises the
    check and the insert across processes, and the commit releases it.
    """
    await session.exec(select(func.pg_advisory_xact_lock(
        func.hashtextextended(f"job-subject:{subject_id}", 0)
    )))
    busy = (await session.exec(
        select(Job)
        .where(Job.subject_id == subject_id)
        .where(col(Job.kind).in_(list(excluding)))
        .where(col(Job.state).not_in(TERMINAL))
        .order_by(col(Job.created_at).desc())
        .limit(1)
    )).first()
    if busy is not None:
        # Read before the rollback, which expires every loaded row.
        busy_id = busy.id
        await session.rollback()
        raise SubjectBusy(busy_id)
    return await create(
        session, owner_id=owner_id, kind=kind, subject_id=subject_id,
        step_count=step_count, parameters=parameters,
    )


async def admit_within(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    kind: JobKind,
    limit: int,
    subject_id: uuid.UUID | None,
    step_count: int,
    parameters: dict[str, Any] | None = None,
) -> Job:
    """Record a job unless its owner already has `limit` of this kind unfinished.

    Refused rather than queued, as a run over the limit is (D64). The same
    advisory lock as `admit_exclusive`, on the owner and the kind, so two tabs
    cannot both take the last place.
    """
    await session.exec(select(func.pg_advisory_xact_lock(
        func.hashtextextended(f"job-owner:{kind}:{owner_id}", 0)
    )))
    active = (await session.exec(
        select(func.count())
        .select_from(Job)
        .where(Job.owner_id == owner_id)
        .where(Job.kind == kind)
        .where(col(Job.state).not_in(TERMINAL))
    )).one()
    if active >= limit:
        await session.rollback()
        raise TooManyActive
    return await create(
        session, owner_id=owner_id, kind=kind, subject_id=subject_id,
        step_count=step_count, parameters=parameters,
    )


async def get_for_owner(
    session: AsyncSession, job_id: uuid.UUID, owner_id: uuid.UUID
) -> Job | None:
    """One job of this owner. Somebody else's is not found rather than refused,
    the rule connectors already follow: an id is not an oracle."""
    job = await session.get(Job, job_id)
    if job is None or job.owner_id != owner_id:
        return None
    return job


async def unfinished_for_subject(
    session: AsyncSession, subject_id: uuid.UUID
) -> Job | None:
    """Whatever is already happening to this thing, if anything is.

    A service takes one job at a time. Two of them at once would be two
    processes telling one container what to do, and the second would report
    the outcome of a race.
    """
    statement = (
        select(Job)
        .where(Job.subject_id == subject_id)
        .where(col(Job.state).not_in(TERMINAL))
        .order_by(col(Job.created_at).desc())
        .limit(1)
    )
    return (await session.exec(statement)).first()


async def for_subject(
    session: AsyncSession, subject_id: uuid.UUID, *, limit: int = 20
) -> list[Job]:
    statement = (
        select(Job)
        .where(Job.subject_id == subject_id)
        .order_by(col(Job.created_at).desc())
        .limit(limit)
    )
    return list((await session.exec(statement)).all())
