"""Whether a caller may reach a connection, asked in exactly one place.

D33: a route states the level it needs, and the answer is one comparison
against what the caller holds. The check sits here rather than inside the
connector routes because a second module — sharing — has to ask the same
question, and an access check that exists twice is a hole waiting for the first
change that touches only one of the copies.
"""

import uuid

from fastapi import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors import crud
from app.connectors.models import Connector
from app.core.access import Access, at_least
from app.users.models import User


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
        raise HTTPException(status_code=404, detail="Connector not found")
    connector, access = found
    if not at_least(access, requires):
        raise HTTPException(
            status_code=403,
            detail={
                "message": f"This needs {requires} access to the connection",
                "required": requires,
                "held": access,
            },
        )
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
