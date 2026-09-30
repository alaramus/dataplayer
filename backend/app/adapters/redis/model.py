"""The columns Redis exports for a key, folder or database (D171).

The CSV transfer uses the same column names as Redis's row view.
"""

from app.adapters.protocol import NodeNotFound
from app.adapters.redis.keyspace import (
    SEPARATOR,
    NotAKey,
    PlaceRef,
    RedisKeyspace,
    is_folder_prefix,
    is_key,
    key_ref,
    place_ref,
)
from app.adapters.redis.shapes import KEY_SHAPES, LISTING, model_columns
from app.adapters.relation import RelationModel


class RedisModel:
    def __init__(self, keyspace: RedisKeyspace) -> None:
        self._keyspace = keyspace

    async def relation_model(self, node_id: str) -> RelationModel:
        if is_key(node_id):
            ref = key_ref(node_id)
            facts = await self._keyspace.facts_of(ref.database, ref.name)
            if facts is None:
                raise NodeNotFound(node_id)
            return RelationModel(
                node_id=node_id,
                name=ref.name,
                kind="key",
                row_estimate=facts.length,
                columns=model_columns(KEY_SHAPES[facts.data_type]),
            )
        place = self._place(node_id)
        return RelationModel(
            node_id=node_id,
            # Named as a file would be, since that is where it goes: `session:`
            # is `session`, and a database is `db0`.
            name=place.prefix.rstrip(SEPARATOR) or f"db{place.database}",
            kind="key_listing",
            columns=model_columns(LISTING),
        )

    def _place(self, node_id: str) -> PlaceRef:
        try:
            place = place_ref(node_id)
        except NotAKey:
            raise NodeNotFound(node_id) from None
        if place.prefix and not is_folder_prefix(place.prefix):
            raise NodeNotFound(node_id)
        return place
