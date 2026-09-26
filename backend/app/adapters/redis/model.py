"""What a Redis node is as a relation, and where it lies (D170).

Every node the catalog shows has a shape a grid reads: a key its type's
columns, a folder or a database the list of keys in it, a declared table `key`
and its fields. Said as a relation model so the structure view, a CSV and,
next, a reference read it the one way they read a table's. And every node has
a path — database, folders, the node — because an id names it and a person
needs the words.
"""

from app.adapters.catalog import CatalogNode, DatabaseNode
from app.adapters.protocol import NodeNotFound
from app.adapters.redis.keyspace import (
    SEPARATOR,
    NotAKey,
    PlaceRef,
    RedisKeyspace,
    database_id,
    folder_node,
    folders_above,
    is_folder_prefix,
    is_key,
    is_table,
    key_node,
    key_ref,
    place_ref,
    table_node,
)
from app.adapters.redis.shapes import KEY_SHAPES, LISTING, model_columns
from app.adapters.redis.tables import RedisTables
from app.adapters.relation import RelationModel


class RedisModel:
    def __init__(self, keyspace: RedisKeyspace, tables: RedisTables) -> None:
        self._keyspace = keyspace
        self._tables = tables

    async def relation_model(self, node_id: str) -> RelationModel:
        if is_table(node_id):
            return self._tables.model(node_id)
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

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        """Database, folders, then the node; a folder is named, never scanned for."""
        last: CatalogNode | None
        if is_table(node_id):
            place, table = self._tables.declared(node_id)
            database, prefix = place.database, place.prefix
            last = table_node(database, prefix, table)
            folders = folders_above(prefix)[:-1]
        elif is_key(node_id):
            ref = key_ref(node_id)
            facts = await self._keyspace.facts_of(ref.database, ref.name)
            if facts is None:
                raise NodeNotFound(node_id)
            database = ref.database
            last = key_node(database, facts)
            folders = folders_above(ref.name)
        else:
            place = self._place(node_id)
            database, last = place.database, None
            folders = folders_above(place.prefix)
        return [
            await self._database(database),
            *(folder_node(database, prefix) for prefix in folders),
            *([] if last is None else [last]),
        ]

    def _place(self, node_id: str) -> PlaceRef:
        try:
            place = place_ref(node_id)
        except NotAKey:
            raise NodeNotFound(node_id) from None
        if place.prefix and not is_folder_prefix(place.prefix):
            raise NodeNotFound(node_id)
        return place

    async def _database(self, database: int) -> DatabaseNode:
        for node in await self._keyspace.databases():
            if isinstance(node, DatabaseNode) and node.id == database_id(database):
                return node
        raise NodeNotFound(database_id(database))
