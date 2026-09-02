"""Database access for managed services, and nothing else."""

import uuid
from datetime import UTC, datetime

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.services.models import ManagedService
from app.services.plan import container_name, volume_name
from app.services.templates import ServiceTemplate


async def create(
    session: AsyncSession, *, owner_id: uuid.UUID, template: ServiceTemplate
) -> ManagedService:
    """Write down a service before anything is started.

    The names are settled here rather than when the container is made, so
    every later command — start, stop, remove, a sweep for orphans — names the
    same container as the one that was planned.
    """
    service_id = uuid.uuid4()
    service = ManagedService(
        id=service_id,
        owner_id=owner_id,
        template_key=template.key,
        container_name=container_name(service_id, template),
        volume_name=volume_name(service_id, template),
        state="creating",
    )
    session.add(service)
    await session.commit()
    await session.refresh(service)
    return service


async def get_for_owner(
    session: AsyncSession, service_id: uuid.UUID, owner_id: uuid.UUID
) -> ManagedService | None:
    """One service of this owner. Somebody else's is not found, not refused."""
    service = await session.get(ManagedService, service_id)
    if service is None or service.owner_id != owner_id:
        return None
    return service


async def list_for_owner(
    session: AsyncSession, owner_id: uuid.UUID
) -> list[ManagedService]:
    statement = (
        select(ManagedService)
        .where(ManagedService.owner_id == owner_id)
        .order_by(col(ManagedService.created_at).desc())
    )
    return list((await session.exec(statement)).all())


async def set_state(
    session: AsyncSession, service: ManagedService, state: str
) -> ManagedService:
    service.state = state
    service.updated_at = datetime.now(UTC)
    session.add(service)
    await session.commit()
    await session.refresh(service)
    return service
