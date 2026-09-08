"""Bounded optional public-function statistics for Details (D121)."""

import asyncio

from psycopg import sql
from pydantic import BaseModel

from app.adapters.postgres.session import PostgresSession
from app.adapters.protocol import AdapterError
from app.adapters.relation import RelationModel
from app.adapters.timescale_metadata import (
    ContinuousAggregateFacts,
    TimescaleCompression,
    TimescaleFacts,
    TimescaleSize,
    TimescaleStatistics,
    UnavailableTimescaleFacts,
)

_FUNCTION = """
SELECT namespace.nspname AS function_schema
FROM pg_catalog.pg_proc AS routine
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = routine.pronamespace
JOIN pg_catalog.pg_depend AS dependency
  ON dependency.classid = 'pg_catalog.pg_proc'::pg_catalog.regclass
 AND dependency.objid = routine.oid
 AND dependency.refclassid = 'pg_catalog.pg_extension'::pg_catalog.regclass
 AND dependency.deptype = 'e'
JOIN pg_catalog.pg_extension AS extension ON extension.oid = dependency.refobjid
WHERE extension.extname = 'timescaledb'
  AND pg_catalog.split_part(extension.extversion, '.', 1) = '2'
  AND routine.pronamespace = extension.extnamespace
  AND routine.proname = %s
  AND routine.prokind = 'f' AND routine.proretset
  AND routine.prorettype = 'pg_catalog.record'::pg_catalog.regtype
  AND routine.pronargs = 1 AND routine.pronargdefaults = 0
  AND routine.proargtypes[0] = 'pg_catalog.regclass'::pg_catalog.regtype
  AND routine.proallargtypes =
      ARRAY['pg_catalog.regclass'::pg_catalog.regtype::oid]
      || pg_catalog.array_fill('pg_catalog.int8'::pg_catalog.regtype::oid, ARRAY[%s])
      || ARRAY['pg_catalog.name'::pg_catalog.regtype::oid]
  AND routine.proargmodes = %s::"char"[]
  AND routine.proargnames[2:pg_catalog.cardinality(routine.proargnames)] = %s::text[]
  AND pg_catalog.has_schema_privilege(namespace.oid, 'USAGE')
  AND pg_catalog.has_function_privilege(routine.oid, 'EXECUTE')
LIMIT 2
"""


async def _read[_Facts: BaseModel](
    session: PostgresSession, names: tuple[str, ...], facts_type: type[_Facts],
    target: str,
) -> _Facts:
    fields = tuple(name for name in facts_type.model_fields if name != "kind")
    for name in names:
        functions = await session.query(
            _FUNCTION,
            (name, len(fields), ["i", *(["t"] * (len(fields) + 1))],
             [*fields, "node_name"]),
            inspection=True,
        )
        if not functions:
            continue
        if len(functions) != 1:
            raise ValueError("Ambiguous statistics API")
        schema = functions[0].get("function_schema")
        if not isinstance(schema, str) or not schema:
            raise ValueError("Invalid statistics API")
        projected = sql.SQL(", ").join(
            sql.SQL("{}::text AS {}").format(sql.Identifier(field), sql.Identifier(field))
            for field in fields
        )
        statement = sql.SQL(
            "SELECT {}, node_name FROM {}(%s::pg_catalog.regclass) LIMIT 2"
        ).format(projected, sql.Identifier(schema, name))
        rows = await session.query(statement.as_string(), (target,), inspection=True)
        if len(rows) != 1 or "node_name" not in rows[0] or rows[0]["node_name"] is not None:
            raise ValueError("Statistics do not identify one local result")
        return facts_type.model_validate({key: value for key, value in rows[0].items() if key != "node_name"})
    raise ValueError("No supported public statistics API")


async def inspect_statistics(
    session: PostgresSession, model: RelationModel, facts: TimescaleFacts | None,
) -> TimescaleStatistics | None:
    if model.specialization is None or facts is None or facts.kind == "unavailable":
        return None
    if model.schema_name is None:
        return None
    target = sql.Identifier(model.schema_name, model.name).as_string()
    compression_target = (
        sql.Identifier(
            facts.materialization_hypertable_schema, facts.materialization_hypertable_name,
        ).as_string()
        if isinstance(facts, ContinuousAggregateFacts) else target
    )
    size: TimescaleSize | UnavailableTimescaleFacts = UnavailableTimescaleFacts(
        reason="TimescaleDB size inspection timed out",
    )
    compression: TimescaleCompression | UnavailableTimescaleFacts = UnavailableTimescaleFacts(
        reason="TimescaleDB compression inspection timed out",
    )
    try:
        async with asyncio.timeout(5):
            try:
                size = await _read(session, ("hypertable_detailed_size",), TimescaleSize, target)
            except (AdapterError, ValueError):
                size = UnavailableTimescaleFacts(reason="TimescaleDB size could not be inspected safely")
            try:
                compression = await _read(
                    session, ("hypertable_columnstore_stats", "hypertable_compression_stats"),
                    TimescaleCompression, compression_target,
                )
            except (AdapterError, ValueError):
                compression = UnavailableTimescaleFacts(
                    reason="TimescaleDB compression statistics could not be inspected safely",
                )
    except TimeoutError:
        pass
    return TimescaleStatistics(size=size, compression=compression)
