"""Resolve a management action's target through the catalog, then the source."""

from app.adapters.actions import ActionRefused
from app.adapters.catalog import SchemaNode, TableNode, ViewNode
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.inspection import PostgresReader
from app.adapters.postgres.timescale.plans import (
    INTEGER_COLUMN_TYPES,
    ContinuousAggregateTarget,
    MaintainedHypertable,
    TimeHypertable,
)
from app.adapters.postgres.timescale.report_access import require_public_view

_DIMENSION_COLUMNS = (
    "hypertable_schema", "hypertable_name", "dimension_number", "column_name",
    "column_type", "dimension_type",
)
_VIEWS = {
    "hypertables": ("hypertable_schema", "hypertable_name", "num_dimensions"),
    "dimensions": _DIMENSION_COLUMNS,
    "continuous_aggregates": ("materialization_hypertable_schema", "materialization_hypertable_name"),
}
_AGGREGATE_VIEWS = {
    "continuous_aggregates": (
        "view_schema", "view_name", "materialization_hypertable_schema",
        "materialization_hypertable_name", "hypertable_schema", "hypertable_name",
    ),
    "dimensions": _DIMENSION_COLUMNS,
}

_TIME_COLUMN_TYPES = frozenset({"timestamp without time zone", "timestamp with time zone", "date"})

_TIME_HYPERTABLE = """
SELECT database.oid::text AS database_oid, relation.oid::text AS relation_oid,
       namespace.nspname AS schema_name, relation.relname AS table_name,
       dimension.column_name, dimension.column_type::text AS column_type
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

# The first dimension is the one chunks are cut along in time; any other is
# counted, and only hash ones are named, since a second range is not maintained.
_MAINTAINED_HYPERTABLE = """
SELECT database.oid::text AS database_oid, relation.oid::text AS relation_oid,
       namespace.nspname AS schema_name, relation.relname AS table_name,
       dimension.column_name, dimension.column_type::text AS column_type,
       ARRAY(
           SELECT other.column_name::text FROM timescaledb_information.dimensions AS other
           WHERE other.hypertable_schema = hypertable.hypertable_schema
             AND other.hypertable_name = hypertable.hypertable_name
             AND other.dimension_number > 1 AND other.dimension_type = 'Space'
           ORDER BY other.dimension_number
       ) AS hash_columns,
       hypertable.num_dimensions
FROM timescaledb_information.hypertables AS hypertable
JOIN timescaledb_information.dimensions AS dimension
  USING (hypertable_schema, hypertable_name)
JOIN pg_catalog.pg_namespace AS namespace ON namespace.nspname = hypertable.hypertable_schema
JOIN pg_catalog.pg_class AS relation
  ON relation.relnamespace = namespace.oid AND relation.relname = hypertable.hypertable_name
JOIN pg_catalog.pg_database AS database ON database.datname = pg_catalog.current_database()
WHERE hypertable.hypertable_schema = %s AND hypertable.hypertable_name = %s
  AND dimension.dimension_type = 'Time' AND dimension.dimension_number = 1 AND relation.relkind = 'r'
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

_CONTINUOUS_AGGREGATE = """
SELECT database.oid::text AS database_oid,
       aggregate_view.oid::text AS view_oid,
       aggregate.view_schema, aggregate.view_name,
       materialization.oid::text AS materialization_oid,
       aggregate.materialization_hypertable_schema AS materialization_schema,
       aggregate.materialization_hypertable_name AS materialization_name,
       aggregate.hypertable_schema AS source_schema,
       aggregate.hypertable_name AS source_name,
       dimension.column_type::text AS column_type
FROM timescaledb_information.continuous_aggregates AS aggregate
JOIN pg_catalog.pg_namespace AS view_namespace ON view_namespace.nspname = aggregate.view_schema
JOIN pg_catalog.pg_class AS aggregate_view
  ON aggregate_view.relnamespace = view_namespace.oid
 AND aggregate_view.relname = aggregate.view_name AND aggregate_view.relkind = 'v'
JOIN pg_catalog.pg_namespace AS materialization_namespace
  ON materialization_namespace.nspname = aggregate.materialization_hypertable_schema
JOIN pg_catalog.pg_class AS materialization
  ON materialization.relnamespace = materialization_namespace.oid
 AND materialization.relname = aggregate.materialization_hypertable_name
 AND materialization.relkind = 'r'
JOIN timescaledb_information.dimensions AS dimension
  ON dimension.hypertable_schema = aggregate.hypertable_schema
 AND dimension.hypertable_name = aggregate.hypertable_name
 AND dimension.dimension_number = 1 AND dimension.dimension_type = 'Time'
JOIN pg_catalog.pg_database AS database ON database.datname = pg_catalog.current_database()
WHERE aggregate.view_schema = %s AND aggregate.view_name = %s
  AND pg_catalog.pg_has_role(aggregate_view.relowner, 'USAGE')
  AND pg_catalog.pg_has_role(materialization.relowner, 'USAGE')
  AND pg_catalog.has_schema_privilege(view_namespace.oid, 'USAGE')
  AND pg_catalog.has_table_privilege(aggregate_view.oid, 'SELECT')
LIMIT 2
"""


