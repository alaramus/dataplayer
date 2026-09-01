"""Making an address, following one, and taking one back.

D58: nothing here grants anything. Creating a link asks for `read` on the
connection because a link names something the caller can already see; following
one asks for nothing, and answers what the follower's own standing allows.
"""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors import crud as connector_crud
from app.connectors.access import get_or_404, resolve
from app.core.db import SessionDep
from app.core.schemas import Message
from app.shares import crud
from app.shares.models import (
    Share,
    ShareBarred,
    ShareCreate,
    ShareOpener,
    SharePublic,
    ShareResolved,
    SharesPublic,
    ShareTarget,
)
from app.shares.view import SharedView
from app.users.deps import CurrentUser
from app.users.models import User

router = APIRouter(prefix="/shares", tags=["shares"])


def _body_of(share: Share) -> SharedView:
    """The stored body, or a refusal a person can read.

    D59: a body written in a shape this version no longer accepts is answered
    for what it is. Letting the validation error out would make an old link
    look like a broken server.
    """
    try:
        return SharedView.model_validate(share.view)
    except ValidationError:
        raise HTTPException(
            status_code=409,
            detail="This link was made by an earlier version of the application",
        ) from None


async def _named(
    session: AsyncSession, user_ids: set[uuid.UUID]
) -> dict[uuid.UUID, User]:
    if not user_ids:
        return {}
    return {
        user_id: user
        for user_id in user_ids
        if (user := await session.get(User, user_id)) is not None
    }


def _display(user: User | None) -> str:
    if user is None:
        return "somebody"
    return user.full_name or user.email


@router.post("/", response_model=SharePublic)
async def create_share(
    session: SessionDep, current_user: CurrentUser, body: ShareCreate
) -> Any:
    """An address for what the caller is looking at.

    `read` and no more: making a link hands nothing over, so requiring the
    owner's level would forbid a harmless act and push people back to sending
    screenshots. Pressing the button twice gives the same address (D59).
    """
    connector = await get_or_404(
        session, body.connector_id, current_user, requires="read"
    )
    share = await crud.create(
        session,
        author_id=current_user.id,
        connector_id=connector.id,
        connector_label=connector.name,
        node_id=body.node_id,
        node_label=body.node_label,
        view=body.view,
    )
    return SharePublic(
        id=share.id,
        token=share.token,
        connector_id=share.connector_id,
        connector_label=share.connector_label,
        node_id=share.node_id,
        node_label=share.node_label,
        created_at=share.created_at,
        shared_by=_display(current_user),
        can_delete=True,
        openers=await _openers_of(session, share),
    )


async def _openers_of(session: AsyncSession, share: Share) -> list[ShareOpener]:
    found = await crud.openers_of(session, share_ids=[share.id])
    return [
        ShareOpener(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            opens=opened.opens,
            first_at=opened.first_at,
            last_at=opened.last_at,
        )
        for user, opened in found.get(share.id, [])
    ]


@router.get("/", response_model=SharesPublic)
async def list_shares(
    session: SessionDep,
    current_user: CurrentUser,
    connector_id: uuid.UUID = Query(),
) -> Any:
    """The links to one connection, with who has opened them.

    The owner sees every link made to their connection; anybody else sees the
    ones they made. `read` is required, so an author whose grant was revoked
    loses the log with the access — the link goes on working for the people it
    was sent to, but a window onto who reads that connection does not stay open
    (D59).
    """
    _, access = await resolve(session, connector_id, current_user, requires="read")
    shares = await crud.list_for_connector(
        session,
        connector_id=connector_id,
        author_id=None if access == "own" else current_user.id,
    )
    openers = await crud.openers_of(session, share_ids=[share.id for share in shares])
    authors = await _named(session, {share.author_id for share in shares})
    return SharesPublic(
        data=[
            SharePublic(
                id=share.id,
                token=share.token,
                connector_id=share.connector_id,
                connector_label=share.connector_label,
                node_id=share.node_id,
                node_label=share.node_label,
                created_at=share.created_at,
                shared_by=_display(authors.get(share.author_id)),
                can_delete=access == "own" or share.author_id == current_user.id,
                openers=[
                    ShareOpener(
                        user_id=user.id,
                        email=user.email,
                        full_name=user.full_name,
                        opens=opened.opens,
                        first_at=opened.first_at,
                        last_at=opened.last_at,
                    )
                    for user, opened in openers.get(share.id, [])
                ],
            )
            for share in shares
        ]
    )


@router.get("/{token}", response_model=ShareResolved)
async def resolve_share(
    session: SessionDep, current_user: CurrentUser, token: str
) -> Any:
    """What this link leads to, and whether the caller may follow it.

    D60: 200 either way. Having no standing is the expected other half of this
    feature, not a failure, and the client renders a screen for it rather than
    reading an error body. 404 is kept for a token that does not exist or was
    deleted, and both are answered the same so tokens cannot be probed.
    """
    share = await crud.by_token(session, token=token)
    if share is None:
        raise HTTPException(status_code=404, detail="Link not found")
    author = await session.get(User, share.author_id)
    found = await connector_crud.get_with_access(
        session, connector_id=share.connector_id, user=current_user
    )
    if found is None:
        return ShareBarred(
            connector_label=share.connector_label,
            node_label=share.node_label,
            shared_by=_display(author),
        )
    body = _body_of(share)
    await crud.record_open(session, share=share, user_id=current_user.id)
    connector, _ = found
    return ShareTarget(
        share_id=share.id,
        connector_id=share.connector_id,
        # The stored name is what a reader without standing is shown; a reader
        # who has it sees what the connection is called now.
        connector_label=connector.name,
        node_id=share.node_id,
        node_label=share.node_label,
        view=body,
        shared_by=_display(author),
    )


@router.delete("/{share_id}")
async def delete_share(
    session: SessionDep, current_user: CurrentUser, share_id: uuid.UUID
) -> Message:
    """Take an address back.

    Tidying, not defence: what closes access is revoking the grant, and the
    dialog says so where somebody is about to press this. The author may remove
    their own link even after losing access to the connection; anybody else
    needs to own it.
    """
    share = await crud.by_id(session, share_id=share_id)
    if share is None:
        raise HTTPException(status_code=404, detail="Link not found")
    if share.author_id != current_user.id:
        await get_or_404(session, share.connector_id, current_user, requires="own")
    await crud.delete(session, share=share)
    return Message(message="Link deleted")
