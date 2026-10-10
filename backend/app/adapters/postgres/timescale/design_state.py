"""Read a hypertable into the design model, and everything planning needs beside it (D207).

Only public views and PostgreSQL catalogs are read (D121). Two settings have no
routine whose shape could say what the release means by them, so the meaning of
an unset segment or order list is declared by release instead (D207): before
2.22.1 an unset list was resolved once, when compression was enabled, and
`RESET` was refused; from it on, an unset list means Timescale chooses for each
chunk. The matrix holds 2.19.3 and 2.23.1 on either side.

An integer time column's integer_now function is named by the views without
its schema, and can even be dropped while it is set; the reader names it only
when one zero-argument function of that name and type exists, and keeps it as
it is otherwise.
"""

import asyncio
import json
import re
from dataclasses import dataclass

from psycopg import sql
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.adapters.actions import ActionRefused
from app.adapters.hypertable_design import (
    BIGINT_MAX,
    AgePolicyDesign,
    ChosenByTimescale,
    ColumnstoreDesign,
    CurrentPolicy,
    DesignDuration,
    DurationUnit,
    ExistingNow,
    HashDimensionDesign,
    HypertableColumn,
    HypertableDesign,
    HypertableDesignState,
    IntegerSpan,
    KeptAsItIs,
    KeptNow,
    NoColumns,
    NowDesign,
    NowFunction,
    NowTemplate,
    OlderThan,
    OrderBy,
    OrderColumns,
    OrderKey,
    SegmentBy,
    SegmentColumns,
    Span,
    SparseColumns,
    SparseIndex,
    SparseIndexes,
)
from app.adapters.postgres.inspection import PostgresReader
from app.adapters.postgres.timescale.age_policy_plan import (
    COMPRESSION,
    JOBS_COLUMNS,
    RETENTION,
    read_age_policy,
)
from app.adapters.postgres.timescale.api import RoutineShape, extension_routine
from app.adapters.postgres.timescale.conversion_plan import (
    ConversionState,
    inspect_conversion,
)
from app.adapters.postgres.timescale.plans import AgePolicy, ConversionColumn
from app.adapters.postgres.timescale.policy_projection import OWNED_POLICY_ROUTINE
from app.adapters.postgres.timescale.profile import discover, require_available
from app.adapters.postgres.timescale.report_access import require_public_view
from app.adapters.protocol import AdapterError

_OID = r"^[1-9][0-9]{0,9}$"
PER_CHUNK_DEFAULTS = (2, 22, 1)
# UUIDv7 partitioning arrived in 2.22, but until 2.25 the views report its
# interval in microseconds and its chunks without a range, and a retention
# policy refuses it; the matrix holds 2.23.1 and 2.30.0 either side (D207).
UUID_TIME = (2, 25, 0)
# sql/policy_api.sql from 2.29; regclass 2205, boolean 16; integer 23, void 2278.
ADD_COMPACTION = RoutineShape("add_compaction_policy", "f", "2205 16", 23)
REMOVE_COMPACTION = RoutineShape("remove_compaction_policy", "f", "2205 16", 2278)
_SPARSE_KINDS = ("minmax", "bloom")
_TIME_TYPES = ("timestamp without time zone", "timestamp with time zone", "date")
INTEGER_TYPES = ("smallint", "integer", "bigint")
INTEGER_MAX = {"smallint": 32_767, "integer": 2_147_483_647, "bigint": BIGINT_MAX}
# Proposed chunk intervals for an integer time column, an order of magnitude apart.
_PROPOSED_COUNT = {"smallint": 10_000, "integer": 100_000, "bigint": 1_000_000}
# What each type holds without overflowing: seconds since 1970 left smallint's
# range in its first nine hours and leave integer's in 2038.
NOW_TEMPLATES: dict[str, tuple[NowTemplate, ...]] = {
    "smallint": (),
    "integer": ("epoch_seconds",),
    "bigint": ("epoch_seconds", "epoch_milliseconds", "epoch_microseconds"),
}

_VIEWS = {
    "hypertables": (
        "hypertable_schema", "hypertable_name", "num_dimensions", "compression_enabled", "tablespaces",
    ),
    "dimensions": (
        "hypertable_schema", "hypertable_name", "dimension_number", "column_name",
        "column_type", "dimension_type", "time_interval", "num_partitions",
        "integer_interval", "integer_now_func",
    ),
    "continuous_aggregates": ("materialization_hypertable_schema", "materialization_hypertable_name"),
    "chunks": ("hypertable_schema", "hypertable_name", "is_compressed"),
    "hypertable_compression_settings": ("hypertable", "segmentby", "orderby", "compress_interval_length"),
    # Deprecated since 2.18 and still in 2.30. The only public answer that lists a
    # column whose name holds a comma as one column: the text views above join
    # names with commas and do not quote them.
    "compression_settings": (
        "hypertable_schema", "hypertable_name", "attname", "segmentby_column_index",
        "orderby_column_index", "orderby_asc", "orderby_nullsfirst",
    ),
    "jobs": JOBS_COLUMNS,
}

