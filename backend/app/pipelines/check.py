"""Whether what a card names is still there (D175).

A card names nodes and does not hold them, so this is asked of the source
each time a card is drawn rather than remembered.
"""

from fastapi import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.protocol import AdapterError, NodeNotFound, SupportsNodePath
from app.adapters.resources import ResourceStore
from app.connectors.access import adapter_for
from app.pipelines.models import Card, CardState
from app.users.models import User

# What each refusal of the one door to a source means for a card. A person
# without standing and a connection deleted are one answer, as they are
# everywhere else (D33).
_REFUSALS = {
    404: "This connection is gone, or no longer shared with you",
    409: "This connection is switched off",
}


async def card_state(
    session: AsyncSession, user: User, resources: ResourceStore, card: Card
) -> CardState:
    try:
        adapter = await adapter_for(
            session, card.connector_id, user, resources, requires="read"
        )
    except HTTPException as refused:
        problem = _REFUSALS.get(refused.status_code, "This connection cannot be read")
        return CardState(problem=problem, checked=False)
    if not isinstance(adapter, SupportsNodePath):
        return CardState(checked=False)
    missing: list[str] = []
    # One row after another rather than all at once: an adapter is not
    # promised to take concurrent calls, and a source that fails fails on the
    # first row instead of a hundred times.
    for row in card.rows:
        if row.node_id is None:
            continue
        try:
            await adapter.path_to(row.node_id)
        except (NodeNotFound, ValueError):
            missing.append(row.node_id)
        except AdapterError as failure:
            return CardState(problem=failure.message, checked=False)
    return CardState(missing=missing)
