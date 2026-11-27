"""A person's copy history (D460): kept, listed, read whole, deleted."""

import uuid
from typing import Any

from fastapi import APIRouter, Query

from app.core.db import SessionDep
from app.core.problems import Problem
from app.users import copies
from app.users.copies import (
    CopiesDelete,
    CopiesDeleted,
    CopiesPublic,
    CopyBrief,
    CopyCreate,
    CopyPublic,
)
from app.users.deps import CurrentUser

router = APIRouter(prefix="/copies", tags=["copies"])


@router.get("/", response_model=CopiesPublic)
async def read_copies(
    session: SessionDep,
    current_user: CurrentUser,
    q: str | None = Query(default=None, max_length=200),
) -> Any:
    """This person's copies, newest first, the ones holding `q` when it is given."""
    return await copies.list_own(session, current_user.id, q)


@router.get("/{copy_id}", response_model=CopyPublic)
async def read_copy(session: SessionDep, current_user: CurrentUser, copy_id: uuid.UUID) -> Any:
    """One copy with its whole text, to be copied again."""
    row = await copies.read_own(session, current_user.id, copy_id)
    if row is None:
        raise Problem(404, "copies.not_found")
    return copies.public_of(row)


@router.post("/", response_model=CopyBrief)
async def record_copy(session: SessionDep, current_user: CurrentUser, body: CopyCreate) -> Any:
    """Keep what was just copied on top of the list."""
    return await copies.record(session, current_user.id, body)


@router.post("/delete", response_model=CopiesDeleted)
async def delete_copies(
    session: SessionDep, current_user: CurrentUser, body: CopiesDelete
) -> Any:
    """Delete the copies named. A POST, because a DELETE with a body is one
    proxies and clients are free to drop."""
    return CopiesDeleted(deleted=await copies.delete_own(session, current_user.id, body.ids))


@router.delete("/", response_model=CopiesDeleted)
async def clear_copies(session: SessionDep, current_user: CurrentUser) -> Any:
    """Delete every copy this person has."""
    return CopiesDeleted(deleted=await copies.delete_own(session, current_user.id, None))
