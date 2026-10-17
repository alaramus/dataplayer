"""Plan turning an empty ordinary table into a hypertable without converting it."""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from psycopg import sql

from app.adapters.actions import ActionRefused
from app.adapters.postgres.inspection import PostgresReader
from app.adapters.postgres.timescale.api import (
    RoutineShape,
    extension_routine,
    extension_type,
)
from app.adapters.postgres.timescale.plans import (
    ConversionColumn,
    ConversionPlan,
    ConversionStrategy,
    ConversionTarget,
    TimeDuration,
)
from app.adapters.postgres.timescale.profile import discover, require_available
from app.adapters.postgres.timescale.report_access import require_public_view
from app.adapters.protocol import AdapterError
from app.core.translation import say

_SUBDAY = frozenset({"second", "minute", "hour"})
_TIME_TYPES = frozenset({"timestamp without time zone", "timestamp with time zone", "date"})
_INDEX_CEILING = 1000

_RELATION = """
SELECT database.oid::text AS database_oid, relation.oid::text AS relation_oid,
       namespace.nspname AS schema_name, relation.relname AS table_name,
       relation.relkind::text AS relkind, relation.relpersistence::text AS persistence,
       pg_catalog.pg_has_role(relation.relowner, 'USAGE') AS owned,
       pg_catalog.has_schema_privilege(namespace.oid, 'USAGE')
         AND pg_catalog.has_table_privilege(relation.oid, 'SELECT') AS readable,
       EXISTS (
           SELECT 1 FROM pg_catalog.pg_inherits AS inheritance
           WHERE inheritance.inhrelid = relation.oid OR inheritance.inhparent = relation.oid
       ) AS inherits,
       EXISTS (
           SELECT 1 FROM pg_catalog.pg_rewrite AS table_rule WHERE table_rule.ev_class = relation.oid
       ) AS has_rules,
       EXISTS (
           -- Keys and unique constraints are always marked connoinherit; the source refuses checks only.
           SELECT 1 FROM pg_catalog.pg_constraint AS table_constraint
           WHERE table_constraint.conrelid = relation.oid AND table_constraint.contype = 'c'
             AND table_constraint.connoinherit
       ) AS no_inherit_constraint
FROM pg_catalog.pg_class AS relation
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
JOIN pg_catalog.pg_database AS database ON database.datname = pg_catalog.current_database()
WHERE namespace.nspname = %s AND relation.relname = %s
LIMIT 2
"""

_HYPERTABLE = """
SELECT EXISTS (
    SELECT 1 FROM timescaledb_information.hypertables
    WHERE hypertable_schema = %s AND hypertable_name = %s
) AS converted
"""

# The source refuses foreign keys between hypertables in either direction.
_HYPERTABLE_REFERENCE = """
SELECT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_constraint AS reference
    JOIN pg_catalog.pg_class AS other
      ON other.oid = CASE WHEN reference.conrelid = %s::pg_catalog.oid
                          THEN reference.confrelid ELSE reference.conrelid END
    JOIN pg_catalog.pg_namespace AS other_namespace ON other_namespace.oid = other.relnamespace
    JOIN timescaledb_information.hypertables AS hypertable
      ON hypertable.hypertable_schema = other_namespace.nspname
     AND hypertable.hypertable_name = other.relname
    WHERE reference.contype = 'f'
      AND %s::pg_catalog.oid IN (reference.conrelid, reference.confrelid)
) AS references_hypertable
"""

_TIME_COLUMNS = """
SELECT attribute.attname AS name, pg_catalog.format_type(attribute.atttypid, NULL) AS type,
       attribute.attnotnull AS not_null
FROM pg_catalog.pg_attribute AS attribute
WHERE attribute.attrelid = %s::pg_catalog.oid AND attribute.attnum > 0 AND NOT attribute.attisdropped
  AND (attribute.atttypid IN (
      'pg_catalog.timestamp'::pg_catalog.regtype, 'pg_catalog.timestamptz'::pg_catalog.regtype,
      'pg_catalog.date'::pg_catalog.regtype
  ) OR (%s AND attribute.atttypid IN (
      'pg_catalog.int2'::pg_catalog.regtype, 'pg_catalog.int4'::pg_catalog.regtype,
      'pg_catalog.int8'::pg_catalog.regtype
  )) OR (%s AND attribute.atttypid = 'pg_catalog.uuid'::pg_catalog.regtype))
ORDER BY attribute.attnum
"""

