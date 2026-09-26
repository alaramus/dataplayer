"""What each of a person's connections can give each other, all at once (D174).

The paste registry already answers this for one pair (D164). Here it answers
for every ordered pair of the person's connections, by what the two are and
the person's standing on each — never for a selection, which is the pair
window's question. No source is opened: an adapter is built, which reads
nothing, and asked by capability.
"""

import uuid

from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.protocol import AdapterError, DataAdapter
from app.adapters.registry import (
    AdapterType,
    Category,
    UnknownAdapterType,
    category_title,
)
from app.adapters.registry import get as get_adapter_type
from app.connectors import crud, service
from app.connectors.access import context_for
from app.connectors.models import Connector
from app.connectors.paste.kinds import PasteKind
from app.connectors.paste.models import ClipboardMode, PasteKindName
from app.connectors.paste.registry import KINDS
from app.core.access import Access, at_least
from app.users.models import User

# The graph's own ceiling: a map it would refuse to draw is not worth building.
MAX_MAP_CONNECTIONS = 300
# How many visible connections are read to find the switched-on ones among
# them; a person who sees more than this is refused rather than half drawn.
MAX_READ = MAX_MAP_CONNECTIONS * 4


class MapConnection(BaseModel):
    id: uuid.UUID
    name: str
    adapter_type: str
    type_title: str
    category: Category
    category_title: str
    access: Access


class MapOperation(BaseModel):
    kind: PasteKindName
    title: str
    mode: ClipboardMode
    available: bool
    # What this person lacks for it, when they lack anything.
    reason: str | None = None


class MapArrow(BaseModel):
    """What one connection can give another, in that direction."""

    source_connector_id: uuid.UUID
    destination_connector_id: uuid.UUID
    operations: list[MapOperation]


class InteractionMap(BaseModel):
    connections: list[MapConnection]
    arrows: list[MapArrow]


class TooManyConnections(Exception):
    pass


async def interaction_map(session: AsyncSession, user: User) -> InteractionMap:
    listed, total = await crud.list_for(session, user=user, limit=MAX_READ)
    ends = [(connector, access) for connector, access, _ in listed if connector.enabled]
    if total > MAX_READ or len(ends) > MAX_MAP_CONNECTIONS:
        raise TooManyConnections
    connections: list[MapConnection] = []
    adapters: list[tuple[MapConnection, DataAdapter | None]] = []
    for connector, access in sorted(ends, key=lambda end: end[0].name.lower()):
        kind = _type_of(connector)
        if kind is None:
            continue
        node = MapConnection(
            id=connector.id,
            name=connector.name,
            adapter_type=connector.adapter_type,
            type_title=kind.title,
            category=kind.category,
            category_title=category_title(kind.category),
            access=access,
        )
        connections.append(node)
        adapters.append((node, _built(kind, connector)))
    arrows: list[MapArrow] = []
    for source, source_adapter in adapters:
        for destination, destination_adapter in adapters:
            if source.id == destination.id:
                continue
            if source_adapter is None or destination_adapter is None:
                continue
            operations = [
                _operation(kind, source, destination)
                for kind in KINDS
                if kind.serves(source_adapter, destination_adapter)
            ]
            if operations:
                arrows.append(
                    MapArrow(
                        source_connector_id=source.id,
                        destination_connector_id=destination.id,
                        operations=operations,
                    )
                )
    return InteractionMap(connections=connections, arrows=arrows)


def _type_of(connector: Connector) -> AdapterType | None:
    try:
        return get_adapter_type(connector.adapter_type)
    except UnknownAdapterType:
        return None


def _built(kind: AdapterType, connector: Connector) -> DataAdapter | None:
    """The adapter, built as a request would and asked nothing; or none when
    its stored options no longer read."""
    try:
        return service.build_adapter(
            kind,
            service.merge_options(connector.config, connector.secrets),
            context_for(connector.owner_id),
        )
    except (ValueError, AdapterError):
        return None


def _operation(
    kind: PasteKind, source: MapConnection, destination: MapConnection
) -> MapOperation:
    """The kind, open to this person or saying what they lack, as Paste says it."""
    reason: str | None = None
    if not at_least(destination.access, kind.destination_requires):
        reason = f"Needs {kind.destination_requires} access to {destination.name}"
    elif not at_least(source.access, kind.source_requires):
        reason = f"Needs {kind.source_requires} access to {source.name}"
    return MapOperation(
        kind=kind.name,
        title=kind.title,
        mode=kind.mode,
        available=reason is None,
        reason=reason,
    )
