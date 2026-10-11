"""`/search/kept`: a connection's kept list of names, seen and switched (D212).

Anyone who can see a connection sees its list's state; only its owner keeps
it, stops keeping it or asks for it to be read now.
"""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app.connectors.access import resolve
from app.connectors.models import Connector
from app.core.access import Access
from app.core.db import SessionDep
from app.search import kept
from app.search.keep import ContentsAdd, KeepOverview, KeepState, KeepUpdate, SearchName
from app.users.deps import CurrentUser
from app.users.models import User

router = APIRouter(prefix="/search/kept", tags=["search"])


@router.get("", response_model=KeepOverview)
async def read_kept(session: SessionDep, current_user: CurrentUser) -> Any:
    """Every kept list on a connection this person can see."""
    return await kept.overview(session, current_user)


@router.get("/{connector_id}", response_model=KeepState)
async def read_keep(
    session: SessionDep, current_user: CurrentUser, connector_id: uuid.UUID
) -> Any:
    """One connection's list, kept or not."""
    connector, access = await resolve(session, connector_id, current_user, requires="read")
    return await _state(session, connector, access)


@router.put("/{connector_id}", response_model=KeepState)
async def change_keep(
    session: SessionDep,
    current_user: CurrentUser,
    connector_id: uuid.UUID,
    body: KeepUpdate,
) -> Any:
    """Keep this connection's names, or stop and delete them. The owner's alone:
    the list is a plaintext copy of their names (D212)."""
    connector, access = await resolve(session, connector_id, current_user, requires="own")
    if body.keep and not kept.can_keep(connector.adapter_type):
        raise HTTPException(
            501, detail={"message": "This kind of source cannot keep its names"}
        )
    await kept.change(session, connector, body)
    return await _state(session, connector, access)


@router.post("/{connector_id}/refresh", response_model=KeepState)
async def refresh_keep(
    session: SessionDep, current_user: CurrentUser, connector_id: uuid.UUID
) -> Any:
    """Read the names again now rather than when the window says."""
    connector, access = await resolve(session, connector_id, current_user, requires="own")
    row = await kept.row_of(session, connector.id)
    if row is None:
        raise HTTPException(
            409, detail={"message": "The names of this connection are not kept"}
        )
    await kept.ask_refresh(session, row)
    return await _state(session, connector, access)


@router.post("/{connector_id}/contents", response_model=KeepState)
async def add_contents(
    session: SessionDep,
    current_user: CurrentUser,
    connector_id: uuid.UUID,
    body: ContentsAdd,
) -> Any:
    """Keep the text of the files below a folder, or of the whole connection.
    The owner's alone, like the names it is read through (D217)."""
    connector, access = await resolve(session, connector_id, current_user, requires="own")
    if not kept.can_keep_contents(connector.adapter_type):
        raise HTTPException(
            501, detail={"message": "This kind of source cannot keep what its files hold"}
        )
    row = await kept.row_of(session, connector.id)
    if row is None:
        raise HTTPException(
            409, detail={"message": "Keep the names of this connection first"}
        )
    node_id = body.node_id or ""
    if node_id:
        # A folder whose name is kept: the scope is read from those names.
        found = await session.get(SearchName, (connector.id, node_id))
        if found is None or found.kind != "directory":
            raise HTTPException(
                422, detail={"message": "Choose a folder whose name is kept"}
            )
    await kept.add_contents(session, row, node_id)
    return await _state(session, connector, access)


@router.delete("/{connector_id}/contents", response_model=KeepState)
async def remove_contents(
    session: SessionDep,
    current_user: CurrentUser,
    connector_id: uuid.UUID,
    node_id: str = "",
) -> Any:
    """Stop keeping a folder's text; what no other folder covers is deleted."""
    connector, access = await resolve(session, connector_id, current_user, requires="own")
    await kept.remove_contents(session, connector.id, node_id)
    return await _state(session, connector, access)


async def _state(session: SessionDep, connector: Connector, access: Access) -> KeepState:
    owner = None
    if access != "own":
        found = await session.get(User, connector.owner_id)
        owner = None if found is None else found.email
    scopes = await kept.scopes_of(session, [connector.id])
    return kept.state_of(
        connector,
        access,
        owner,
        await kept.row_of(session, connector.id),
        scopes.get(connector.id, []),
    )
