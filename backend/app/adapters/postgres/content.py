"""Bounded, read-only SQL about one node: a relation's DDL, or a report's own
statement.

Two things and not one, because a report has no DDL — there is nothing on the
server to recreate — and the question a person asks by opening it is the same
one they ask of a table's DDL: what is this, really. The statement is written
in this repository (D55), so answering costs no round trip.
"""

import textwrap
from collections.abc import Mapping, Sequence
from typing import Any

from psycopg import sql

from app.adapters.content import ContentRequest, ContentResult, SqlContent
from app.adapters.postgres.relation_context import PostgresRelationContext
from app.adapters.postgres.report_registry import resolve_report
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.system_reports import SystemReport
from app.adapters.protocol import NodeNotFound
from app.core.translation import say

MAX_DDL_BYTES = 256 * 1024
# A single catalog expression is clipped before it crosses the connection.
# PostgreSQL's left() counts characters rather than bytes, so this is the
# smallest character limit that still permits every valid UTF-8 answer up to
# MAX_DDL_BYTES; the final byte prefix is the authoritative response bound.
MAX_DDL_FRAGMENT_CHARACTERS = MAX_DDL_BYTES

_RELATION = """
SELECT c.relkind AS kind,
       c.relpersistence AS persistence,
       c.relispartition AS is_partition,
       n.nspname AS schema_name,
       c.relname AS relation_name,
       pg_get_userbyid(c.relowner) AS owner,
       left(obj_description(c.oid, 'pg_class'), %s) AS comment,
       left(pg_get_viewdef(c.oid, true), %s) AS view_definition,
       left(pg_get_partkeydef(c.oid), %s) AS partition_key,
       pn.nspname AS parent_schema,
       pc.relname AS parent_relation,
       left(pg_get_expr(c.relpartbound, c.oid, true), %s) AS partition_bounds
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_inherits inh ON inh.inhrelid = c.oid
LEFT JOIN pg_class pc ON pc.oid = inh.inhparent
LEFT JOIN pg_namespace pn ON pn.oid = pc.relnamespace
WHERE n.nspname = %s
  AND c.relname = %s
  AND c.relkind IN ('r', 'p', 'v', 'm')
LIMIT 1
"""

_COLUMNS = """
SELECT a.attname AS name,
       format_type(a.atttypid, a.atttypmod) AS sql_type,
       a.attnotnull AS not_null,
       a.attidentity AS identity,
       a.attgenerated AS generated,
       left(pg_get_expr(ad.adbin, ad.adrelid, true), %s) AS expression,
       cn.nspname AS collation_schema,
       co.collname AS collation_name
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_attrdef ad ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum
LEFT JOIN pg_collation co ON co.oid = a.attcollation AND co.collname <> 'default'
LEFT JOIN pg_namespace cn ON cn.oid = co.collnamespace
WHERE n.nspname = %s
  AND c.relname = %s
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum
"""

_CONSTRAINTS = """
SELECT con.conname AS name,
       left(pg_get_constraintdef(con.oid, true), %s) AS definition
FROM pg_constraint con
JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = %s
  AND c.relname = %s
ORDER BY con.conname
"""

_INDEXES = """
SELECT left(pg_get_indexdef(ix.indexrelid), %s) AS definition
FROM pg_index ix
JOIN pg_class c ON c.oid = ix.indrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = %s
  AND c.relname = %s
  AND NOT EXISTS (
      SELECT 1 FROM pg_constraint con WHERE con.conindid = ix.indexrelid
  )
  AND NOT EXISTS (
      SELECT 1 FROM pg_inherits inh WHERE inh.inhrelid = ix.indexrelid
  )
ORDER BY ix.indexrelid
"""


class PostgresContent:
    """Issue a relation's recreate-oriented DDL from server catalog facts."""

    def __init__(
        self,
        session: PostgresSession,
        relation_context: PostgresRelationContext | None = None,
    ) -> None:
        self._session = session
        self._relation_context = relation_context or PostgresRelationContext(session)

    async def read_content(self, request: ContentRequest) -> ContentResult:
        if request.representation != "sql":
            raise ValueError(
                say('This PostgreSQL source does not offer the "{representation}" content representation', representation=request.representation)
            )
        report = await resolve_report(self._session, request.node_id)
        if report is not None:
            return _report_statement(report)

        schema, separator, relation = request.node_id.partition(".")
        if not separator or not schema or not relation:
            raise ValueError(
                say('"{node_id}" is not a relation: expected schema.relation', node_id=request.node_id)
            )

        context = await self._relation_context.schema(schema, relation)
        refused = context.structured_operations_reason(relation)
        if refused is not None:
            raise ValueError(say("{refused}; reconstructed DDL is unavailable", refused=refused))

        rows = await self._session.query(
            _RELATION,
            (
                MAX_DDL_FRAGMENT_CHARACTERS,
                MAX_DDL_FRAGMENT_CHARACTERS,
                MAX_DDL_FRAGMENT_CHARACTERS,
                MAX_DDL_FRAGMENT_CHARACTERS,
                schema,
                relation,
            ),
        )
        if not rows:
            raise NodeNotFound(request.node_id)
        metadata = rows[0]

        kind = str(metadata["kind"])
        columns: list[dict[str, Any]] = []
        constraints: list[dict[str, Any]] = []
        if kind in {"r", "p"} and not bool(metadata.get("is_partition")):
            columns = await self._session.query(
                _COLUMNS,
                (MAX_DDL_FRAGMENT_CHARACTERS, schema, relation),
            )
            constraints = await self._session.query(
                _CONSTRAINTS,
                (MAX_DDL_FRAGMENT_CHARACTERS, schema, relation),
            )

        indexes = (
            await self._session.query(
                _INDEXES,
                (MAX_DDL_FRAGMENT_CHARACTERS, schema, relation),
            )
            if kind != "v"
            else []
        )
        ddl = _relation_ddl(metadata, columns, constraints, indexes)
        text, truncated = _bounded_utf8(ddl, MAX_DDL_BYTES)
        return SqlContent(
            text=text,
            truncated=truncated,
            notice=(
                say("This DDL is larger than 256 KB; only its beginning is shown.")
                if truncated
                else None
            ),
        )


