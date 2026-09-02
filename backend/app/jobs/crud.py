"""Database access for jobs, and nothing else."""

import uuid

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.jobs.models import TERMINAL, Job, JobKind


async def create(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    kind: JobKind,
    subject_id: uuid.UUID | None,
    step_count: int,
) -> Job:
    """Record a job as accepted. It is not running yet, and says so."""
    job = Job(
        owner_id=owner_id, kind=kind, subject_id=subject_id, step_count=step_count
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


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
