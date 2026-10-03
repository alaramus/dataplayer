"""Database access for managed services, and nothing else."""

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors.models import Connector
from app.services.models import ManagedService, ServicePurpose
from app.services.plan import Placement, container_name, volume_name
from app.services.templates import ServiceTemplate

# Every question of a person about their services is about connections: the
# metrics store is the installation's (D126).
_A_CONNECTION = col(ManagedService.purpose) == "connection"


async def create(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    template: ServiceTemplate,
    connector_name: str,
    placement: Placement,
    request_id: uuid.UUID | None = None,
    chosen_credentials: Mapping[str, str] | None = None,
    sample_data: bool = False,
    password_mode: str = "generated",
    chosen_password: bytes | None = None,
    purpose: ServicePurpose = "connection",
) -> ManagedService:
    """Write down a service before anything is started.

    The names are settled here rather than when the container is made, so
    every later command — start, stop, remove, a sweep for orphans — names the
    same container as the one that was planned.

    A password somebody typed arrives here already encrypted: this module does
    database access and nothing else, and a function that took a plaintext
    secret would be one more place a secret could be written down by mistake.
    """
    service_id = uuid.uuid4()
    service = ManagedService(
        id=service_id,
        owner_id=owner_id,
        template_key=template.key,
        purpose=purpose,
        request_id=request_id,
        connector_name=connector_name,
        container_name=container_name(service_id, template),
        volume_name=volume_name(service_id, template),
        network=placement.network,
        publish=placement.publish,
        requested_port=placement.host_port,
        sample_data=sample_data,
        chosen_credentials=dict(chosen_credentials or {}),
        password_mode=password_mode,
        chosen_password=chosen_password,
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
    if (
        service is None
        or service.owner_id != owner_id
        or service.purpose != "connection"
    ):
        return None
    return service


async def list_for_owner(
    session: AsyncSession, owner_id: uuid.UUID
) -> list[ManagedService]:
    statement = (
        select(ManagedService)
        .where(ManagedService.owner_id == owner_id)
        .where(_A_CONNECTION)
        .order_by(col(ManagedService.created_at).desc())
    )
    return list((await session.exec(statement)).all())


async def named_for_owner(
    session: AsyncSession,
    owner_id: uuid.UUID,
    *,
    limit: int,
    ids: Sequence[uuid.UUID] | None = None,
) -> list[tuple[ManagedService, str]]:
    """This owner's services, newest first, each with the name it goes by now.

    That is its connection's name; the name kept when it was asked for only
    while it has no connection, since a kept name goes stale with the first
    rename (D199).
    """
    statement = (
        select(ManagedService, Connector.name)
        .join(
            Connector,
            onclause=col(Connector.id) == col(ManagedService.connector_id),
            isouter=True,
        )
        .where(ManagedService.owner_id == owner_id)
        .where(_A_CONNECTION)
    )
    if ids is not None:
        statement = statement.where(col(ManagedService.id).in_(ids))
    rows = await session.exec(
        statement.order_by(col(ManagedService.created_at).desc()).limit(limit)
    )
    return [
        (service, service.connector_name if current is None else current)
        for service, current in rows.all()
    ]


async def set_state(
    session: AsyncSession, service: ManagedService, state: str
) -> ManagedService:
    service.state = state
    service.updated_at = datetime.now(UTC)
    session.add(service)
    await session.commit()
    await session.refresh(service)
    return service


async def by_request(
    session: AsyncSession, *, owner_id: uuid.UUID, request_id: uuid.UUID
) -> ManagedService | None:
    """The service an earlier request of this id already made, if it did.

    Scoped to the owner: an id somebody else chose says nothing about what
    this person asked for, and answering with their row would be a leak.
    """
    statement = (
        select(ManagedService)
        .where(ManagedService.owner_id == owner_id)
        .where(ManagedService.request_id == request_id)
        .where(_A_CONNECTION)
        .limit(1)
    )
    return (await session.exec(statement)).first()


async def all_container_names(session: AsyncSession) -> set[str]:
    """Every container name a service row still claims, whoever owns it.

    Deliberately not scoped to an owner: the question it answers is about the
    machine — what is running here that nothing knows about — and a set
    filtered by caller would call another person's service an orphan.
    """
    statement = select(ManagedService.container_name)
    return set((await session.exec(statement)).all())


async def names_taken(session: AsyncSession, owner_id: uuid.UUID) -> set[str]:
    """What this person's services are already called.

    Read so that a name nobody was asked for does not collide with one they
    chose earlier: two connections called "PostgreSQL 1" are two rows nobody
    can tell apart.
    """
    statement = (
        select(ManagedService.connector_name)
        .where(ManagedService.owner_id == owner_id)
        .where(_A_CONNECTION)
    )
    return set((await session.exec(statement)).all())


async def count_for_owner(session: AsyncSession, owner_id: uuid.UUID) -> int:
    """How many services this person has, whatever state they are in.

    Everything counts, including one that failed: a failed service still holds
    a name, and may still hold a container somebody has not looked at yet.
    """
    statement = (
        select(ManagedService.id)
        .where(ManagedService.owner_id == owner_id)
        .where(_A_CONNECTION)
    )
    return len(list((await session.exec(statement)).all()))


async def metrics_store_service(session: AsyncSession) -> ManagedService | None:
    """The service started to be the metrics store, if one ever was (D126)."""
    statement = (
        select(ManagedService)
        .where(col(ManagedService.purpose) == "metrics_store")
        .order_by(col(ManagedService.created_at).desc())
        .limit(1)
    )
    return (await session.exec(statement)).first()