_TARGET = """
SELECT database.oid::text AS database_oid, relation.oid::text AS relation_oid,
       namespace.nspname AS schema_name, relation.relname AS table_name,
       dimension.column_name, dimension.column_type::text AS column_type,
       (EXTRACT(epoch FROM dimension.time_interval) * 1000000)::pg_catalog.int8 AS interval_microseconds,
       dimension.integer_interval::pg_catalog.int8 AS integer_interval,
       dimension.integer_now_func::text AS integer_now_func,
       hypertable.compression_enabled
FROM timescaledb_information.hypertables AS hypertable
JOIN timescaledb_information.dimensions AS dimension
  USING (hypertable_schema, hypertable_name)
JOIN pg_catalog.pg_namespace AS namespace ON namespace.nspname = hypertable.hypertable_schema
JOIN pg_catalog.pg_class AS relation
  ON relation.relnamespace = namespace.oid AND relation.relname = hypertable.hypertable_name
JOIN pg_catalog.pg_database AS database ON database.datname = pg_catalog.current_database()
WHERE hypertable.hypertable_schema = %s AND hypertable.hypertable_name = %s
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

_SPACE = """
SELECT dimension_number, column_name, num_partitions, dimension_type
FROM timescaledb_information.dimensions
WHERE hypertable_schema = %s AND hypertable_name = %s AND dimension_number > 1
ORDER BY dimension_number
"""

# A column is orderable when its type has a default btree operator class, the
# question Timescale asks of a segment, order or hash column. Arrays and enums
# reach theirs through the polymorphic class.
_COLUMNS = """
SELECT attribute.attname AS name,
       pg_catalog.format_type(attribute.atttypid, attribute.atttypmod) AS type,
       EXISTS (
           SELECT 1 FROM pg_catalog.pg_opclass AS opclass
           JOIN pg_catalog.pg_am AS method ON method.oid = opclass.opcmethod
           WHERE method.amname = 'btree' AND opclass.opcdefault
             AND (opclass.opcintype = attribute.atttypid
                  OR (opclass.opcintype = 'pg_catalog.anyarray'::pg_catalog.regtype
                      AND data_type.typcategory = 'A')
                  OR (opclass.opcintype = 'pg_catalog.anyenum'::pg_catalog.regtype
                      AND data_type.typtype = 'e'))
       ) AS orderable
FROM pg_catalog.pg_attribute AS attribute
JOIN pg_catalog.pg_type AS data_type ON data_type.oid = attribute.atttypid
WHERE attribute.attrelid = %s::pg_catalog.oid AND attribute.attnum > 0 AND NOT attribute.attisdropped
ORDER BY attribute.attnum
"""

_INDEXES = """
SELECT index_class.relname AS name
FROM pg_catalog.pg_index AS table_index
JOIN pg_catalog.pg_class AS index_class ON index_class.oid = table_index.indexrelid
WHERE table_index.indrelid = %s::pg_catalog.oid AND table_index.indisvalid AND table_index.indisready
ORDER BY 1
"""

_UNIQUE_KEYS = """
SELECT index_class.relname AS name,
       pg_catalog.array_agg(attribute.attname::text ORDER BY position) AS columns
FROM pg_catalog.pg_index AS unique_index
JOIN pg_catalog.pg_class AS index_class ON index_class.oid = unique_index.indexrelid
CROSS JOIN LATERAL pg_catalog.generate_series(0, unique_index.indnkeyatts - 1) AS position
LEFT JOIN pg_catalog.pg_attribute AS attribute
  ON attribute.attrelid = unique_index.indrelid AND attribute.attnum = unique_index.indkey[position]
WHERE unique_index.indrelid = %s::pg_catalog.oid AND unique_index.indisunique
GROUP BY index_class.relname
ORDER BY 1
"""

_IS_HYPERTABLE = """
SELECT EXISTS (
    SELECT 1 FROM timescaledb_information.hypertables
    WHERE hypertable_schema = %s AND hypertable_name = %s
) AS converted
"""

# The planner's estimate; -1 before the first ANALYZE.
_ESTIMATE = """
SELECT CASE WHEN relation.reltuples < 0 THEN NULL ELSE relation.reltuples::pg_catalog.int8 END AS rows
FROM pg_catalog.pg_class AS relation WHERE relation.oid = %s::pg_catalog.oid
"""

_TABLESPACES = """
SELECT spcname AS name FROM pg_catalog.pg_tablespace
WHERE spcname <> 'pg_global' AND pg_catalog.has_tablespace_privilege(oid, 'CREATE')
ORDER BY 1
"""

_ATTACHED = """
SELECT COALESCE(tablespaces, '{}')::text[] AS tablespaces
FROM timescaledb_information.hypertables
WHERE hypertable_schema = %s AND hypertable_name = %s
"""

_CHUNKS = """
SELECT pg_catalog.count(*) > 0 AS has_chunks,
       COALESCE(pg_catalog.bool_or(is_compressed), false) AS compressed_chunks
FROM timescaledb_information.chunks
WHERE hypertable_schema = %s AND hypertable_name = %s
"""

_SETTINGS = """
SELECT segmentby, orderby,
       (EXTRACT(epoch FROM compress_interval_length::pg_catalog.interval) * 1000000)::pg_catalog.int8
           AS merge_microseconds
