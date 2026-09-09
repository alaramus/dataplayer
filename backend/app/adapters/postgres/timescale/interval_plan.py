"""Inspect the first bounded Timescale interval plan without invoking its API."""

import asyncio

from app.adapters.actions import ActionRefused
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.plans import (
    ChunkIntervalPlan,
    IntervalStrategy,
    IntervalTarget,
    TimeDuration,
)
from app.adapters.postgres.timescale.profile import discover
from app.adapters.postgres.timescale.report_access import require_public_view
from app.adapters.protocol import AdapterError

_VIEWS = {
    "hypertables": ("hypertable_schema", "hypertable_name", "num_dimensions"),
    "dimensions": (
        "hypertable_schema", "hypertable_name", "dimension_number", "column_name",
        "column_type", "dimension_type", "time_interval",
    ),
    "continuous_aggregates": ("materialization_hypertable_schema", "materialization_hypertable_name"),
}

_TARGET = """
SELECT database.oid::text AS database_oid, relation.oid::text AS relation_oid,
       namespace.nspname AS schema_name, relation.relname AS table_name,
       dimension.dimension_number, dimension.column_name,
       dimension.column_type::text AS column_type,
       dimension.time_interval::text AS current_interval
FROM timescaledb_information.hypertables AS hypertable
JOIN timescaledb_information.dimensions AS dimension
  USING (hypertable_schema, hypertable_name)
JOIN pg_catalog.pg_namespace AS namespace ON namespace.nspname = hypertable.hypertable_schema
JOIN pg_catalog.pg_class AS relation
  ON relation.relnamespace = namespace.oid AND relation.relname = hypertable.hypertable_name
JOIN pg_catalog.pg_database AS database ON database.datname = pg_catalog.current_database()
WHERE hypertable.hypertable_schema = %s AND hypertable.hypertable_name = %s
  AND hypertable.num_dimensions = 1 AND dimension.dimension_type = 'Time'
  AND dimension.dimension_number = 1 AND relation.relkind = 'r'
  AND pg_catalog.pg_has_role(relation.relowner, 'USAGE')
  AND pg_catalog.has_schema_privilege(namespace.oid, 'USAGE')
  AND pg_catalog.has_table_privilege(relation.oid, 'SELECT')
  AND NOT EXISTS (
      SELECT 1 FROM timescaledb_information.continuous_aggregates AS aggregate
      WHERE aggregate.materialization_hypertable_schema = namespace.nspname
        AND aggregate.materialization_hypertable_name = relation.relname
  )
LIMIT 2
"""

_API = """
SELECT routine.oid::text AS function_oid, namespace.nspname AS function_schema,
       extension.extversion AS extension_version
FROM pg_catalog.pg_proc AS routine
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = routine.pronamespace
JOIN pg_catalog.pg_depend AS dependency
  ON dependency.classid = 'pg_catalog.pg_proc'::pg_catalog.regclass
 AND dependency.objid = routine.oid
 AND dependency.refclassid = 'pg_catalog.pg_extension'::pg_catalog.regclass
 AND dependency.deptype = 'e'
JOIN pg_catalog.pg_extension AS extension ON extension.oid = dependency.refobjid
WHERE extension.extname = 'timescaledb' AND extension.extversion = %s
  AND routine.pronamespace = extension.extnamespace
  AND routine.proname = 'set_chunk_time_interval' AND routine.prokind = 'f'
  AND NOT routine.proretset AND routine.prorettype = 'pg_catalog.void'::pg_catalog.regtype
  AND routine.pronargs = 3 AND routine.pronargdefaults = 1
  AND routine.proargtypes[0] = 'pg_catalog.regclass'::pg_catalog.regtype
  AND routine.proargtypes[1] = 'pg_catalog.anyelement'::pg_catalog.regtype
  AND routine.proargtypes[2] = 'pg_catalog.name'::pg_catalog.regtype
  AND pg_catalog.has_schema_privilege(namespace.oid, 'USAGE')
  AND pg_catalog.has_function_privilege(routine.oid, 'EXECUTE')
LIMIT 2
"""


async def plan_chunk_interval(
    session: PostgresSession, schema_name: str, table_name: str, interval: TimeDuration,
) -> ChunkIntervalPlan:
    if interval.unit in {"month", "year"}:
        raise ActionRefused("not_applicable", "Calendar chunk intervals are not supported by this strategy")
    try:
        async with asyncio.timeout(5):
            profile = await discover(session)
            version = profile.feature.installed_version
            if not profile.available or version not in {"2.17.2", "2.18.0"}:
                raise ActionRefused("not_applicable", "No supported TimescaleDB interval planning API")
            for view, columns in _VIEWS.items():
                await require_public_view(session, view, columns)
            rows = await session.query(_TARGET, (schema_name, table_name), inspection=True)
            if len(rows) != 1:
                raise ActionRefused(
                    "not_applicable", "Choose an owned hypertable with one time dimension",
                )
            target = IntervalTarget.model_validate(rows[0])
            if target.column_type == "date" and interval.unit not in {"day", "week"}:
                raise ActionRefused("not_applicable", "Date dimensions require whole days or weeks")
            functions = await session.query(_API, (version,), inspection=True)
            if len(functions) != 1:
                raise ActionRefused("not_applicable", "The interval API is unavailable or ambiguous")
            strategy = IntervalStrategy.model_validate(functions[0])
            if strategy.extension_version != version:
                raise ActionRefused("conflict", "TimescaleDB changed during planning; try again")
            return ChunkIntervalPlan(target=target, interval=interval, strategy=strategy)
    except TimeoutError:
        raise ActionRefused("not_applicable", "TimescaleDB interval planning timed out") from None
    except (AdapterError, ValueError):
        raise ActionRefused("not_applicable", "TimescaleDB interval metadata could not be inspected safely") from None
