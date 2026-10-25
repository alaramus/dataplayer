"""Walking the catalog of a ClickHouse server: databases, then their relations (D267)."""

from collections.abc import Mapping
from typing import Any

from app.adapters.catalog import CatalogNode, SchemaNode, TableNode, ViewNode
from app.adapters.clickhouse.inspection import VIEW_ENGINES, relation_rows
from app.adapters.clickhouse.session import ClickhouseSession
from app.adapters.content import NodeRepresentation
from app.adapters.database_ids import database_id, parse, relation_id
from app.adapters.frameworks import detect_frameworks
from app.adapters.protocol import AdapterError, NodeNotFound
from app.adapters.words import worded_titles
from app.core.translation import N_, say

# The server's own databases. Read like any other and never changed.
SYSTEM_DATABASES = frozenset({"system", "information_schema", "INFORMATION_SCHEMA"})

TABLE_REPRESENTATION = NodeRepresentation(kind="table", title=N_("View as table"))
DDL_REPRESENTATION = NodeRepresentation(kind="sql", title=N_("View DDL"))

_DATABASES = "SELECT name FROM system.databases"

_DATABASE = "SELECT name FROM system.databases WHERE name = {database:String}"

# Every table's name, for the frameworks a database's tables betray. One query
# for the server rather than one per database.
_TABLE_NAMES = """
SELECT database, name FROM system.tables
WHERE NOT is_temporary AND engine NOT IN ('View', 'MaterializedView')
"""

_RELATIONS = """
SELECT name, engine, total_rows, total_bytes
FROM system.tables
WHERE database = {database:String} AND NOT is_temporary
"""


# Where a materialized view without `TO` keeps its rows. Read through the
# view, which is the thing a person made, so not listed beside it.
_INNER_PREFIXES = (".inner.", ".inner_id.")


def is_inner_table(name: str) -> bool:
    return name.startswith(_INNER_PREFIXES)


def is_system_database(name: str) -> bool:
    return name in SYSTEM_DATABASES


def database_node(name: str, tables: list[str]) -> SchemaNode:
    system = is_system_database(name)
    return SchemaNode(
        id=database_id(name),
        name=name,
        term="database",
        has_children=True,
        is_system=system,
        representations=[],
        frameworks=[] if system else detect_frameworks(tables),
    )


def relation_node(schema: str, row: Mapping[str, Any]) -> CatalogNode:
    """One relation as a node; shared by the listing and `path_to`."""
    name = str(row["name"])
    engine = str(row["engine"])
    system = is_system_database(schema)
    representations = worded_titles([TABLE_REPRESENTATION, DDL_REPRESENTATION])
    if engine in VIEW_ENGINES:
        return ViewNode(
            id=relation_id(schema, name),
            name=name,
            has_children=False,
            is_materialized=engine == "MaterializedView",
            is_system=system,
            representations=representations,
            describable=True,
            summarizable=True,
        )
    rows = row["total_rows"]
    size = row["total_bytes"]
    return TableNode(
        id=relation_id(schema, name),
        name=name,
        has_children=False,
        row_count_estimate=None if rows is None else int(rows),
        size_bytes=None if size is None else int(size),
        is_system=system,
        representations=representations,
        describable=True,
        summarizable=True,
    )


class ClickhouseCatalog:
    def __init__(self, session: ClickhouseSession) -> None:
        self._session = session

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        if node_id is None:
            return await self._databases()
        schema, relation = parse(node_id)
        if relation is not None:
            await self.path_to(node_id)
            return []
        rows = await self._session.query(_RELATIONS, {"database": schema})
        if not rows and not await self._database_exists(schema):
            raise AdapterError("config", say('Database "{name}" does not exist', name=schema))
        return [
            relation_node(schema, row)
            for row in sorted(rows, key=lambda row: str(row["name"]))
            if not is_inner_table(str(row["name"]))
        ]

    async def _databases(self) -> list[CatalogNode]:
        tables: dict[str, list[str]] = {}
        for row in await self._session.query(_TABLE_NAMES):
            tables.setdefault(str(row["database"]), []).append(str(row["name"]))
        names = [str(row["name"]) for row in await self._session.query(_DATABASES)]
        # The connection's own database first, the way PostgreSQL lists
        # `public` first; the server's own databases last.
        own = self._session.database() or "default"
        names.sort(key=lambda name: (name != own, is_system_database(name), name))
        return [database_node(name, tables.get(name, [])) for name in names]

    async def _database_exists(self, schema: str) -> bool:
        return bool(await self._session.query(_DATABASE, {"database": schema}))

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        """Every node from the root down to node_id, each confirmed on the server."""
        schema, relation = parse(node_id)
        if not await self._database_exists(schema):
            raise NodeNotFound(node_id)
        tables = [
            str(row["name"])
            for row in await self._session.query(_TABLE_NAMES)
            if str(row["database"]) == schema
        ]
        path: list[CatalogNode] = [database_node(schema, tables)]
        if relation is None:
            return path
        found = await relation_rows(self._session, schema, [relation])
        if relation not in found:
            raise NodeNotFound(node_id)
        path.append(relation_node(schema, found[relation]))
        return path
