"""Drawing, listing and removing a reference the application keeps (D106).

A router of its own rather than three more routes under one connection: a
declared reference belongs to neither of its ends, and hanging it off one of
them would make the other an argument.
"""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.adapters.protocol import AdapterError, NodeNotFound
from app.adapters.resources import ResourcesDep
from app.connectors.declared import (
    DeclaredReferenceCreate,
    DeclaredReferencePublic,
    EndReading,
    create,
    delete,
    get_own,
    list_visible,
    public_of,
    read_end,
)
from app.core.db import SessionDep
from app.core.problems import Problem
from app.core.schemas import Message
from app.core.translation import say
from app.users.deps import CurrentUser

router = APIRouter(prefix="/declared-references", tags=["declared-references"])


@router.get("/", response_model=list[DeclaredReferencePublic])
async def list_declared_references(
    session: SessionDep,
    current_user: CurrentUser,
    connector_id: uuid.UUID | None = None,
    node_id: str | None = Query(default=None, max_length=1024),
) -> Any:
    """
    Every reference this person has drawn, or only the ones touching one node.

    A reference whose far end they can no longer read is not listed, for the
    same reason its arrow is not drawn.
    """
    return await list_visible(
        session, user=current_user, connector_id=connector_id, node_id=node_id
    )


@router.post("/", response_model=DeclaredReferencePublic)
async def declare_reference(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    request: DeclaredReferenceCreate,
) -> Any:
    """
    Draw a reference between two columns no source calls related.

    Both ends are read from their sources first: `read` on each connection, the
    node still there, the column still among the ones it states, and equality
    among the ways that column can be looked up (D107). Drawing the same pair
    twice is the same reference.
    """
    first, second = request.ends
    if (first.connector_id, first.node_id, first.column) == (
        second.connector_id,
        second.node_id,
        second.column,
    ):
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", "ends"],
                    "msg": say("A column cannot reference itself"),
                    "type": "value_error",
                }
            ],
        )

    readings: list[EndReading] = []
    for position, end in enumerate(request.ends):
        try:
            readings.append(await read_end(session, current_user, resources, end))
        except NodeNotFound as exc:
            raise HTTPException(
                status_code=404, detail={"message": str(exc)}
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=[
                    {
                        "loc": ["body", "ends", position],
                        "msg": str(exc),
                        "type": "value_error",
                    }
                ],
            ) from exc
        except AdapterError as exc:
            raise HTTPException(
                status_code=502,
                detail={"message": exc.message, "error_kind": exc.error_kind},
            ) from exc

    reference = await create(
        session, author=current_user, ends=(readings[0], readings[1])
    )
    return public_of(
        reference, {reading.connector.id: reading.connector for reading in readings}
    )


@router.delete("/{reference_id}")
async def undeclare_reference(
    session: SessionDep,
    current_user: CurrentUser,
    reference_id: uuid.UUID,
) -> Message:
    """
    Remove one reference. Only its author has one to remove.
    """
    reference = await get_own(session, author=current_user, reference_id=reference_id)
    if reference is None:
        raise Problem(404, "declared.not_found")
    await delete(session, reference)
    return Message(message=say("Declared reference removed"))
