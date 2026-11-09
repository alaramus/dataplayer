"""Walking the catalog of a cluster: keyspaces, then their tables and views (D341)."""

from app.adapters.cassandra.inspection import (
    Inspector,
    RelationFacts,
    is_system_keyspace,
)
from app.adapters.cassandra.session import CassandraSession
from app.adapters.catalog import CatalogNode, SchemaNode, TableNode, ViewNode
from app.adapters.content import NodeRepresentation
from app.adapters.database_ids import database_id, parse, relation_id
from app.adapters.frameworks import detect_frameworks
from app.adapters.protocol import AdapterError, NodeNotFound
from app.adapters.words import worded_titles
from app.core.translation import N_, say

TABLE_REPRESENTATION = NodeRepresentation(kind="table", title=N_("View as table"))
DDL_REPRESENTATION = NodeRepresentation(kind="sql", title=N_("View DDL"))


def keyspace_node(name: str, tables: list[str], *, system: bool) -> SchemaNode:
    return SchemaNode(
        id=database_id(name),
        name=name,
        term="keyspace",
        has_children=True,
        is_system=system,
        representations=[],
        frameworks=[] if system else detect_frameworks(tables),
    )


def relation_node(facts: RelationFacts) -> CatalogNode:
    """One relation as a node; shared by the listing and `path_to`."""
    system = facts.is_system
    representations = worded_titles([TABLE_REPRESENTATION, DDL_REPRESENTATION])
    node_id = relation_id(facts.keyspace, facts.name)
    if facts.is_view:
        return ViewNode(
            id=node_id,
            name=facts.name,
            has_children=False,
            is_materialized=True,
            is_system=system,
            representations=representations,
            describable=True,
            summarizable=True,
        )
    return TableNode(
        id=node_id,
        name=facts.name,
        has_children=False,
        is_system=system,
        representations=representations,
        describable=True,
        summarizable=True,
    )


class CassandraCatalog:
    def __init__(self, session: CassandraSession, inspector: Inspector) -> None:
        self._session = session
        self._inspector = inspector

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        if node_id is None:
            return await self._keyspaces()
        keyspace, relation = parse(node_id)
        if relation is not None:
            await self.path_to(node_id)
            return []
        place = await self._inspector.keyspace(keyspace)
        if place is None:
            raise AdapterError(
                "config", say('Keyspace "{name}" does not exist', name=keyspace)
            )
        found = await self._inspector.relations(keyspace, place[1], structure=False)
        return [relation_node(found[name]) for name in sorted(found)]

    async def _keyspaces(self) -> list[CatalogNode]:
        names = await self._inspector.keyspaces()
        own = self._session.keyspace()
        scylla = await self._inspector.scylla()
        # The connection's own keyspace first, the server's own last.
        names.sort(
            key=lambda item: (
                item[0] != own,
                is_system_keyspace(item[0], scylla=scylla),
                item[0],
            )
        )
        tables = await self._inspector.table_names()
        return [
            keyspace_node(
                name,
                tables.get(name, []),
                system=is_system_keyspace(name, scylla=scylla),
            )
            for name, _ in names
        ]

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        """Every node from the root down to node_id, each confirmed on the server."""
        keyspace, relation = parse(node_id)
        place = await self._inspector.keyspace(keyspace)
        if place is None:
            raise NodeNotFound(node_id)
        tables = (await self._inspector.table_names()).get(keyspace, [])
        system = is_system_keyspace(keyspace, scylla=await self._inspector.scylla())
        path: list[CatalogNode] = [keyspace_node(keyspace, tables, system=system)]
        if relation is None:
            return path
        found = await self._inspector.relations(
            keyspace, place[1], structure=False, names=[relation]
        )
        if relation not in found:
            raise NodeNotFound(node_id)
        path.append(relation_node(found[relation]))
        return path