def _report_statement(report: SystemReport) -> ContentResult:
    """What the report runs, as it is written here.

    Dedented rather than passed on as it sits in the source, where every line
    carries the indentation of the Python file it lives in.
    """
    return SqlContent(text=textwrap.dedent(report.statement.as_string()).strip())


def _relation_ddl(
    metadata: Mapping[str, Any],
    columns: Sequence[Mapping[str, Any]],
    constraints: Sequence[Mapping[str, Any]],
    indexes: Sequence[Mapping[str, Any]],
) -> str:
    """Compose SQL only from names and expressions PostgreSQL described."""

    schema = str(metadata["schema_name"])
    name = str(metadata["relation_name"])
    qualified = _identifier(schema, name)
    kind = str(metadata["kind"])

    if kind in {"v", "m"}:
        materialized = "MATERIALIZED " if kind == "m" else ""
        definition = str(metadata.get("view_definition") or "")
        create = f"CREATE {materialized}VIEW {qualified} AS\n{definition.rstrip(';')};"
    elif bool(metadata.get("is_partition")):
        parent = _identifier(
            str(metadata["parent_schema"]), str(metadata["parent_relation"])
        )
        bounds = str(metadata.get("partition_bounds") or "")
        create = f"CREATE TABLE {qualified} PARTITION OF {parent}\n{bounds};"
    else:
        persistence = {
            "u": "UNLOGGED ",
            "t": "TEMPORARY ",
        }.get(str(metadata.get("persistence") or ""), "")
        definitions = [
            *(_column_definition(column) for column in columns),
            *(_constraint_definition(constraint) for constraint in constraints),
        ]
        body = ",\n".join(f"    {definition}" for definition in definitions)
        create = f"CREATE {persistence}TABLE {qualified} (\n{body}\n)"
        partition_key = metadata.get("partition_key")
        if kind == "p" and partition_key:
            create += f"\nPARTITION BY {partition_key}"
        create += ";"

    statements = [create]
    statements.extend(
        f"{str(index['definition']).rstrip(';')};"
        for index in indexes
        if index.get("definition")
    )

    owner = metadata.get("owner")
    if owner:
        statements.append(
            f"ALTER {_object_kind(kind)} {qualified} "
            f"OWNER TO {_identifier(str(owner))};"
        )
    comment = metadata.get("comment")
    if comment is not None:
        statements.append(
            f"COMMENT ON {_object_kind(kind)} {qualified} "
            f"IS {_literal(str(comment))};"
        )
    return "\n\n".join(statements) + "\n"


def _column_definition(column: Mapping[str, Any]) -> str:
    definition = f"{_identifier(str(column['name']))} {column['sql_type']}"
    collation = column.get("collation_name")
    collation_schema = column.get("collation_schema")
    if collation and collation_schema:
        definition += f" COLLATE {_identifier(str(collation_schema), str(collation))}"

    identity = str(column.get("identity") or "")
    generated = str(column.get("generated") or "")
    expression = column.get("expression")
    if identity == "a":
        definition += " GENERATED ALWAYS AS IDENTITY"
    elif identity == "d":
        definition += " GENERATED BY DEFAULT AS IDENTITY"
    elif generated in {"s", "v"} and expression:
        storage = "STORED" if generated == "s" else "VIRTUAL"
        definition += f" GENERATED ALWAYS AS ({expression}) {storage}"
    elif expression:
        definition += f" DEFAULT {expression}"
    if bool(column.get("not_null")):
        definition += " NOT NULL"
    return definition


def _constraint_definition(constraint: Mapping[str, Any]) -> str:
    return (
        f"CONSTRAINT {_identifier(str(constraint['name']))} "
        f"{constraint['definition']}"
    )


def _object_kind(kind: str) -> str:
    if kind == "m":
        return "MATERIALIZED VIEW"
    if kind == "v":
        return "VIEW"
    return "TABLE"


def _identifier(*parts: str) -> str:
    return sql.Identifier(*parts).as_string()


def _literal(value: str) -> str:
    return sql.Literal(value).as_string()


def _bounded_utf8(value: str, limit: int) -> tuple[str, bool]:
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value, False
    return encoded[:limit].decode("utf-8", errors="ignore"), True
