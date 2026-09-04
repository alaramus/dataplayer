import uuid
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from app.core.db import SessionDep
from app.jobs import crud
from app.jobs.models import JobPublic, JobsPublic, is_terminal, public
from app.jobs.runner import JobRunnerDep
from app.users.deps import CurrentUser

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/", response_model=JobsPublic)
async def read_jobs(
    session: SessionDep,
    current_user: CurrentUser,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> JobsPublic:
    """This owner's work, active first, with counts independent of the page."""
    return await crud.for_owner(session, current_user.id, skip=skip, limit=limit)


@router.get("/{job_id}", response_model=JobPublic)
async def read_job(
    session: SessionDep, current_user: CurrentUser, job_id: uuid.UUID
) -> Any:
    """
    What one owned job is doing, or what became of it.

    The authority on a job's state and the fallback for a client whose socket
    missed something: the same arrangement a query run has, and the reason the
    realtime message can be lost without costing anything (D81).
    """
    job = await crud.get_for_owner(session, job_id, current_user.id)
    if job is None:
        raise HTTPException(status_code=404, detail={"message": "No such job"})
    return public(job)


@router.post("/{job_id}/cancel", response_model=JobPublic)
async def cancel_job(
    session: SessionDep,
    current_user: CurrentUser,
    runner: JobRunnerDep,
    job_id: uuid.UUID,
) -> Any:
    """
    Ask a job to stop.

    What it had already done is left as it stands: a half-made service is a
    thing to retry or to remove, and undoing it here would be this application
    guessing at what somebody wanted kept (D84).

    A job that has already ended is answered rather than refused — the caller
    asked for it to be over, and it is.
    """
    job = await crud.get_for_owner(session, job_id, current_user.id)
    if job is None:
        raise HTTPException(status_code=404, detail={"message": "No such job"})
    if is_terminal(job.state):
        return public(job)
    if not await runner.cancel(job_id):
        # Not this process's to stop. One process carries out what it accepted,
        # so the honest answer is that this one cannot reach it.
        raise HTTPException(
            status_code=409,
            detail={"message": "This job is being carried out elsewhere"},
        )
    await session.refresh(job)
    return public(job)
