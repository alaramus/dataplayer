from collections.abc import Mapping
from typing import Any

from app.adapters.catalog import (
    CatalogNode,
    ColumnNode,
    SchemaNode,
    TableNode,
    ViewNode,
)
from app.adapters.postgres.session import PostgresSession
from app.adapters.protocol import AdapterError, NodeNotFound

_SYSTEM_SCHEMAS = ("information_schema",)


def _is_system_schema(name: str) -> bool:
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
            return await self._list_schemas()
        schema, _, table = node_id.partition(".")
        if table:
            return await self._list_columns(schema, table)
        return await self._list_relations(schema)

    async def _list_schemas(self) -> list[CatalogNode]:
        rows = await self._session.query(
            """
            SELECT nspname AS name
            FROM pg_namespace
            WHERE nspname NOT LIKE 'pg_toast%'
              AND nspname NOT LIKE 'pg_temp%'
            ORDER BY nspname
            """
        )
        return [
            SchemaNode(
                id=row["name"],
                name=row["name"],
                has_children=True,
                is_system=_is_system_schema(row["name"]),
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

    async def _list_columns(self, schema: str, table: str) -> list[CatalogNode]:
        rows = await self._session.query(
            """
            SELECT a.attname AS name,
                   format_type(a.atttypid, a.atttypmod) AS data_type,
                   NOT a.attnotnull AS nullable,
                   COALESCE(i.indisprimary, false) AS primary_key
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            LEFT JOIN pg_index i
                   ON i.indrelid = c.oid
                  AND a.attnum = ANY (i.indkey)
                  AND i.indisprimary
            WHERE n.nspname = %s AND c.relname = %s
              AND a.attnum > 0 AND NOT a.attisdropped
            ORDER BY a.attnum
            """,
            (schema, table),
        )
        if not rows:
            raise AdapterError("config", f'Relation "{schema}.{table}" does not exist')

        return [
            ColumnNode(
                id=f"{schema}.{table}.{row['name']}",
                name=row["name"],
                data_type=row["data_type"],
                nullable=row["nullable"],
                primary_key=row["primary_key"],
            )
            for row in rows
        ]

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        """Every node from the root down to node_id, the node itself last.

        Taken apart by the same `partition` that `list_children` uses, so the
        two cannot disagree about what an id means. Each step is confirmed
        against the server rather than assumed from the shape of the string:
        an id survives in a tab across a `DROP TABLE`, and the caller has to
        be able to tell "it moved" from "it is gone".
        """
        schema, _, rest = node_id.partition(".")
        relation, _, column = rest.partition(".")

        path: list[CatalogNode] = [await self._schema_node(schema, node_id)]
        if not relation:
            return path

        path.append(await self._relation_node(schema, relation, node_id))
        if not column:
            return path

        path.append(await self._column_node(schema, relation, column, node_id))
        return path

    async def _schema_node(self, schema: str, node_id: str) -> CatalogNode:
        if not await self._schema_exists(schema):
            raise NodeNotFound(node_id)
        return SchemaNode(
            id=schema,
            name=schema,
            has_children=True,
            is_system=_is_system_schema(schema),
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

    async def _column_node(
        self, schema: str, relation: str, column: str, node_id: str
    ) -> CatalogNode:
        columns = await self._list_columns(schema, relation)
        for node in columns:
            if node.name == column:
                return node
        raise NodeNotFound(node_id)

    async def _schema_exists(self, schema: str) -> bool:
        rows = await self._session.query(
            "SELECT 1 FROM pg_namespace WHERE nspname = %s", (schema,)
        )
        return bool(rows)


def _relation_of(schema: str, name: str, row: Mapping[str, Any]) -> CatalogNode:
    """One relation as a node, from a row that names its kind and its size.

    Shared by the listing and by `path_to` so a table cannot be described one
    way when walked into and another way when pointed at.
    """
    is_system = _is_system_schema(schema)
    if row["kind"] in ("v", "m"):
        return ViewNode(
            id=f"{schema}.{name}",
            name=name,
            has_children=True,
            is_materialized=row["kind"] == "m",
            is_system=is_system,
        )
    estimate = int(row["row_estimate"])
    return TableNode(
        id=f"{schema}.{name}",
        name=name,
        has_children=True,
        # reltuples is -1 until the table has been analysed.
        row_count_estimate=estimate if estimate >= 0 else None,
        size_bytes=row["size_bytes"],
        is_system=is_system,
    )