async def user_table(catalog: PostgresCatalog, node_id: str | None) -> tuple[SchemaNode, TableNode]:
    if node_id is not None:
        path = await catalog.path_to(node_id)
        if len(path) == 2:
            schema, node = path
            if (
                isinstance(schema, SchemaNode) and not schema.is_system
                and isinstance(node, TableNode) and not node.is_system
            ):
                return schema, node
    raise ActionRefused("not_applicable", "Choose one user hypertable")


async def user_view(catalog: PostgresCatalog, node_id: str | None) -> tuple[SchemaNode, ViewNode]:
    if node_id is not None:
        path = await catalog.path_to(node_id)
        if len(path) == 2:
            schema, node = path
            if (
                isinstance(schema, SchemaNode) and not schema.is_system
                and isinstance(node, ViewNode) and not node.is_system
            ):
                return schema, node
    raise ActionRefused("not_applicable", "Choose one user continuous aggregate")


async def time_hypertable(reader: PostgresReader, schema_name: str, table_name: str) -> TimeHypertable:
    """An owned hypertable with one time dimension, never an aggregate's materialization."""
    for view, columns in _VIEWS.items():
        await require_public_view(reader, view, columns)
    rows = await reader.query(_TIME_HYPERTABLE, (schema_name, table_name), inspection=True)
    if len(rows) != 1:
        raise ActionRefused("not_applicable", "Choose an owned hypertable with one time dimension")
    if rows[0].get("column_type") not in _TIME_COLUMN_TYPES:
        raise ActionRefused("not_applicable", "Only timestamp and date dimensions are supported here")
    return TimeHypertable.model_validate(rows[0])


async def maintained_hypertable(reader: PostgresReader, schema_name: str, table_name: str) -> MaintainedHypertable:
    """An owned hypertable cut along one time or integer column, hash dimensions beside it allowed."""
    for view, columns in _VIEWS.items():
        await require_public_view(reader, view, columns)
    rows = await reader.query(_MAINTAINED_HYPERTABLE, (schema_name, table_name), inspection=True)
    if len(rows) != 1:
        raise ActionRefused("not_applicable", "Choose an owned hypertable partitioned by time")
    row = dict(rows[0])
    if int(str(row.pop("num_dimensions"))) != 1 + len(row["hash_columns"]):
        raise ActionRefused("not_applicable", "Only a hypertable with one range dimension is maintained here")
    if row.get("column_type") not in _TIME_COLUMN_TYPES | INTEGER_COLUMN_TYPES:
        raise ActionRefused("not_applicable", "Only timestamp, date and integer dimensions are supported here")
    return MaintainedHypertable.model_validate(row)


async def continuous_aggregate(
    reader: PostgresReader, schema_name: str, view_name: str,
) -> ContinuousAggregateTarget:
    """An owned continuous aggregate over a timestamp or date dimension."""
    for view, columns in _AGGREGATE_VIEWS.items():
        await require_public_view(reader, view, columns)
    rows = await reader.query(_CONTINUOUS_AGGREGATE, (schema_name, view_name), inspection=True)
    if len(rows) != 1:
        raise ActionRefused("not_applicable", "Choose an owned continuous aggregate")
    if rows[0].get("column_type") not in _TIME_COLUMN_TYPES:
        raise ActionRefused("not_applicable", "Only aggregates over timestamp and date dimensions are supported here")
    return ContinuousAggregateTarget.model_validate(rows[0])
