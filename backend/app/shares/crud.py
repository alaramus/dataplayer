"""Reading and writing share records.

Nothing here decides whether anybody may see anything: that is
`connectors.access`, and the routes ask it before calling in.
"""

import secrets
import uuid

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors.models import Connector
from app.core.schemas import get_datetime_utc
from app.shares.models import TOKEN_BYTES, AccessRequest, Share, ShareOpen
from app.shares.view import SharedView, fingerprint_of
from app.users.models import User


async def by_token(session: AsyncSession, *, token: str) -> Share | None:
    statement = select(Share).where(Share.token == token)
    return (await session.exec(statement)).first()


async def by_id(session: AsyncSession, *, share_id: uuid.UUID) -> Share | None:
    return await session.get(Share, share_id)


async def for_view(
    session: AsyncSession,
    *,
    author_id: uuid.UUID,
    fingerprint: str,
) -> Share | None:
    statement = select(Share).where(
        Share.author_id == author_id, Share.fingerprint == fingerprint
    )
    return (await session.exec(statement)).first()


async def create(
    session: AsyncSession,
    *,
    author_id: uuid.UUID,
    connector_id: uuid.UUID,
    connector_label: str,
    node_id: str,
    node_label: str,
    view: SharedView,
) -> Share:
    """The address for this view, made once.

    The unique constraint is the arbiter rather than the lookup above it: two
    windows of one person pressing Share at the same moment both find nothing
    and both insert. The loser of that race reads the winner's row, which is
    the answer it wanted anyway.
    """
    fingerprint = fingerprint_of(connector_id, node_id, view)
    existing = await for_view(session, author_id=author_id, fingerprint=fingerprint)
    if existing is not None:
        return existing
    share = Share(
        token=secrets.token_urlsafe(TOKEN_BYTES),
        author_id=author_id,
        connector_id=connector_id,
        connector_label=connector_label,
        node_id=node_id,
        node_label=node_label,
        view=view.model_dump(mode="json"),
        fingerprint=fingerprint,
    )
    session.add(share)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raced = await for_view(session, author_id=author_id, fingerprint=fingerprint)
        if raced is None:
            raise
        return raced
    await session.refresh(share)
    return share


async def list_for_connector(
    session: AsyncSession,
    *,
    connector_id: uuid.UUID,
    author_id: uuid.UUID | None = None,
) -> list[Share]:
    """Every link to a connection, or only the caller's own.

    `author_id` is `None` for the owner of the connection, who sees them all:
    who hands out addresses to their database is their business (D59).
    """
    statement = select(Share).where(Share.connector_id == connector_id)
    if author_id is not None:
        statement = statement.where(Share.author_id == author_id)
    statement = statement.order_by(col(Share.created_at).desc())
    return list((await session.exec(statement)).all())


async def delete(session: AsyncSession, *, share: Share) -> None:
    await session.delete(share)
    await session.commit()


async def record_open(
    session: AsyncSession, *, share: Share, user_id: uuid.UUID
) -> None:
    """Note that somebody other than the author followed the link."""
    if user_id == share.author_id:
        return
    opened = await session.get(ShareOpen, (share.id, user_id))
    now = get_datetime_utc()
    if opened is None:
        opened = ShareOpen(share_id=share.id, user_id=user_id, opens=1)
    else:
        opened.opens += 1
        opened.last_at = now
    session.add(opened)
    await session.commit()


async def openers_of(
    session: AsyncSession, *, share_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[tuple[User, ShareOpen]]]:
    """Who opened which link, in one query rather than one per link."""
    if not share_ids:
        return {}
    statement = (
        select(ShareOpen, User)
        .join(User, onclause=col(ShareOpen.user_id) == User.id)
        .where(col(ShareOpen.share_id).in_(share_ids))
        .order_by(col(ShareOpen.last_at).desc())
    )
    found: dict[uuid.UUID, list[tuple[User, ShareOpen]]] = {}
    for opened, user in (await session.exec(statement)).all():
        found.setdefault(opened.share_id, []).append((user, opened))
    return found


async def pending_request(
    session: AsyncSession, *, connector_id: uuid.UUID, requester_id: uuid.UUID
) -> AccessRequest | None:
    """The ask this person already has open on this connection, if any."""
    statement = select(AccessRequest).where(
        AccessRequest.connector_id == connector_id,
        AccessRequest.requester_id == requester_id,
        AccessRequest.state == "pending",
    )
    return (await session.exec(statement)).first()


async def request_by_id(
    session: AsyncSession, *, request_id: uuid.UUID
) -> AccessRequest | None:
    return await session.get(AccessRequest, request_id)


async def open_request(
    session: AsyncSession,
    *,
    connector_id: uuid.UUID,
    requester_id: uuid.UUID,
    share_id: uuid.UUID | None,
) -> tuple[AccessRequest, bool]:
    """Ask, or hand back the ask already waiting.

    D61: a second request while one is open is not a second row, so pressing
    the button again is not a way to prod anybody. The boolean says whether
    this call is what opened it, which is what decides if anyone is told.
    """
    waiting = await pending_request(
        session, connector_id=connector_id, requester_id=requester_id
    )
    if waiting is not None:
        return waiting, False
    asked = AccessRequest(
        connector_id=connector_id, requester_id=requester_id, share_id=share_id
    )
    session.add(asked)
    try:
        await session.commit()
    except IntegrityError:
        # Two windows of one person pressed at the same moment; the loser reads
        # the winner's row, which is the answer it wanted.
        await session.rollback()
        raced = await pending_request(
            session, connector_id=connector_id, requester_id=requester_id
        )
        if raced is None:
            raise
        return raced, False
    await session.refresh(asked)
    return asked, True


async def close_request(
    session: AsyncSession,
    *,
    asked: AccessRequest,
    state: str,
) -> AccessRequest:
    """Answer an ask, one way or another."""
    asked.state = state
    asked.answered_at = get_datetime_utc()
    session.add(asked)
    await session.commit()
    await session.refresh(asked)
    return asked


async def pending_for_connector(
    session: AsyncSession, *, connector_id: uuid.UUID
) -> list[tuple[AccessRequest, User]]:
    """Who is waiting on this connection, oldest first."""
    statement = (
        select(AccessRequest, User)
        .join(User, onclause=col(AccessRequest.requester_id) == User.id)
        .where(
            AccessRequest.connector_id == connector_id,
            AccessRequest.state == "pending",
        )
        .order_by(col(AccessRequest.created_at))
    )
    return list((await session.exec(statement)).all())


async def pending_for_owner(
    session: AsyncSession, *, owner_id: uuid.UUID
) -> list[tuple[AccessRequest, User, Connector]]:
    """Everything waiting on every connection this person owns, oldest first.

    The connection travels with the ask because the caller is about to name it:
    a list that crosses connections cannot say "this connection" (D113).
    """
    statement = (
        select(AccessRequest, User, Connector)
        .join(User, onclause=col(AccessRequest.requester_id) == User.id)
        .join(Connector, onclause=col(AccessRequest.connector_id) == Connector.id)
        .where(
            Connector.owner_id == owner_id,
            AccessRequest.state == "pending",
        )
        .order_by(col(AccessRequest.created_at))
    )
    return list((await session.exec(statement)).all())
