import asyncio
import time
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.adapters.catalog import (
    CatalogNode,
    ColumnNode,
    SchemaNode,
    TableNode,
    ViewNode,
)
from app.adapters.postgres.options import PostgresOptions
from app.adapters.protocol import AdapterError, ConnectionCheckResult, ErrorKind
from app.adapters.registry import register

CHECK_TIMEOUT_SECONDS = 5.0

# Order matters: `role "x" does not exist` matches both sets, and it is a
# credentials problem rather than a configuration one.
_AUTH_MARKERS = ("password", "authentication", "role", "permission denied")
_CONFIG_MARKERS = ("does not exist",)

_SYSTEM_SCHEMAS = ("information_schema",)


def _is_system_schema(name: str) -> bool:
    return name.startswith("pg_") or name in _SYSTEM_SCHEMAS


def _classify(
    exc: BaseException, *, fallback_message: str = "Connection failed"
) -> tuple[ErrorKind, str]:
    """Reduce a driver exception to a safe (kind, message) pair.

    The exception text never reaches the caller: psycopg includes the
    connection string, password and all, in it.

    fallback_message covers everything that is not a connection problem. It is
    a parameter because "Connection failed" is misleading when the connection
    was fine and the query was not.
    """
    # ConnectionTimeout subclasses OperationalError, so it is checked first.
    if isinstance(exc, TimeoutError | psycopg.errors.ConnectionTimeout):
        return "timeout", "Connection timed out"
    if isinstance(exc, psycopg.OperationalError):
        text = str(exc).lower()
        if any(marker in text for marker in _AUTH_MARKERS):
            return "auth", "Authentication failed"
        if any(marker in text for marker in _CONFIG_MARKERS):
            return "config", "Database does not exist"
        return "network", "Could not reach the database server"
    return "unknown", fallback_message


class PostgresAdapter:
    def __init__(self, options: PostgresOptions) -> None:
        self._options = options

    def _conninfo(self) -> str:
        options = self._options
        return psycopg.conninfo.make_conninfo(
            host=options.host,
            port=options.port,
            dbname=options.database,
            user=options.user,
            password=options.password.get_secret_value(),
            # Without this psycopg waits about two minutes on an unreachable
            # host. asyncio.wait_for below would drop the wait, but the
            # connection would keep hanging inside the driver, so the limit is
            # set on both sides.
            connect_timeout=int(CHECK_TIMEOUT_SECONDS),
        )

    async def check_connection(self) -> ConnectionCheckResult:
        started = time.perf_counter()
        try:
            connection = await asyncio.wait_for(
                psycopg.AsyncConnection.connect(self._conninfo()),
                CHECK_TIMEOUT_SECONDS,
            )
            async with connection:
                await connection.execute("SELECT 1")
        except Exception as exc:
            error_kind, message = _classify(exc)
            return ConnectionCheckResult(
                ok=False, message=message, error_kind=error_kind
            )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return ConnectionCheckResult(
            ok=True, message="Connection successful", latency_ms=latency_ms
        )

    async def _query(
        self, sql: str, params: tuple[object, ...] | None = None
    ) -> list[dict[str, Any]]:
        """Run a read-only catalog query.

        params stays None when there is nothing to bind: psycopg treats a
        supplied sequence, even an empty one, as a signal that the statement is
        parameterised, and then a literal % — as in LIKE 'pg_toast%' — is read
        as a placeholder.
        """
        try:
            connection = await asyncio.wait_for(
                psycopg.AsyncConnection.connect(self._conninfo()),
                CHECK_TIMEOUT_SECONDS,
            )
            async with connection:
                cursor = await connection.cursor(row_factory=dict_row).execute(
                    sql, params
                )
                return await cursor.fetchall()
        except Exception as exc:
            error_kind, message = _classify(exc, fallback_message="Catalog query failed")
            raise AdapterError(error_kind, message) from None

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        if node_id is None:
            return await self._list_schemas()
        schema, _, table = node_id.partition(".")
        if table:
            return await self._list_columns(schema, table)
        return await self._list_relations(schema)

    async def _list_schemas(self) -> list[CatalogNode]:
        rows = await self._query(
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
        rows = await self._query(
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

        nodes: list[CatalogNode] = []
        for row in rows:
            is_system = _is_system_schema(schema)
            if row["kind"] in ("v", "m"):
                nodes.append(
                    ViewNode(
                        id=f"{schema}.{row['name']}",
                        name=row["name"],
                        has_children=True,
                        is_materialized=row["kind"] == "m",
                        is_system=is_system,
                    )
                )
            else:
                estimate = int(row["row_estimate"])
                nodes.append(
                    TableNode(
                        id=f"{schema}.{row['name']}",
                        name=row["name"],
                        has_children=True,
                        # reltuples is -1 until the table has been analysed.
                        row_count_estimate=estimate if estimate >= 0 else None,
                        size_bytes=row["size_bytes"],
                        is_system=is_system,
                    )
                )
        return nodes

    async def _list_columns(self, schema: str, table: str) -> list[CatalogNode]:
        rows = await self._query(
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

    async def _schema_exists(self, schema: str) -> bool:
        rows = await self._query(
            "SELECT 1 FROM pg_namespace WHERE nspname = %s", (schema,)
        )
        return bool(rows)


@register(name="postgres", title="PostgreSQL", options_schema=PostgresOptions)
def _build(options: PostgresOptions) -> PostgresAdapter:
    return PostgresAdapter(options)
