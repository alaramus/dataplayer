import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app.core.db import SessionDep
from app.jobs import crud
from app.jobs.models import JobPublic, public
from app.users.deps import CurrentUser

router = APIRouter(prefix="/jobs", tags=["jobs"])


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