# Every attribute of every index, as the source reads index definitions; an expression is NULL.
_INDEXES = """
SELECT index_relation.relname AS name,
       (table_index.indisunique OR table_index.indisexclusion) AS constrains,
       pg_catalog.array_agg(attribute.attname ORDER BY position) AS columns
FROM pg_catalog.pg_index AS table_index
JOIN pg_catalog.pg_class AS index_relation ON index_relation.oid = table_index.indexrelid
CROSS JOIN LATERAL pg_catalog.generate_series(0, table_index.indnatts - 1) AS position
LEFT JOIN pg_catalog.pg_attribute AS attribute
  ON attribute.attrelid = table_index.indrelid AND attribute.attnum = table_index.indkey[position]
WHERE table_index.indrelid = %s::pg_catalog.oid
GROUP BY index_relation.relname, table_index.indisunique, table_index.indisexclusion
ORDER BY 1
LIMIT %s
"""


@dataclass(frozen=True)
class TableIndex:
    name: str
    constrains: bool
    columns: tuple[str | None, ...]


@dataclass(frozen=True)
class ConversionState:
    target: ConversionTarget
    columns: tuple[ConversionColumn, ...]
    indexes: tuple[TableIndex, ...]
    strategy: ConversionStrategy
    empty: bool = True


def create_shape(dimension_info: str) -> RoutineShape:
    # sql/ddl_api.sql: regclass, dimension_info, three booleans, returning a record
    # set. The legacy overload beside it cannot win a call whose arguments are all
    # concrete, and its own leading arguments differ.
    return RoutineShape(
        "create_hypertable", "f", f"2205 {dimension_info} 16 16 16", 2249,
        returns_set=True, exclusive=False,
    )


def by_range_shape(dimension_info: str) -> RoutineShape:
    # name and anyelement returning dimension_info; polymorphic, so it must be alone.
    return RoutineShape("by_range", "f", "19 2283", int(dimension_info))


async def inspect_conversion(
    reader: PostgresReader, schema_name: str, table_name: str, *,
    allow_rows: bool = False, allow_integer: bool = False, allow_uuid: bool = False,
) -> ConversionState:
    """Everything that refuses a conversion whatever column and interval are chosen.

    Rows refuse it unless the caller moves them as a job (D207); then whether
    there are any is a fact of the state. Integer columns are candidates only
    for a caller that can plan integer_now beside them, and UUIDv7 ones only
    where the release partitions by them whole (D207).
    """
    try:
        async with asyncio.timeout(5):
            version = require_available(await discover(reader))
            await require_public_view(reader, "hypertables", ("hypertable_schema", "hypertable_name"))
            relations = await reader.query(_RELATION, (schema_name, table_name), inspection=True)
            if len(relations) != 1:
                raise ActionRefused("not_applicable", say("Choose an existing ordinary table"))
            _refuse_unconvertible(relations[0])
            target = ConversionTarget.model_validate({
                key: relations[0][key] for key in ("database_oid", "relation_oid", "schema_name", "table_name")
            })
            identity = (target.schema_name, target.table_name)
            if await _flag(reader, _HYPERTABLE, identity, "converted"):
                raise ActionRefused("not_applicable", say("This table is already a hypertable"))
            if await _flag(reader, _HYPERTABLE_REFERENCE, (target.relation_oid,) * 2, "references_hypertable"):
                raise ActionRefused(
                    "not_applicable", say("Foreign keys between this table and a hypertable are not supported"),
                )
            columns = tuple(
                ConversionColumn.model_validate(row)
                for row in await reader.query(_TIME_COLUMNS, (target.relation_oid, allow_integer, allow_uuid), inspection=True)
            )
            if not columns:
                raise ActionRefused("not_applicable", (
                    say("This table has no timestamp, date or integer column to partition by") if allow_integer
                    else say("This table has no timestamp or date column to partition by")
                ))
            empty = await _flag(reader, _empty_statement(target), None, "empty")
            if not empty and not allow_rows:
                raise ActionRefused("not_applicable", say("This table is not empty; only empty tables are converted here"))
            indexes = await reader.query(_INDEXES, (target.relation_oid, _INDEX_CEILING + 1), inspection=True)
            if len(indexes) > _INDEX_CEILING:
                raise ActionRefused("not_applicable", say("This table has too many indexes to inspect"))
            dimension_info = await extension_type(reader, version, "_timescaledb_internal", "dimension_info")
            create = await extension_routine(reader, version, create_shape(dimension_info))
            by_range = await extension_routine(reader, version, by_range_shape(dimension_info))
            strategy = ConversionStrategy.model_validate({
                "extension_version": version,
                "function_schema": create.schema_name,
                "create_function_oid": create.oid,
                "by_range_function_oid": by_range.oid,
                "dimension_info_oid": dimension_info,
            })
            if by_range.schema_name != create.schema_name:
                raise ActionRefused("not_applicable", say("The TimescaleDB conversion API is split across schemas"))
            return ConversionState(
                target=target, columns=columns,
                indexes=tuple(
                    TableIndex(name=row["name"], constrains=row["constrains"] is True, columns=tuple(row["columns"]))
                    for row in indexes
                ),
                strategy=strategy,
                empty=empty,
            )
    except TimeoutError:
        raise ActionRefused("not_applicable", say("TimescaleDB conversion planning timed out")) from None
    except (AdapterError, ValueError):
        raise ActionRefused(
            "not_applicable", say("The table could not be inspected safely for conversion"),
        ) from None


