"""What the person last opened from the search, named again (S6).

The browser keeps the targets and sends them; nothing is stored here. They are
answered through the same visibility the search itself uses: a connection the
person can no longer read, a node of a connection switched off, and an object
that is not theirs are dropped without a word (D199).
"""

import uuid
from collections.abc import Sequence

from app.search.connections import connection_hit
from app.search.models import (
    ConnectionTarget,
    Facts,
    Hit,
    NodeTarget,
    ObjectsPlace,
    ObjectTarget,
    ObjectType,
    recent_target,
    target_key,
)
from app.search.providers import (
    ApplicationProvider,
    Asked,
    Found,
    ProviderCell,
    Recalls,
    VisibleConnection,
    recalled,
)


class RecentlyOpened:
    """The whole of an empty search, in the order the things were opened."""

    place = ObjectsPlace(provider="recent")
    title = "Recently opened"
    offered_to_agent = False

    def __init__(self, providers: Sequence[ApplicationProvider]) -> None:
        # The engine's own list rather than a copy, so a provider handed in
        # later is asked too.
        self._providers = providers

    def cells(self) -> tuple[ProviderCell, ...]:
        return (ProviderCell(field="names", cost="instant"),)

    async def search(self, asked: Asked) -> Found:
        visible = {connection.id: connection for connection in asked.visible}
        targets = [
            target for target in map(recent_target, asked.recent) if target is not None
        ]
        objects = await self._objects(
            asked, [target for target in targets if isinstance(target, ObjectTarget)]
        )
        hits: list[Hit] = []
        seen: set[str] = set()
        for target in targets:
            key = target_key(target)
            if key in seen:
                continue
            seen.add(key)
            if isinstance(target, ObjectTarget):
                hit = objects.get(key)
            else:
                hit = _inside(target, visible)
            if hit is not None:
                hits.append(hit)
        return Found(hits=hits[: asked.limit], more=len(hits) > asked.limit)

    async def _objects(
        self, asked: Asked, targets: list[ObjectTarget]
    ) -> dict[str, Hit]:
        """Each kind of object asked of the provider that keeps it, by its own rule."""
        wanted: dict[ObjectType, list[str]] = {}
        for target in targets:
            wanted.setdefault(target.object_type, []).append(target.object_id)
        found: dict[str, Hit] = {}
        for object_type, ids in wanted.items():
            provider = next(
                (
                    one
                    for one in self._providers
                    if isinstance(one, Recalls) and object_type in one.recalls
                ),
                None,
            )
            if provider is None:
                continue
            for hit in await provider.recall(asked, object_type, ids):
                found[hit.key] = hit
        return found


def _inside(
    target: ConnectionTarget | NodeTarget,
    visible: dict[uuid.UUID, VisibleConnection],
) -> Hit | None:
    connection = visible.get(target.connector_id)
    if connection is None:
        return None
    if isinstance(target, ConnectionTarget):
        return connection_hit(connection, recalled(connection.name))
    # A switched-off connection is found by its name and nothing in it is
    # named: it is not a source while it is off (D20).
    if not connection.enabled:
        return None
    # Named from the browser's copy, not read again from the source: asking
    # every source would make an empty search no longer instant. A node renamed
    # or gone since keeps its old name here; opening it answers D21's 404.
    return Hit(
        key=target_key(target),
        target=target,
        title=target.name,
        detail=connection.name,
        facts=Facts(kind=target.node_kind),
        match=recalled(target.name),
        access=connection.access,
        open="preferred",
    )
