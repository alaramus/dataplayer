"""Making an address, following one, and taking one back.

D58: nothing here grants anything. Creating a link asks for `read` on the
connection because a link names something the caller can already see; following
one asks for nothing, and answers what the follower's own standing allows.
"""

import uuid
from typing import Any, cast

from fastapi import APIRouter, Query
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors import crud as connector_crud
from app.connectors.access import get_or_404, resolve
from app.connectors.models import Connector
from app.core.db import SessionDep
from app.core.problems import Problem
from app.core.schemas import Message
from app.realtime.topics import TopicsDep
from app.shares import crud, topic
from app.shares.models import (
    AccessRequest,
    AccessRequestPublic,
    AccessRequestsPublic,
    RequestApproval,
    RequestState,
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
        raise Problem(409, "shares.link_outdated") from None


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


def _asked_public(
    asked: AccessRequest,
    requester: User,
    connector_label: str,
    node_label: str | None,
) -> AccessRequestPublic:
    return AccessRequestPublic(
        id=asked.id,
        connector_id=asked.connector_id,
        connector_label=connector_label,
        requester_id=requester.id,
        requester_email=requester.email,
        requester_name=requester.full_name,
        node_label=node_label,
        state=cast(RequestState, asked.state),
        created_at=asked.created_at,
    )


async def _node_labels(
    session: AsyncSession, asks: list[AccessRequest]
) -> dict[uuid.UUID, str]:
    """What each request came looking for, where the link is still there.

    Context and nothing more: the answer is about the connection either way,
    and a deleted link leaves the ask standing (D61).
    """
    labels: dict[uuid.UUID, str] = {}
    for asked in asks:
        if asked.share_id is None:
            continue
        share = await crud.by_id(session, share_id=asked.share_id)
        if share is not None:
            labels[asked.id] = share.node_label
    return labels


async def _answerable(
    session: AsyncSession, current_user: User, request_id: uuid.UUID
) -> tuple[AccessRequest, User, Connector]:
    """The ask this owner may answer, or the reason they may not.

    An ask that has already been answered is gone as far as this route is
    concerned, so two windows of one owner cannot hand out two grants for it.
    """
    asked = await crud.request_by_id(session, request_id=request_id)
    if asked is None or asked.state != "pending":
        raise Problem(404, "shares.request_not_found")
    connector = await get_or_404(
        session, asked.connector_id, current_user, requires="own"
    )
    requester = await session.get(User, asked.requester_id)
    if requester is None:
        raise Problem(404, "shares.request_not_found")
    return asked, requester, connector


@router.get("/requests", response_model=AccessRequestsPublic)
async def list_requests(
    session: SessionDep,
    current_user: CurrentUser,
    connector_id: uuid.UUID | None = Query(default=None),
) -> Any:
    """Who is waiting: on one connection, or on every connection of mine.

    The owner's business either way, like the grants beside which these are
    answered. Naming none is what the activity sheet asks (D113), and it widens
    nothing: the query joins on ownership rather than trusting a list of ids
    from the caller.
    """
    if connector_id is None:
        across = await crud.pending_for_owner(session, owner_id=current_user.id)
        labels = await _node_labels(session, [asked for asked, _, _ in across])
        return AccessRequestsPublic(
            data=[
                _asked_public(asked, requester, connector.name, labels.get(asked.id))
                for asked, requester, connector in across
            ]
        )
    connector = await get_or_404(session, connector_id, current_user, requires="own")
    waiting = await crud.pending_for_connector(session, connector_id=connector_id)
    labels = await _node_labels(session, [asked for asked, _ in waiting])
    return AccessRequestsPublic(
        data=[
            _asked_public(asked, requester, connector.name, labels.get(asked.id))
            for asked, requester in waiting
        ]
    )


@router.post("/requests/{request_id}/approve", response_model=AccessRequestPublic)
async def approve_request(
    session: SessionDep,
    current_user: CurrentUser,
    topics: TopicsDep,
    request_id: uuid.UUID,
    body: RequestApproval,
) -> Any:
    """Say yes, which is to write an ordinary grant.

    D61: approving adds no second kind of access. The level is the owner's
    choice at this moment; the ask itself only ever asked for `read`.
    """
    asked, requester, connector = await _answerable(session, current_user, request_id)
    await connector_crud.set_grant(
        session,
        connector_id=asked.connector_id,
        user_id=asked.requester_id,
        access=body.access,
    )
    answered = await crud.close_request(session, asked=asked, state="approved")
    await topic.announce(
        topics,
        asked.requester_id,
        topic.RequestEvent(
            kind="answered",
            request_id=answered.id,
            connector_id=connector.id,
            connector_label=connector.name,
            person=_display(current_user),
            outcome="approved",
            access=body.access,
        ),
    )
    return _asked_public(answered, requester, connector.name, None)


@router.post("/requests/{request_id}/decline", response_model=AccessRequestPublic)
async def decline_request(
    session: SessionDep,
    current_user: CurrentUser,
    topics: TopicsDep,
    request_id: uuid.UUID,
) -> Any:
    """Say no, and say it without a reason.

    The reason is a conversation between people, not a field in a form. What
    the person is told is that they were answered at all, so they are not left
    asking into silence.
    """
    asked, requester, connector = await _answerable(session, current_user, request_id)
    answered = await crud.close_request(session, asked=asked, state="declined")
    await topic.announce(
        topics,
        asked.requester_id,
        topic.RequestEvent(
            kind="answered",
            request_id=answered.id,
            connector_id=connector.id,
            connector_label=connector.name,
            person=_display(current_user),
            outcome="declined",
        ),
    )
    return _asked_public(answered, requester, connector.name, None)


@router.delete("/requests/{request_id}")
async def cancel_request(
    session: SessionDep, current_user: CurrentUser, request_id: uuid.UUID
) -> Message:
    """Take back an ask. The person who made it, and nobody else."""
    asked = await crud.request_by_id(session, request_id=request_id)
    if asked is None or asked.state != "pending":
        raise Problem(404, "shares.request_not_found")
    if asked.requester_id != current_user.id:
        raise Problem(404, "shares.request_not_found")
    await crud.close_request(session, asked=asked, state="cancelled")
    return Message(message="Request withdrawn")


@router.post("/{token}/request", response_model=AccessRequestPublic)
async def request_access(
    session: SessionDep,
    current_user: CurrentUser,
    topics: TopicsDep,
    token: str,
) -> Any:
    """Ask the owner of this connection for access to it.

    Only reachable through a link, which is the whole of the discovery: a
    connection nobody has shared is invisible, so there is nothing to ask
    about (D61).
    """
    share = await crud.by_token(session, token=token)
    if share is None:
        raise Problem(404, "shares.link_not_found")
    connector = await session.get(Connector, share.connector_id)
    if connector is None:
        raise Problem(404, "shares.link_not_found")
    held = await connector_crud.get_with_access(
        session, connector_id=share.connector_id, user=current_user
    )
    if held is not None:
        # There is nothing to ask for. The screen resolves the link again and
        # walks in rather than explaining this.
        raise Problem(409, "shares.already_have_access")
    asked, opened = await crud.open_request(
        session,
        connector_id=share.connector_id,
        requester_id=current_user.id,
        share_id=share.id,
    )
    if opened:
        await topic.announce(
            topics,
            connector.owner_id,
            topic.RequestEvent(
                kind="asked",
                request_id=asked.id,
                connector_id=connector.id,
                connector_label=connector.name,
                person=_display(current_user),
            ),
        )
    return _asked_public(asked, current_user, share.connector_label, share.node_label)


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
        raise Problem(404, "shares.link_not_found")
    author = await session.get(User, share.author_id)
    found = await connector_crud.get_with_access(
        session, connector_id=share.connector_id, user=current_user
    )
    if found is None:
        waiting = await crud.pending_request(
            session, connector_id=share.connector_id, requester_id=current_user.id
        )
        return ShareBarred(
            connector_label=share.connector_label,
            node_label=share.node_label,
            shared_by=_display(author),
            requested=waiting is not None,
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
        raise Problem(404, "shares.link_not_found")
    if share.author_id != current_user.id:
        await get_or_404(session, share.connector_id, current_user, requires="own")
    await crud.delete(session, share=share)
    return Message(message="Link deleted")
