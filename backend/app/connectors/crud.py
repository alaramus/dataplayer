import uuid
from typing import Any

from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors.models import Connector
from app.users.models import User


async def create(
    session: AsyncSession,
    *,
    name: str,
    adapter_type: str,
    config: dict[str, Any],
    secrets: bytes,
    owner_id: uuid.UUID,
) -> Connector:
    connector = Connector(
        name=name,
        adapter_type=adapter_type,
        config=config,
        secrets=secrets,
        owner_id=owner_id,
    )
    session.add(connector)
    await session.commit()
    await session.refresh(connector)
    return connector


async def get(
    session: AsyncSession, *, connector_id: uuid.UUID, owner: User
) -> Connector | None:
    connector = await session.get(Connector, connector_id)
    if connector is None:
        return None
    if connector.owner_id != owner.id and not owner.is_superuser:
        # Someone else's connector is indistinguishable from a missing one:
        # otherwise enumerating ids reveals which connections others have.
        return None
    return connector


async def list_for(
    session: AsyncSession, *, owner: User, skip: int = 0, limit: int = 100
) -> tuple[list[Connector], int]:
    count_statement = select(func.count()).select_from(Connector)
    statement = select(Connector).order_by(col(Connector.created_at).desc())
    if not owner.is_superuser:
        count_statement = count_statement.where(Connector.owner_id == owner.id)
        statement = statement.where(Connector.owner_id == owner.id)

    count = (await session.exec(count_statement)).one()
    connectors = (await session.exec(statement.offset(skip).limit(limit))).all()
    return list(connectors), count


async def enabled_of(
    session: AsyncSession, *, owner_id: uuid.UUID
) -> list[Connector]:
    """Every switched-on connector of one owner.

    By owner id and not by ``User``, and deliberately not through ``list_for``:
    that one shows a superuser everybody's connectors, which is right for an
    administrative list and wrong for watching your own connections.
    """
    statement = select(Connector).where(
        Connector.owner_id == owner_id, col(Connector.enabled).is_(True)
    )
    return list((await session.exec(statement)).all())


async def save(session: AsyncSession, *, connector: Connector) -> Connector:
    session.add(connector)
    await session.commit()
    await session.refresh(connector)
    return connector


async def delete(session: AsyncSession, *, connector: Connector) -> None:
    await session.delete(connector)
    await session.commit()
