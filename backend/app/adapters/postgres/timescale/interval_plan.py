"""Inspect the first bounded Timescale interval plan without invoking its API."""

import asyncio

from app.adapters.actions import ActionRefused
from app.adapters.postgres.inspection import PostgresReader
from app.adapters.postgres.timescale.api import (
    RoutineShape,
    extension_routine,
    lockable_view,
)
from app.adapters.postgres.timescale.plans import (
    ChunkIntervalPlan,
    IntervalStrategy,
    IntervalTarget,
    TimeDuration,
)
from app.adapters.postgres.timescale.profile import discover, require_available
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

# sql/size_utils.sql: the hypertable, the interval and the dimension name.
# regclass 2205, anyelement 2283, name 19, returning void 2278. Polymorphic, so
# the routine must be the only one of its name in the extension's schema.
SET_INTERVAL = RoutineShape("set_chunk_time_interval", "f", "2205 2283 19", 2278)


async def plan_chunk_interval(
    session: PostgresReader, schema_name: str, table_name: str, interval: TimeDuration,
) -> ChunkIntervalPlan:
    if interval.unit in {"month", "year"}:
        raise ActionRefused("not_applicable", "Calendar chunk intervals are not supported by this strategy")
    try:
        async with asyncio.timeout(5):
            version = require_available(await discover(session))
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
            setter = await extension_routine(session, version, SET_INTERVAL)
            strategy = IntervalStrategy.model_validate({
                "extension_version": version,
                "function_oid": setter.oid,
                "function_schema": setter.schema_name,
                "dimensions_view_oid": await lockable_view(session, version, "dimensions"),
            })
            return ChunkIntervalPlan(target=target, interval=interval, strategy=strategy)
    except TimeoutError:
        raise ActionRefused("not_applicable", "TimescaleDB interval planning timed out") from None
    except (AdapterError, ValueError):
        raise ActionRefused("not_applicable", "TimescaleDB interval metadata could not be inspected safely") from None
