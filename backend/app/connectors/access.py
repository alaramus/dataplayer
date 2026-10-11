"""Whether a caller may reach a connection, asked in exactly one place.

D33: a route states the level it needs, and the answer is one comparison
against what the caller holds. The check sits here rather than inside the
connector routes because a second module — sharing — has to ask the same
question, and an access check that exists twice is a hole waiting for the first
change that touches only one of the copies.
"""

import uuid
from dataclasses import dataclass

from fastapi import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.protocol import DataAdapter
from app.adapters.registry import AdapterContext, AdapterType, UnknownAdapterType
from app.adapters.registry import get as get_adapter_type
from app.adapters.resources import Pooling, ResourceStore
from app.connectors import crud, service
from app.connectors.models import Connector
from app.connectors.ssh_keys import OwnerKeys
from app.core.access import Access, at_least
from app.core.problems import Problem, ProblemCode
from app.users import storage
from app.users.models import User

# A code per level, not the level as a parameter (D225).
NEEDS: dict[Access, ProblemCode] = {
    "read": "access.needs_read",
    "write": "access.needs_write",
    "structure": "access.needs_structure",
    "own": "access.needs_own",
}


async def resolve(
    session: AsyncSession,
    connector_id: uuid.UUID,
    current_user: User,
    *,
    requires: Access,
) -> tuple[Connector, Access]:
    """The connection and the caller's standing, or the reason they get neither.

    The one place the question is asked. `requires` has no default on purpose:
    a route added later cannot reach a source without saying what it needs,
    because the call does not type-check without it.

    Two statuses, and the difference is what the caller already knows. No
    standing at all answers 404, the same as a connection that does not exist,
    so the id space is not an oracle for what other people hold. A standing
    below what the route needs answers 403: they can already see this
    connection, and hiding it now would only confuse.
    """
    found = await crud.get_with_access(
        session, connector_id=connector_id, user=current_user
    )
    if found is None:
        raise Problem(404, "connectors.not_found")
    connector, access = found
    if not at_least(access, requires):
        raise Problem(403, NEEDS[requires])
    return connector, access


async def get_or_404(
    session: AsyncSession,
    connector_id: uuid.UUID,
    current_user: User,
    *,
    requires: Access,
) -> Connector:
    connector, _ = await resolve(session, connector_id, current_user, requires=requires)
    return connector


def adapter_type_or_422(adapter_type: str) -> AdapterType:
    """The declared type of a stored connection, or a refusal a caller can read."""
    try:
        found: AdapterType = get_adapter_type(adapter_type)
        return found
    except UnknownAdapterType:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", "adapter_type"],
                    "msg": f"Unknown adapter type: {adapter_type}",
                    "type": "value_error",
                }
            ],
        )


def context_for(
    owner_id: uuid.UUID,
    *,
    pooling: Pooling | None = None,
) -> AdapterContext:
    """What the driver may reach, decided here rather than by the request.

    Always the owner's: a grantee reading a connection signs in with the
    owner's credentials and reads the owner's storage (D33), and a key is a
    credential like the rest (D146).
    """
    return AdapterContext(
        home_dir=storage.home_dir(owner_id),
        pooling=pooling,
        keys=OwnerKeys(owner_id),
    )


@dataclass(frozen=True)
class ResolvedSource:
    """A live source, what the caller may do with it, and how long it keeps.

    The freshness window travels with the adapter because it is read from the
    same row, in the same query the access check already makes. A route that
    asked for it separately would be a second read of the connector, and a
    route that forgot to would silently cache for the source's window instead
    of the owner's (D105).
    """

    adapter: DataAdapter
    access: Access
    cache_ttl_seconds: int | None


async def resolve_source(
    session: AsyncSession,
    connector_id: uuid.UUID,
    current_user: User,
    resources: ResourceStore | None = None,
    *,
    requires: Access,
) -> ResolvedSource:
    """Resolve a stored connector into a live adapter.

    A stored connector has an identity, so whatever it keeps between requests
    can be found again. Without a store — a check, which is meant to exercise
    the credentials — the driver connects on its own.

    A disabled connector is refused here rather than in each route: this is the
    one door to a live source, so the rule is written once and cannot be
    forgotten by a route added later. Reading and editing the row go through
    ``get_or_404`` and stay open — switching a connection off is not deleting
    it.
    """
    connector, access = await resolve(
        session, connector_id, current_user, requires=requires
    )
    if not connector.enabled:
        # 409 rather than 404: the connector exists and the caller can see it.
        # Nor 403: they hold the level this route asked for, and what is
        # missing is not a right but a switch its owner turned off.
        raise Problem(409, "connectors.disabled")
    adapter_type = adapter_type_or_422(connector.adapter_type)
    options = service.merge_options(connector.config, connector.secrets)
    pooling = (
        Pooling(store=resources, connector_id=connector.id)
        if resources is not None
        else None
    )
    return ResolvedSource(
        adapter=service.build_adapter(
            adapter_type,
            options,
            context_for(connector.owner_id, pooling=pooling),
        ),
        access=access,
        cache_ttl_seconds=connector.cache_ttl_seconds,
    )


async def resolve_adapter(
    session: AsyncSession,
    connector_id: uuid.UUID,
    current_user: User,
    resources: ResourceStore | None = None,
    *,
    requires: Access,
) -> tuple[DataAdapter, Access]:
    """A live adapter and the caller's level, for routes that cache nothing."""
    source = await resolve_source(
        session, connector_id, current_user, resources, requires=requires
    )
    return source.adapter, source.access


async def adapter_for(
    session: AsyncSession,
    connector_id: uuid.UUID,
    current_user: User,
    resources: ResourceStore | None = None,
    *,
    requires: Access,
) -> DataAdapter:
    """A live adapter, for the routes that do not need to report the level."""
    source = await resolve_source(
        session, connector_id, current_user, resources, requires=requires
    )
    return source.adapter