FROM timescaledb_information.hypertable_compression_settings
WHERE hypertable = %s::pg_catalog.regclass
"""

# From 2.22 the settings view says which sparse indexes a chunk gets, each with
# where it came from: "config" is what was set, anything else Timescale's own.
_SPARSE = """
SELECT index::text AS sparse
FROM timescaledb_information.hypertable_compression_settings
WHERE hypertable = %s::pg_catalog.regclass
"""

_COMPACTION = sql.SQL("""
SELECT source.job_id::text AS job_id, source.scheduled
FROM timescaledb_information.jobs AS source
WHERE source.hypertable_schema = %s AND source.hypertable_name = %s
  AND source.proc_name = 'policy_compaction' AND {owned}
ORDER BY source.job_id
LIMIT 2
""").format(owned=OWNED_POLICY_ROUTINE).as_string()

_SETTING_COLUMNS = """
SELECT attname::text AS name, segmentby_column_index, orderby_column_index, orderby_asc, orderby_nullsfirst
FROM timescaledb_information.compression_settings
WHERE hypertable_schema = %s AND hypertable_name = %s
"""

_REORDER = sql.SQL("""
SELECT source.job_id::text AS job_id, source.scheduled,
       (CASE WHEN pg_catalog.jsonb_typeof(source.config -> 'index_name') = 'string'
             AND pg_catalog.length(source.config ->> 'index_name') <= 63
        THEN source.config ->> 'index_name' END) AS index_name
FROM timescaledb_information.jobs AS source
WHERE source.hypertable_schema = %s AND source.hypertable_name = %s
  AND source.proc_name = 'policy_reorder' AND {owned}
ORDER BY source.job_id
LIMIT 2
""").format(owned=OWNED_POLICY_ROUTINE).as_string()

# What Timescale accepts as integer_now (src/dimension.c): no arguments, the
# column's type, stable or immutable. Functions of system schemas and of any
# extension are nobody's clock. No placeholders, so a percent sign is safe.
_NOW_FUNCTIONS = """
SELECT namespace.nspname AS schema_name, routine.proname AS name,
       pg_catalog.format_type(routine.prorettype, NULL) AS type
FROM pg_catalog.pg_proc AS routine
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = routine.pronamespace
WHERE routine.prokind = 'f' AND routine.pronargs = 0 AND NOT routine.proretset
  AND routine.provolatile IN ('s', 'i')
  AND routine.prorettype IN (
      'pg_catalog.int2'::pg_catalog.regtype, 'pg_catalog.int4'::pg_catalog.regtype,
      'pg_catalog.int8'::pg_catalog.regtype
  )
  AND namespace.nspname <> 'information_schema'
  AND NOT pg_catalog.starts_with(namespace.nspname, 'pg_')
  AND NOT pg_catalog.starts_with(namespace.nspname, '_timescaledb')
  AND NOT pg_catalog.starts_with(namespace.nspname, 'timescaledb_')
  AND pg_catalog.has_schema_privilege(namespace.oid, 'USAGE')
  AND pg_catalog.has_function_privilege(routine.oid, 'EXECUTE')
  AND NOT EXISTS (
      SELECT 1 FROM pg_catalog.pg_depend AS dependency
      WHERE dependency.classid = 'pg_catalog.pg_proc'::pg_catalog.regclass
        AND dependency.objid = routine.oid AND dependency.deptype = 'e'
  )
ORDER BY 1, 2
LIMIT 100
"""

_NOW_NAMED = """
SELECT namespace.nspname AS schema_name, routine.proname AS name
FROM pg_catalog.pg_proc AS routine
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = routine.pronamespace
WHERE routine.proname = %s AND routine.prokind = 'f' AND routine.pronargs = 0
  AND routine.prorettype = %s::pg_catalog.regtype
LIMIT 2
"""

# A new function's name must be free in its schema, and free of any other
# zero-argument function, or reading it back by name would become ambiguous.
_NAME_FREE = """
SELECT NOT EXISTS (
           SELECT 1 FROM pg_catalog.pg_proc AS routine
           JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = routine.pronamespace
           WHERE routine.proname = %s AND (namespace.nspname = %s OR routine.pronargs = 0)
       ) AS free,
       COALESCE((
           SELECT pg_catalog.has_schema_privilege(namespace.oid, 'CREATE')
           FROM pg_catalog.pg_namespace AS namespace WHERE namespace.nspname = %s
       ), false) AS creatable
"""

_MICROSECONDS: dict[DurationUnit, int] = {
    "week": 604_800_000_000, "day": 86_400_000_000, "hour": 3_600_000_000,
    "minute": 60_000_000, "second": 1_000_000,
}
_FIXED_UNITS: tuple[DurationUnit, ...] = ("week", "day", "hour", "minute", "second")
_CLOCK_UNITS: tuple[tuple[DurationUnit, int], ...] = (("hour", 3600), ("minute", 60), ("second", 1))
_SUBDAY = ("second", "minute", "hour")
# What PostgreSQL writes for an interval of one field under the default IntervalStyle.
_ONE_FIELD = re.compile(r"^(?P<amount>[1-9][0-9]{0,9}) (?P<unit>years?|mons?|days?)$")
_CLOCK = re.compile(r"^(?P<hours>[0-9]{1,9}):(?P<minutes>[0-9]{2}):(?P<seconds>[0-9]{2})$")


class DesignTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    database_oid: str = Field(pattern=_OID)
    relation_oid: str = Field(pattern=_OID)
    schema_name: str = Field(min_length=1, max_length=63)
    table_name: str = Field(min_length=1, max_length=63)
    column_name: str = Field(min_length=1, max_length=63)
    column_type: str = Field(min_length=1, max_length=100)


class ColumnFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=63)
    type: str = Field(min_length=1, max_length=200)
    orderable: bool


class UniqueKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=63)
    # None for an expression key, which no column can be said to be part of.
    columns: tuple[str | None, ...]


class ReorderPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(pattern=_OID)
    scheduled: bool = Field(strict=True)
    index_name: str | None = Field(default=None, min_length=1, max_length=63)


class CompactionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(pattern=_OID)
    scheduled: bool = Field(strict=True)


@dataclass(frozen=True)
class Capabilities:
    """What this release offers beyond the matrix's oldest, found where it can be."""

    sparse_indexes: bool
    compaction: bool
    uuid_time: bool


