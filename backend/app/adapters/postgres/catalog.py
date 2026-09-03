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
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.system_reports import (
    REPORTS,
    SECTION_DESCRIPTION,
    SECTION_ID,
    SECTION_TITLE,
    SystemReport,
    is_section,
    report_for,
)
from app.adapters.protocol import AdapterError, NodeNotFound

_SYSTEM_SCHEMAS = ("information_schema",)
TABLE_REPRESENTATION = NodeRepresentation(kind="table", title="View as table")
DDL_REPRESENTATION = NodeRepresentation(kind="sql", title="View DDL")
# A report has no DDL — there is nothing on the server to recreate — but it
# does have the statement it is made of, and that is the same question a
# person asks of a table when they open its DDL: what is this, really.
REPORT_SQL_REPRESENTATION = NodeRepresentation(kind="sql", title="View the statement")


def is_system_schema(name: str) -> bool:
    """Whether a schema belongs to the server rather than to the reader.

    In one place because three modules ask it: the catalog to mark a
    node, the relation model to refuse a structure change, and fetch to
    refuse a write (D54).
    """
    return name.startswith("pg_") or name in _SYSTEM_SCHEMAS


class PostgresCatalog:
    """Walking the catalog of a PostgreSQL server.

    Built on a session rather than owning a connection: what a caller wants and
    how the server is reached are separate concerns, and separate files.
    """

    def __init__(self, session: PostgresSession) -> None:
        self._session = session

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        if node_id is None:
            return [*await self._list_schemas(), _section_node()]
        if is_section(node_id):
            return [_report_node(report) for report in REPORTS]
        return await self._list_relations(node_id)

    async def _list_schemas(self) -> list[CatalogNode]:
        rows = await self._session.query(
            """
            SELECT nspname AS name
            FROM pg_namespace
            WHERE nspname NOT LIKE 'pg_toast%'
              AND nspname NOT LIKE 'pg_temp%'
            ORDER BY (nspname <> 'public'), nspname
            """
        )
        return [
            SchemaNode(
                id=row["name"],
                name=row["name"],
                has_children=True,
                is_system=is_system_schema(row["name"]),
                representations=[],
            )
            for row in rows
        ]

    async def _list_relations(self, schema: str) -> list[CatalogNode]:
        rows = await self._session.query(
            """
            SELECT c.relname AS name,
                   c.relkind AS kind,
                   c.reltuples AS row_estimate,
                   pg_total_relation_size(c.oid) AS size_bytes
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = %s AND c.relkind IN ('r', 'p', 'v', 'm')
            ORDER BY c.relname
            """,
            (schema,),
        )
        if not rows and not await self._schema_exists(schema):
            raise AdapterError("config", f'Schema "{schema}" does not exist')

        return [_relation_of(schema, row["name"], row) for row in rows]

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        """Every node from the root down to node_id, the node itself last.

        Taken apart by the same `partition` that `list_children` uses, so the
        two cannot disagree about what an id means. Each step is confirmed
        against the server rather than assumed from the shape of the string:
        an id survives in a tab across a `DROP TABLE`, and the caller has to
        be able to tell "it moved" from "it is gone".
        """
        if is_section(node_id):
            return [_section_node()]
        report = report_for(node_id)
        if report is not None:
            return [_section_node(), _report_node(report)]
        # An id in the reports' namespace naming no report is gone rather than
        # a relation to look for: no schema can be called `pg_dataplayer`,
        # because PostgreSQL reserves the prefix.
        if node_id.startswith(f"{SECTION_ID}."):
            raise NodeNotFound(node_id)

        schema, _, relation = node_id.partition(".")

        path: list[CatalogNode] = [await self._schema_node(schema, node_id)]
        if not relation:
            return path

        path.append(await self._relation_node(schema, relation, node_id))
        return path

    async def _schema_node(self, schema: str, node_id: str) -> CatalogNode:
        if not await self._schema_exists(schema):
            raise NodeNotFound(node_id)
        return SchemaNode(
            id=schema,
            name=schema,
            has_children=True,
            is_system=is_system_schema(schema),
            representations=[],
        )

    async def _relation_node(
        self, schema: str, relation: str, node_id: str
    ) -> CatalogNode:
        """One relation, described exactly as the listing of its schema would.

        Asked for by name rather than found in the listing: a schema of ten
        thousand tables would otherwise be read whole to describe one of them.
        """
        rows = await self._session.query(
            """
            SELECT c.relkind AS kind,
                   c.reltuples AS row_estimate,
                   pg_total_relation_size(c.oid) AS size_bytes
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = %s AND c.relname = %s
              AND c.relkind IN ('r', 'p', 'v', 'm')
            """,
            (schema, relation),
        )
        if not rows:
            raise NodeNotFound(node_id)

        row = rows[0]
        return _relation_of(schema, relation, row)

    async def _schema_exists(self, schema: str) -> bool:
        rows = await self._session.query(
            "SELECT 1 FROM pg_namespace WHERE nspname = %s", (schema,)
        )
        return bool(rows)


def _section_node() -> ReportNode:
    """The connector's own section of reports, listed beside its schemas.

    A grouping like a schema is, and last, because a reader came for their own
    data. What it holds is fixed in code, so nothing is asked of the server to
    say that it has children (D55).
    """
    return ReportNode(
        id=SECTION_ID,
        name=SECTION_TITLE,
        description=SECTION_DESCRIPTION,
        has_children=True,
        representations=[],
    )


def _report_node(report: SystemReport) -> ReportNode:
    return ReportNode(
        id=report.node_id,
        name=report.title,
        description=report.description,
        has_children=False,
        representations=[TABLE_REPRESENTATION, REPORT_SQL_REPRESENTATION],
    )


def _relation_of(schema: str, name: str, row: Mapping[str, Any]) -> CatalogNode:
    """One relation as a node, from a row that names its kind and its size.

    Shared by the listing and by `path_to` so a table cannot be described one
    way when walked into and another way when pointed at.
    """
    is_system = is_system_schema(schema)
    if row["kind"] in ("v", "m"):
        return ViewNode(
            id=f"{schema}.{name}",
            name=name,
            has_children=False,
            is_materialized=row["kind"] == "m",
            is_system=is_system,
            representations=[TABLE_REPRESENTATION, DDL_REPRESENTATION],
            describable=True,
        )
    estimate = int(row["row_estimate"])
    return TableNode(
        id=f"{schema}.{name}",
        name=name,
        has_children=False,
        # reltuples is -1 until the table has been analysed.
        row_count_estimate=estimate if estimate >= 0 else None,
        size_bytes=row["size_bytes"],
        is_system=is_system,
        representations=[TABLE_REPRESENTATION, DDL_REPRESENTATION],
        describable=True,
    )
