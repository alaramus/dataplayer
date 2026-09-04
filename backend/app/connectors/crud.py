import uuid
from collections.abc import Collection
from typing import Any

from pydantic import TypeAdapter
from sqlalchemy import or_
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors.models import Connector, ConnectorGrant
from app.core.access import Access, ExecutionPolicy, Grant
from app.users.models import User

_LEVEL: TypeAdapter[Grant] = TypeAdapter(Grant)


def _granted(value: str) -> Grant:
    """A level as the database gave it, checked rather than assumed.

    The column is a plain string, so this is the only thing standing between a
    row edited by hand and a level travelling through the application without
    a rank. Cheap enough to do per row, and the alternative is a cast, which
    would assert the same thing without looking.
    """
    level: Grant = _LEVEL.validate_python(value)
    return level


async def create(
    session: AsyncSession,
    *,
    name: str,
    adapter_type: str,
    config: dict[str, Any],
    secrets: bytes,
    owner_id: uuid.UUID,
    execution_policy: ExecutionPolicy = "confirm_writes",
    tab_color: str | None = None,
) -> Connector:
    connector = Connector(
        name=name,
        adapter_type=adapter_type,
        config=config,
        secrets=secrets,
        owner_id=owner_id,
        execution_policy=execution_policy,
        tab_color=tab_color,
    )
    session.add(connector)
    await session.commit()
    await session.refresh(connector)
    return connector


async def access_of(
    session: AsyncSession, *, connector: Connector, user: User
) -> Access | None:
    """What this user holds on this connection, or nothing at all.

    Ownership first and a grant second, so the owner is never a row that could
    be missing. A superuser is deliberately not a case here: administering
    accounts is not a standing on somebody's data (D34).
    """
    if connector.owner_id == user.id:
        return "own"
    grant = await session.get(ConnectorGrant, (connector.id, user.id))
    if grant is None:
        return None
    return grant.access


async def get_with_access(
    session: AsyncSession, *, connector_id: uuid.UUID, user: User
) -> tuple[Connector, Access] | None:
    """The connection and the caller's standing on it, or nothing.

    Nothing covers both a connection that does not exist and one the caller
    has no standing on: otherwise enumerating ids reveals which connections
    other people hold.
    """
    connector = await session.get(Connector, connector_id)
    if connector is None:
        return None
    access = await access_of(session, connector=connector, user=user)
    if access is None:
        return None
    return connector, access


def _visible_to(user_id: uuid.UUID) -> ColumnElement[bool]:
    """The condition that a connection is the user's own or granted to them."""
    return or_(
        col(Connector.owner_id) == user_id,
        col(Connector.id).in_(
            select(ConnectorGrant.connector_id).where(
                ConnectorGrant.user_id == user_id
            )
        ),
    )


async def list_for(
    session: AsyncSession, *, user: User, skip: int = 0, limit: int = 100
) -> tuple[list[tuple[Connector, Access, str | None]], int]:
    """Every connection the user may see, each with their standing on it.

    One query rather than a list followed by a lookup per row: the standing
    and the owner's address are both a join away, and asking again per
    connection would grow with the list.
    """
    visible = _visible_to(user.id)
    count = (
        await session.exec(select(func.count()).select_from(Connector).where(visible))
    ).one()

    statement = (
        select(Connector, ConnectorGrant.access, User.email)
        .join(
            ConnectorGrant,
            onclause=(col(ConnectorGrant.connector_id) == Connector.id)
            & (col(ConnectorGrant.user_id) == user.id),
            isouter=True,
        )
        .join(User, onclause=col(User.id) == Connector.owner_id)
        .where(visible)
        .order_by(col(Connector.created_at).desc())
        .offset(skip)
        .limit(limit)
    )
    rows = (await session.exec(statement)).all()
    listed: list[tuple[Connector, Access, str | None]] = []
    for connector, granted, owner_email in rows:
        if connector.owner_id == user.id:
            listed.append((connector, "own", None))
        else:
            # Not the caller's own, so the row is in the answer only because
            # the outer join found a grant naming them.
            listed.append((connector, _granted(granted), owner_email))
    return listed, count


async def visible_enabled_of(
    session: AsyncSession, *, user_id: uuid.UUID
) -> list[Connector]:
    """Every switched-on connection one user may see, owned or granted.

    What the health monitor watches. A shared connection left out of it would
    be a connection whose state is permanently unknown to the person who was
    given it.
    """
    statement = select(Connector).where(
        _visible_to(user_id), col(Connector.enabled).is_(True)
    )
    return list((await session.exec(statement)).all())


async def visible_names(
    session: AsyncSession, *, user: User, connector_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """What these connections are called, for the ones this user may see.

    One query for a page of query documents rather than a lookup per document,
    and the omissions are the answer: a connection missing from the result is
    one that was deleted or is no longer granted, which is exactly what a
    document with an unavailable context has to say (D63).
    """
    if not connector_ids:
        return {}
    statement = select(Connector).where(
        _visible_to(user.id), col(Connector.id).in_(list(connector_ids))
    )
    return {
        connector.id: connector.name
        for connector in (await session.exec(statement)).all()
    }


async def list_grants(
    session: AsyncSession, *, connector_id: uuid.UUID
) -> list[tuple[User, Grant]]:
    statement = (
        select(User, ConnectorGrant.access)
        .join(ConnectorGrant, onclause=col(ConnectorGrant.user_id) == User.id)
        .where(ConnectorGrant.connector_id == connector_id)
        .order_by(col(User.email))
    )
    return [
        (user, _granted(access)) for user, access in (await session.exec(statement)).all()
    ]


async def set_grant(
    session: AsyncSession,
    *,
    connector_id: uuid.UUID,
    user_id: uuid.UUID,
    access: Grant,
) -> ConnectorGrant:
    """Give a level, or change the one already given."""
    grant = await session.get(ConnectorGrant, (connector_id, user_id))
    if grant is None:
        grant = ConnectorGrant(
            connector_id=connector_id, user_id=user_id, access=access
        )
    else:
        grant.access = access
    session.add(grant)
    await session.commit()
    await session.refresh(grant)
    return grant


async def remove_grant(
    session: AsyncSession, *, connector_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    grant = await session.get(ConnectorGrant, (connector_id, user_id))
    if grant is None:
        return False
    await session.delete(grant)
    await session.commit()
    return True


async def save(session: AsyncSession, *, connector: Connector) -> Connector:
    session.add(connector)
    await session.commit()
    await session.refresh(connector)
    return connector


async def delete(session: AsyncSession, *, connector: Connector) -> None:
    await session.delete(connector)
    await session.commit()