async def capabilities(reader: PostgresReader, version: str) -> Capabilities:
    try:
        await require_public_view(reader, "hypertable_compression_settings", ("index",))
        sparse = True
    except ValueError:
        sparse = False
    try:
        await extension_routine(reader, version, ADD_COMPACTION)
        await extension_routine(reader, version, REMOVE_COMPACTION)
        compaction = True
    except ActionRefused:
        compaction = False
    return Capabilities(sparse_indexes=sparse, compaction=compaction, uuid_time=release(version) >= UUID_TIME)


class CurrentHypertable(BaseModel):
    """The whole present state; a plan carries it, so any change to it is a new plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    extension_version: str
    target: DesignTarget
    design: HypertableDesign
    # Microseconds for a time column, the column's own values for an integer one.
    interval_length: int = Field(strict=True, gt=0)
    columns: tuple[ColumnFact, ...]
    unique_keys: tuple[UniqueKey, ...]
    indexes: tuple[str, ...]
    available_tablespaces: tuple[str, ...]
    retention: AgePolicy | None
    compression: AgePolicy | None
    reorder: ReorderPolicy | None
    per_chunk_defaults: bool
    has_chunks: bool
    compressed_chunks: bool
    # The functions integer_now may name, for an integer time column only.
    now_functions: tuple[NowFunction, ...] = ()
    integer_now_name: str | None = None
    compaction: CompactionPolicy | None = None
    sparse_indexes_supported: bool = False
    compaction_supported: bool = False

    def column(self, name: str) -> ColumnFact | None:
        return next((column for column in self.columns if column.name == name), None)

    @property
    def integer(self) -> bool:
        return self.target.column_type in INTEGER_TYPES


def release(version: str) -> tuple[int, ...]:
    core = re.match(r"^[0-9]+\.[0-9]+\.[0-9]+", version)
    return tuple(int(part) for part in core.group(0).split(".")) if core else (0, 0, 0)


def duration_microseconds(duration: DesignDuration) -> int | None:
    """The fixed length of a duration; None for months and years, which have none."""
    per_unit = _MICROSECONDS.get(duration.unit)
    return None if per_unit is None else duration.amount * per_unit


def fixed_duration(microseconds: int) -> DesignDuration | None:
    """The largest whole unit a fixed length is written in, or None below a second."""
    for unit in _FIXED_UNITS:
        per_unit = _MICROSECONDS[unit]
        if microseconds % per_unit == 0 and 0 < microseconds // per_unit <= 2_147_483_647:
            return DesignDuration(amount=microseconds // per_unit, unit=unit)
    return None


def interval_duration(text: str) -> DesignDuration | None:
    """One field of a policy threshold as the source wrote it; None for anything else."""
    field = _ONE_FIELD.match(text)
    if field is not None:
        amount = int(field["amount"])
        unit = field["unit"].rstrip("s")
        if unit == "mon":
            return DesignDuration(amount=amount // 12, unit="year") if amount % 12 == 0 else (
                DesignDuration(amount=amount, unit="month")
            )
        if unit == "year":
            return DesignDuration(amount=amount, unit="year")
        return DesignDuration(amount=amount // 7, unit="week") if amount % 7 == 0 else (
            DesignDuration(amount=amount, unit="day")
        )
    clock = _CLOCK.match(text)
    if clock is None:
        return None
    seconds = int(clock["hours"]) * 3600 + int(clock["minutes"]) * 60 + int(clock["seconds"])
    if seconds == 0:
        return None
    for unit, size in _CLOCK_UNITS:
        if seconds % size == 0:
            return DesignDuration(amount=seconds // size, unit=unit)
    return None


def count_span(value: int) -> IntegerSpan:
    return IntegerSpan(amount=str(value))


def _policy_design(policy: AgePolicy | None) -> AgePolicyDesign | None:
    if policy is None:
        return None
    if policy.scheduled and policy.older_than is not None:
        duration = interval_duration(policy.older_than)
        if duration is not None:
            return OlderThan(older_than=duration)
    if policy.scheduled and policy.older_than_count is not None and int(policy.older_than_count) <= BIGINT_MAX:
        return OlderThan(older_than=IntegerSpan(amount=policy.older_than_count))
    return KeptAsItIs()


def _describe(noun: str, policy: AgePolicy | None) -> CurrentPolicy | None:
    if policy is None:
        return None
    paused = "" if policy.scheduled else "; paused"
    return CurrentPolicy(
        job_id=policy.job_id,
        description=f"Job {policy.job_id} {noun} chunks {policy.threshold()}, every {policy.schedule_interval}{paused}",
    )


def _segment_by(raw: object, listed: list[str], per_chunk_defaults: bool) -> SegmentBy:
    if listed:
        return SegmentColumns(columns=listed)
    # Before per-chunk defaults an unset list and an empty one read alike, and both
    # mean no segmenting.
    if per_chunk_defaults and raw is None:
        return ChosenByTimescale()
    return NoColumns()


def sparse_indexes(raw: object) -> SparseIndexes:
    """The sparse indexes that were set, read from the view's JSON; Timescale's own are not the design's."""
    if not isinstance(raw, str):
        return ChosenByTimescale()
    entries = json.loads(raw)
    if not isinstance(entries, list):
        raise ActionRefused("not_applicable", "The current sparse indexes could not be read")
    configured = [item for item in entries if isinstance(item, dict) and item.get("source") == "config"]
    if not configured:
        return ChosenByTimescale()
    typed = [item for item in configured if "type" in item]
    if not typed:
        # Set to an empty list, which is "none" rather than unset.
        return NoColumns()
    if any(item.get("type") not in _SPARSE_KINDS or not isinstance(item.get("column"), str) for item in typed):
        raise ActionRefused(
            "not_applicable", "This hypertable has a sparse index of a kind this editor does not know; manage it with SQL",
        )
    return SparseColumns(indexes=[SparseIndex(column=item["column"], kind=item["type"]) for item in typed])


