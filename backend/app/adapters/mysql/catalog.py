"""Walking the catalog of a MySQL server: databases, then their relations (D229)."""

from collections.abc import Mapping
from typing import Any

from app.adapters.catalog import (
    CatalogNode,
    ReportNode,
    SchemaNode,
    TableNode,
    ViewNode,
)
from app.adapters.content import NodeRepresentation
from app.adapters.frameworks import detect_frameworks
from app.adapters.mysql import ids
from app.adapters.mysql.inspection import RELATION_TYPES, VIEW_TYPES
from app.adapters.mysql.reports import (
    REPORTS,
    SECTION_DESCRIPTION,
    SECTION_ID,
    SECTION_TITLE,
    SystemReport,
    in_section,
    is_section,
    report_for,
)
from app.adapters.mysql.session import MysqlSession
from app.adapters.protocol import AdapterError, NodeNotFound
from app.adapters.words import worded_titles
from app.core.translation import N_, say

# The server's own databases. Read like any other and never changed.
SYSTEM_DATABASES = frozenset({"mysql", "information_schema", "performance_schema", "sys"})

TABLE_REPRESENTATION = NodeRepresentation(kind="table", title=N_("View as table"))
DDL_REPRESENTATION = NodeRepresentation(kind="sql", title=N_("View DDL"))
# A report has no DDL, but the statement it is made of answers the same
# question: what is this, really (D55).
REPORT_SQL_REPRESENTATION = NodeRepresentation(kind="sql", title=N_("View the statement"))

_DATABASES = "SELECT SCHEMA_NAME AS name FROM information_schema.SCHEMATA"

# Every base table's name, for the frameworks a database's tables betray. One
# query for the server rather than one per database.
_TABLE_NAMES = """
SELECT TABLE_SCHEMA AS schema_name, TABLE_NAME AS name
FROM information_schema.TABLES
WHERE TABLE_TYPE = 'BASE TABLE'
"""

_RELATIONS = """
SELECT TABLE_NAME AS name,
       TABLE_TYPE AS table_type,
       TABLE_ROWS AS table_rows,
       DATA_LENGTH + INDEX_LENGTH AS size_bytes
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = %s
"""

_RELATION = """
SELECT TABLE_NAME AS name,
       TABLE_TYPE AS table_type,
       TABLE_ROWS AS table_rows,
       DATA_LENGTH + INDEX_LENGTH AS size_bytes
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
"""

_DATABASE = "SELECT SCHEMA_NAME AS name FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s"


def section_node() -> ReportNode:
    """The server's own section of reports, listed after the databases."""
    return ReportNode(
        id=SECTION_ID,
        name=say(SECTION_TITLE),
        description=say(SECTION_DESCRIPTION),
        has_children=True,
        representations=[],
    )


def report_node(report: SystemReport) -> ReportNode:
    return ReportNode(
        id=report.node_id,
        name=say(report.title),
        description=say(report.description),
        has_children=False,
        representations=worded_titles([TABLE_REPRESENTATION, REPORT_SQL_REPRESENTATION]),
    )


def is_system_database(name: str) -> bool:
    return name.lower() in SYSTEM_DATABASES


def database_node(name: str, tables: list[str]) -> SchemaNode:
    system = is_system_database(name)
    return SchemaNode(
        id=ids.database_id(name),
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
    system = is_system_database(schema)
    representations = worded_titles([TABLE_REPRESENTATION, DDL_REPRESENTATION])
    if str(row["table_type"]) in VIEW_TYPES:
        return ViewNode(
            id=ids.relation_id(schema, name),
            name=name,
            has_children=False,
            is_system=system,
            representations=representations,
            describable=True,
            summarizable=True,
        )
    estimate = row["table_rows"]
    size = row["size_bytes"]
    return TableNode(
        id=ids.relation_id(schema, name),
        name=name,
        has_children=False,
        # TABLE_ROWS is InnoDB's estimate, and MySQL 8 caches it for up to a
        # day: an estimate it is called, and nothing counts the rows (D229).
        row_count_estimate=None if estimate is None else int(estimate),
        size_bytes=None if size is None else int(size),
        is_system=system,
        representations=representations,
        describable=True,
        summarizable=True,
    )


class MysqlCatalog:
    def __init__(self, session: MysqlSession) -> None:
        self._session = session

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        if node_id is None:
            return [*await self._databases(), section_node()]
        if is_section(node_id):
            return [report_node(report) for report in REPORTS]
        if in_section(node_id):
            await self.path_to(node_id)
            return []
        schema, relation = ids.parse(node_id)
        if relation is not None:
            await self.path_to(node_id)
            return []
        rows = await self._session.query(_RELATIONS, (schema,))
        if not rows and not await self._database_exists(schema):
            raise AdapterError("config", say('Database "{name}" does not exist', name=schema))
        # Ordered here rather than by the server: the collation of the catalog
        # differs between MySQL and MariaDB, and with it where `_` sorts.
        return [
            relation_node(schema, row)
            for row in sorted(rows, key=lambda row: str(row["name"]))
            if str(row["table_type"]) in RELATION_TYPES
        ]

    async def _databases(self) -> list[CatalogNode]:
        tables: dict[str, list[str]] = {}
        for row in await self._session.query(_TABLE_NAMES):
            tables.setdefault(str(row["schema_name"]), []).append(str(row["name"]))
        names = [str(row["name"]) for row in await self._session.query(_DATABASES)]
        # The connection's own database first, the way PostgreSQL lists
        # `public` first; the server's own databases last.
        own = self._session.database()
        names.sort(key=lambda name: (name != own, is_system_database(name), name))
        return [database_node(name, tables.get(name, [])) for name in names]

    async def _database_exists(self, schema: str) -> bool:
        return bool(await self._session.query(_DATABASE, (schema,)))

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        """Every node from the root down to node_id, each confirmed on the server."""
        if is_section(node_id):
            return [section_node()]
        if in_section(node_id):
            report = report_for(node_id)
            if report is None:
                raise NodeNotFound(node_id)
            return [section_node(), report_node(report)]
        schema, relation = ids.parse(node_id)
        if not await self._database_exists(schema):
            raise NodeNotFound(node_id)
        tables = [
            str(row["name"])
            for row in await self._session.query(_TABLE_NAMES)
            if str(row["schema_name"]) == schema
        ]
        path: list[CatalogNode] = [database_node(schema, tables)]
        if relation is None:
            return path
        rows = await self._session.query(_RELATION, (schema, relation))
        if not rows or str(rows[0]["table_type"]) not in RELATION_TYPES:
            raise NodeNotFound(node_id)
        path.append(relation_node(schema, rows[0]))
        return path