def _refuse_unconvertible(facts: Mapping[str, Any]) -> None:
    # The source's own refusals, in its order, so the review names the first it would raise.
    checks = (
        (facts.get("owned") is not True, say("Only the table's owner can convert it")),
        (facts.get("readable") is not True, say("This connection may not read the table")),
        (facts.get("relkind") == "p", say("Partitioned tables cannot become hypertables")),
        (facts.get("relkind") != "r", say("Choose an ordinary table")),
        (facts.get("no_inherit_constraint") is not False, say("Tables with NO INHERIT constraints cannot become hypertables")),
        (facts.get("inherits") is not False, say("Tables that use inheritance cannot become hypertables")),
        (facts.get("persistence") != "p", say("Only logged tables can become hypertables")),
        (facts.get("has_rules") is not False, say("Tables with rules cannot become hypertables")),
    )
    reason = next((message for failed, message in checks if failed), None)
    if reason is not None:
        raise ActionRefused("not_applicable", reason)


def _empty_statement(target: ConversionTarget) -> str:
    return sql.SQL("SELECT NOT EXISTS (SELECT 1 FROM ONLY {}) AS empty").format(
        sql.Identifier(target.schema_name, target.table_name),
    ).as_string()


async def _flag(
    reader: PostgresReader, statement: str, params: tuple[object, ...] | None, column: str,
) -> bool:
    rows = await reader.query(statement, params, inspection=True)
    value = rows[0].get(column) if len(rows) == 1 else None
    if not isinstance(value, bool):
        raise ActionRefused("not_applicable", say("The table could not be inspected safely for conversion"))
    return value


def conversion_column(state: ConversionState, column_name: str) -> ConversionColumn:
    column = next((item for item in state.columns if item.name == column_name), None)
    if column is None:
        choices = ", ".join(item.name for item in state.columns)
        raise ActionRefused("not_applicable", say("Choose a column this table can be partitioned by: {choices}", choices=choices))
    return column


def require_unique_indexes(state: ConversionState, column: ConversionColumn) -> None:
    missing = next(
        (index.name for index in state.indexes if index.constrains and column.name not in index.columns), None,
    )
    if missing is not None:
        raise ActionRefused("not_applicable", say(
            'Unique index "{index}" must include "{column}", which partitions the table',
            index=missing, column=column.name,
        ))


def time_index_exists(state: ConversionState, column: ConversionColumn) -> bool:
    # The rule of the default-index check in src/indexing.c (2.17.2 and 2.18.0).
    return any(index.columns == (column.name,) for index in state.indexes)


def conversion_plan(state: ConversionState, column_name: str, interval: TimeDuration) -> ConversionPlan:
    column = conversion_column(state, column_name)
    if column.type not in _TIME_TYPES:
        raise ActionRefused("not_applicable", say("An integer or UUID column is converted from Hypertable settings"))
    if interval.unit in {"month", "year"}:
        raise ActionRefused("not_applicable", say("Calendar chunk intervals are not supported by this strategy"))
    if column.type == "date" and interval.unit in _SUBDAY:
        raise ActionRefused("not_applicable", say("Date columns require whole days or weeks"))
    require_unique_indexes(state, column)
    return ConversionPlan(
        target=state.target, column=column, interval=interval,
        time_index_exists=time_index_exists(state, column),
        strategy=state.strategy,
    )


async def plan_conversion(
    reader: PostgresReader, schema_name: str, table_name: str, column_name: str, interval: TimeDuration,
) -> ConversionPlan:
    return conversion_plan(await inspect_conversion(reader, schema_name, table_name), column_name, interval)