def _order_by(listed: list[OrderKey]) -> OrderBy:
    # Every release refuses an empty order, so nothing listed is always Timescale's choice:
    # an older release resolves one on enabling, a newer one for each chunk.
    return OrderColumns(columns=listed) if listed else ChosenByTimescale()


async def _columnstore(
    reader: PostgresReader, target: DesignTarget, enabled: bool, per_chunk_defaults: bool, integer: bool,
    sparse_supported: bool,
) -> ColumnstoreDesign:
    settings = await reader.query(_SETTINGS, (target.relation_oid,), inspection=True)
    if len(settings) != 1:
        raise ActionRefused("not_applicable", "The current columnstore settings could not be read")
    rows = await reader.query(_SETTING_COLUMNS, (target.schema_name, target.table_name), inspection=True)
    segment = sorted(
        (row for row in rows if row.get("segmentby_column_index") is not None),
        key=lambda row: int(row["segmentby_column_index"]),
    )
    order = sorted(
        (row for row in rows if row.get("orderby_column_index") is not None),
        key=lambda row: int(row["orderby_column_index"]),
    )
    merge = settings[0].get("merge_microseconds")
    # Timescale reads the setting as time even on an integer column, so a value
    # there means seconds nobody chose; the editor offers none and changes none.
    if integer and merge is not None:
        raise ActionRefused(
            "not_applicable", "This hypertable merges compressed chunks by a time interval; manage it with SQL",
        )
    return ColumnstoreDesign(
        enabled=enabled,
        segment_by=_segment_by(settings[0].get("segmentby"), [str(row["name"]) for row in segment], per_chunk_defaults),
        order_by=_order_by([
            OrderKey(column=str(row["name"]), descending=row["orderby_asc"] is False,
                     nulls_first=row["orderby_nullsfirst"] is True)
            for row in order
        ]),
        merge_interval=fixed_duration(merge) if isinstance(merge, int) and merge > 0 else None,
        sparse_indexes=await _sparse(reader, target) if sparse_supported else ChosenByTimescale(),
    )


async def _sparse(reader: PostgresReader, target: DesignTarget) -> SparseIndexes:
    rows = await reader.query(_SPARSE, (target.relation_oid,), inspection=True)
    return sparse_indexes(rows[0].get("sparse") if len(rows) == 1 else None)


async def _compaction(reader: PostgresReader, target: DesignTarget) -> CompactionPolicy | None:
    rows = await reader.query(_COMPACTION, (target.schema_name, target.table_name), inspection=True)
    if len(rows) > 1:
        raise ActionRefused("not_applicable", "This hypertable has several compaction policy jobs; manage them with SQL")
    return CompactionPolicy.model_validate(rows[0]) if rows else None


async def _reorder(reader: PostgresReader, target: DesignTarget) -> ReorderPolicy | None:
    rows = await reader.query(_REORDER, (target.schema_name, target.table_name), inspection=True)
    if len(rows) > 1:
        raise ActionRefused("not_applicable", "This hypertable has several reorder policy jobs; manage them with SQL")
    if not rows:
        return None
    try:
        policy: ReorderPolicy | None = ReorderPolicy.model_validate(rows[0])
    except ValidationError:
        policy = None
    # Shown as no policy, an unreadable one would be removed by the next unrelated change.
    if policy is None or policy.index_name is None:
        raise ActionRefused(
            "not_applicable", "The existing reorder policy could not be read safely; manage it with SQL",
        )
    return policy


@dataclass(frozen=True)
class TableFacts:
    """What every table has, whether or not it is a hypertable yet."""

    columns: tuple[ColumnFact, ...]
    unique_keys: tuple[UniqueKey, ...]
    indexes: tuple[str, ...]
    tablespaces: tuple[str, ...]


async def _table_facts(reader: PostgresReader, relation_oid: str) -> TableFacts:
    column_rows = await reader.query(_COLUMNS, (relation_oid,), inspection=True)
    unique_rows = await reader.query(_UNIQUE_KEYS, (relation_oid,), inspection=True)
    index_rows = await reader.query(_INDEXES, (relation_oid,), inspection=True)
    tablespace_rows = await reader.query(_TABLESPACES, inspection=True)
    return TableFacts(
        columns=tuple(ColumnFact.model_validate(item) for item in column_rows),
        unique_keys=tuple(UniqueKey(name=item["name"], columns=tuple(item["columns"])) for item in unique_rows),
        indexes=tuple(str(item["name"]) for item in index_rows),
        tablespaces=tuple(str(item["name"]) for item in tablespace_rows),
    )


async def read_current(reader: PostgresReader, schema_name: str, table_name: str) -> CurrentHypertable:
    """The hypertable as it is now; refuses what this editor cannot work on, saying why."""
    version = require_available(await discover(reader))
    for view, columns in _VIEWS.items():
        await require_public_view(reader, view, columns)
    rows = await reader.query(_TARGET, (schema_name, table_name), inspection=True)
    if len(rows) != 1:
        raise ActionRefused("not_applicable", "Choose an owned hypertable")
    row = rows[0]
    column_type = row.get("column_type")
    integer = column_type in INTEGER_TYPES
    offered = await capabilities(reader, version)
    if column_type == "uuid" and not offered.uuid_time:
        raise ActionRefused(
            "not_applicable", f"TimescaleDB {version} partitions by UUIDv7 only partly; it is edited here from 2.25",
        )
    if not integer and column_type not in (*_TIME_TYPES, "uuid"):
        raise ActionRefused("not_applicable", "Only timestamp, date, UUIDv7 and integer time dimensions are edited here")
    interval = row.get("integer_interval" if integer else "interval_microseconds")
    if not isinstance(interval, int) or interval <= 0:
        raise ActionRefused("not_applicable", "The current chunk interval could not be read")
    target = DesignTarget.model_validate({key: row[key] for key in DesignTarget.model_fields})
    identity = (target.schema_name, target.table_name)

    space = await reader.query(_SPACE, identity, inspection=True)
    if any(item.get("dimension_type") != "Space" or not isinstance(item.get("num_partitions"), int)
           for item in space):
        raise ActionRefused("not_applicable", "Only hash dimensions beside the time dimension are edited here")
    per_chunk_defaults = release(version) >= PER_CHUNK_DEFAULTS
    enabled = row.get("compression_enabled") is True
    columnstore = await _columnstore(reader, target, enabled, per_chunk_defaults, integer, offered.sparse_indexes)
    now_name = row.get("integer_now_func") if integer else None
    integer_now = await _integer_now(reader, now_name, target.column_type) if isinstance(now_name, str) else None

    retention = await read_age_policy(reader, RETENTION, *identity)
    compression = await read_age_policy(reader, COMPRESSION, *identity)
    reorder = await _reorder(reader, target)
    compaction = await _compaction(reader, target) if offered.compaction else None
    attached = await reader.query(_ATTACHED, identity, inspection=True)
    chunks = await reader.query(_CHUNKS, identity, inspection=True)
    if len(attached) != 1 or len(chunks) != 1:
        raise ActionRefused("not_applicable", "The hypertable's chunks and tablespaces could not be read")

    design = HypertableDesign(
        time_column=target.column_name,
        chunk_interval=count_span(interval) if integer else fixed_duration(interval),
        hash_dimensions=[
            HashDimensionDesign(column=str(item["column_name"]), partitions=int(item["num_partitions"]))
            for item in space
        ],
        columnstore=columnstore,
        retention=_policy_design(retention),
        columnstore_policy=_policy_design(compression),
        reorder_index=reorder.index_name if reorder is not None else None,
        tablespaces=list(attached[0]["tablespaces"]),
        integer_now=integer_now,
        compaction_policy=compaction is not None,
    )
    facts = await _table_facts(reader, target.relation_oid)
    return CurrentHypertable(
        extension_version=version,
        target=target,
        design=design,
        interval_length=interval,
        columns=facts.columns,
        unique_keys=facts.unique_keys,
        indexes=facts.indexes,
        available_tablespaces=facts.tablespaces,
        retention=retention,
        compression=compression,
        reorder=reorder,
        per_chunk_defaults=per_chunk_defaults,
        has_chunks=chunks[0]["has_chunks"] is True,
        compressed_chunks=chunks[0]["compressed_chunks"] is True,
        now_functions=await now_functions(reader, target.column_type) if integer else (),
        integer_now_name=now_name if isinstance(now_name, str) else None,
        compaction=compaction,
        sparse_indexes_supported=offered.sparse_indexes,
        compaction_supported=offered.compaction,
    )


async def _integer_now(reader: PostgresReader, name: str, column_type: str) -> NowDesign:
    rows = await reader.query(_NOW_NAMED, (name, column_type), inspection=True)
    if len(rows) != 1:
        return KeptNow()
    return ExistingNow(schema_name=rows[0]["schema_name"], name=rows[0]["name"])


async def now_functions(reader: PostgresReader, column_type: str | None = None) -> tuple[NowFunction, ...]:
    """The functions integer_now may name, for one integer type or for all of them."""
    rows = await reader.query(_NOW_FUNCTIONS, inspection=True)
    found = []
    for row in rows:
        try:
            found.append(NowFunction.model_validate(row))
        except ValidationError:
            continue
    return tuple(item for item in found if column_type is None or item.type == column_type)


async def require_new_function(reader: PostgresReader, schema_name: str, name: str) -> None:
    """Refuse a template function whose name is taken, or a schema this role cannot create in."""
    rows = await reader.query(_NAME_FREE, (name, schema_name, schema_name), inspection=True)
    if len(rows) != 1 or rows[0].get("creatable") is not True:
        raise ActionRefused("not_applicable", f'This connection may not create functions in schema "{schema_name}"')
    if rows[0].get("free") is not True:
        raise ActionRefused(
            "not_applicable", f'A function named "{name}" already exists; choose it from the list or another name',
        )


def proposed_interval(column_type: str) -> Span:
    count = _PROPOSED_COUNT.get(column_type)
    # The default TimescaleDB itself gives a timestamp column.
    return DesignDuration(amount=1, unit="week") if count is None else count_span(count)


@dataclass(frozen=True)
class TableCandidate:
    """An ordinary table the editor may convert, before a column is chosen (D207)."""

    extension_version: str
    conversion: ConversionState
    facts: TableFacts
    per_chunk_defaults: bool
    row_estimate: int | None
    # For every integer type, since the column is still to be chosen.
    now_functions: tuple[NowFunction, ...] = ()
    capabilities: Capabilities = Capabilities(sparse_indexes=False, compaction=False, uuid_time=False)


async def is_hypertable(reader: PostgresReader, schema_name: str, table_name: str) -> bool:
    # Discovery first, so a database without the extension says that rather than
    # failing on a view it does not have.
    require_available(await discover(reader))
    await require_public_view(reader, "hypertables", ("hypertable_schema", "hypertable_name"))
    rows = await reader.query(_IS_HYPERTABLE, (schema_name, table_name), inspection=True)
    return len(rows) == 1 and rows[0].get("converted") is True


async def row_estimate(reader: PostgresReader, relation_oid: str) -> int | None:
    rows = await reader.query(_ESTIMATE, (relation_oid,), inspection=True)
    value = rows[0].get("rows") if len(rows) == 1 else None
    return value if isinstance(value, int) and value >= 0 else None


async def read_table(reader: PostgresReader, schema_name: str, table_name: str) -> TableCandidate:
    """An ordinary table as a conversion would find it; refuses what cannot become a hypertable."""
    version = require_available(await discover(reader))
    for view, columns in _VIEWS.items():
        await require_public_view(reader, view, columns)
    offered = await capabilities(reader, version)
    conversion = await inspect_conversion(
        reader, schema_name, table_name, allow_rows=True, allow_integer=True, allow_uuid=offered.uuid_time,
    )
    return TableCandidate(
        extension_version=version,
        conversion=conversion,
        facts=await _table_facts(reader, conversion.target.relation_oid),
        per_chunk_defaults=release(version) >= PER_CHUNK_DEFAULTS,
        row_estimate=await row_estimate(reader, conversion.target.relation_oid),
        now_functions=await now_functions(reader),
        capabilities=offered,
    )


def span_length(column_type: str, interval: Span) -> int:
    """The interval as Timescale stores it for this column; refuses a unit the column cannot take."""
    if column_type in INTEGER_TYPES:
        if not isinstance(interval, IntegerSpan):
            raise ActionRefused("not_applicable", "A chunk interval of an integer column is a number of its values")
        if int(interval.amount) > INTEGER_MAX[column_type]:
            raise ActionRefused(
                "not_applicable", f"A chunk interval of a {column_type} column is at most {INTEGER_MAX[column_type]:,}",
            )
        return int(interval.amount)
    microseconds = None if isinstance(interval, IntegerSpan) else duration_microseconds(interval)
    if microseconds is None:
        raise ActionRefused("not_applicable", "A chunk interval is counted in minutes, hours, days or weeks")
    return microseconds


def converted(candidate: TableCandidate, column: ConversionColumn, interval: Span) -> CurrentHypertable:
    """The hypertable right after converting by this column, before anything else is set.

    Planning every other step against it means a conversion and its settings are
    planned by the same rules as the settings of a hypertable that exists.
    """
    length = span_length(column.type, interval)
    target = candidate.conversion.target
    return CurrentHypertable(
        extension_version=candidate.extension_version,
        target=DesignTarget(
            database_oid=target.database_oid, relation_oid=target.relation_oid,
            schema_name=target.schema_name, table_name=target.table_name,
            column_name=column.name, column_type=column.type,
        ),
        design=HypertableDesign(
            time_column=column.name,
            chunk_interval=interval,
            columnstore=ColumnstoreDesign(
                enabled=False,
                segment_by=ChosenByTimescale() if candidate.per_chunk_defaults else NoColumns(),
            ),
        ),
        interval_length=length,
        columns=candidate.facts.columns,
        unique_keys=candidate.facts.unique_keys,
        indexes=candidate.facts.indexes,
        available_tablespaces=candidate.facts.tablespaces,
        retention=None,
        compression=None,
        reorder=None,
        per_chunk_defaults=candidate.per_chunk_defaults,
        # Moving rows in makes chunks, so what needs none is planned as if there were some.
        has_chunks=not candidate.conversion.empty,
        compressed_chunks=False,
        now_functions=tuple(item for item in candidate.now_functions if item.type == column.type),
        sparse_indexes_supported=candidate.capabilities.sparse_indexes,
        compaction_supported=candidate.capabilities.compaction,
    )


def _preferred(columns: tuple[ConversionColumn, ...]) -> ConversionColumn:
    # A time column before any integer one, which is as likely an id as a clock;
    # then one that already requires a value, which converts with one rule fewer.
    timed = [column for column in columns if column.type in _TIME_TYPES] or list(columns)
    return next((column for column in timed if column.not_null), timed[0])


def state_of_table(node_id: str, candidate: TableCandidate) -> HypertableDesignState:
    choice = _preferred(candidate.conversion.columns)
    proposed = converted(candidate, choice, proposed_interval(choice.type))
    return HypertableDesignState(
        node_id=node_id,
        hypertable=False,
        design=proposed.design,
        extension_version=candidate.extension_version,
        time_column=choice.name,
        time_column_type=choice.type,
        columns=[HypertableColumn(name=item.name, type=item.type, orderable=item.orderable)
                 for item in candidate.facts.columns],
        time_columns=[time_column(item.name, item.type) for item in candidate.conversion.columns],
        row_estimate=candidate.row_estimate,
        indexes=list(candidate.facts.indexes),
        tablespaces=list(candidate.facts.tablespaces),
        # Every unit some column allows, since the column is still to be chosen; the
        # plan refuses hours for a date column, saying so.
        interval_units=["minute", "hour", "day", "week"],
        policy_units=["hour", "day", "week", "month", "year"],
        merge_units=["minute", "hour", "day", "week"],
        per_chunk_defaults=candidate.per_chunk_defaults,
        has_chunks=not candidate.conversion.empty,
        now_functions=list(candidate.now_functions),
        schema_name=candidate.conversion.target.schema_name,
        sparse_indexes_supported=candidate.capabilities.sparse_indexes,
        compaction_supported=candidate.capabilities.compaction,
    )


def time_column(name: str, column_type: str) -> HypertableColumn:
    """A column a table may be partitioned by, with what the editor proposes for it."""
    return HypertableColumn(
        name=name, type=column_type, orderable=True,
        chunk_interval=proposed_interval(column_type), now_templates=list(NOW_TEMPLATES.get(column_type, ())),
    )


def interval_units(target: DesignTarget) -> list[DurationUnit]:
    """The units of a time column's intervals; none for an integer column, counted in its values."""
    if target.column_type in INTEGER_TYPES:
        return []
    if target.column_type == "date":
        return ["day", "week"]
    return ["minute", "hour", "day", "week"]


def policy_units(target: DesignTarget) -> list[DurationUnit]:
    if target.column_type in INTEGER_TYPES:
        return []
    units: list[DurationUnit] = ["hour", "day", "week", "month", "year"]
    return [unit for unit in units if not (target.column_type == "date" and unit in _SUBDAY)]


def state_of(node_id: str, current: CurrentHypertable) -> HypertableDesignState:
    reorder = current.reorder
    return HypertableDesignState(
        node_id=node_id,
        design=current.design,
        extension_version=current.extension_version,
        time_column=current.target.column_name,
        time_column_type=current.target.column_type,
        columns=[HypertableColumn(name=item.name, type=item.type, orderable=item.orderable) for item in current.columns],
        time_columns=[time_column(current.target.column_name, current.target.column_type)],
        indexes=list(current.indexes),
        tablespaces=list(current.available_tablespaces),
        interval_units=interval_units(current.target),
        policy_units=policy_units(current.target),
        merge_units=interval_units(current.target),
        per_chunk_defaults=current.per_chunk_defaults,
        has_chunks=current.has_chunks,
        compressed_chunks=current.compressed_chunks,
        retention=_describe("drops", current.retention),
        columnstore_policy=_describe("compresses", current.compression),
        reorder=None if reorder is None else CurrentPolicy(
            job_id=reorder.job_id,
            description=(
                f"Job {reorder.job_id} reorders chunks by "
                f"{reorder.index_name or 'an index this editor cannot read'}"
                + ("" if reorder.scheduled else "; paused")
            ),
        ),
        now_functions=list(current.now_functions),
        integer_now_name=current.integer_now_name,
        schema_name=current.target.schema_name,
        sparse_indexes_supported=current.sparse_indexes_supported,
        compaction_supported=current.compaction_supported,
    )


async def read_state(reader: PostgresReader, node_id: str, schema_name: str, table_name: str) -> HypertableDesignState:
    try:
        async with asyncio.timeout(5):
            if await is_hypertable(reader, schema_name, table_name):
                return state_of(node_id, await read_current(reader, schema_name, table_name))
            return state_of_table(node_id, await read_table(reader, schema_name, table_name))
    except ActionRefused as exc:
        return HypertableDesignState(node_id=node_id, reason=exc.message)
    except TimeoutError:
        return HypertableDesignState(node_id=node_id, reason="Reading the hypertable timed out")
    except (AdapterError, ValueError):
        return HypertableDesignState(node_id=node_id, reason="The hypertable could not be inspected safely")
