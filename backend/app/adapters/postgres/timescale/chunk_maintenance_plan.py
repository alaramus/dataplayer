"""Plan chunk maintenance over a fixed set of chunks, executing nothing (D208).

Every operation names its chunks at review: a drop never re-evaluates an age
when it runs, and a merge, a split or an attach carries the exact chunks and
bounds it was reviewed with in its unit, so a source that changed in between
refuses the unit instead of doing something else.

An owned hypertable cut along one time or integer column is maintained here,
with hash dimensions beside it. Which hash partition a chunk belongs to is not
in the public views (D121), and without it neither a merge nor an attach can be
checked before it is sent, so those two refuse a hypertable with any; a split
is refused there by TimescaleDB itself.
"""

import asyncio
import json
from datetime import datetime
from typing import Literal

from psycopg import sql
from pydantic import BaseModel, ConfigDict, Field

from app.adapters.actions import ActionRefused
from app.adapters.operations import MAX_OPERATION_TARGETS
from app.adapters.postgres.inspection import PostgresReader
from app.adapters.postgres.timescale.api import RoutineShape, extension_routine
from app.adapters.postgres.timescale.design_state import release
from app.adapters.postgres.timescale.plans import (
    BoundWindow,
    ChunkRef,
    MaintainedHypertable,
    PlannedChunk,
    ReviewedPlan,
)
from app.adapters.postgres.timescale.profile import discover, require_available
from app.adapters.postgres.timescale.report_access import require_public_view
from app.adapters.postgres.timescale.targets import maintained_hypertable
from app.adapters.protocol import AdapterError

Maintenance = Literal["drop", "move", "reorder", "detach", "merge", "merge_concurrently", "split", "attach"]
# Both take a group of adjacent chunks as one unit.
MERGES: frozenset[Maintenance] = frozenset({"merge", "merge_concurrently"})
_OID = r"^[1-9][0-9]{0,9}$"

# sql/maintenance_utils.sql and sql/ddl_api.sql. regclass 2205, name 19,
# regclass[] 2210, "any" 2276, jsonb 3802; void 2278. move_chunk and
# reorder_chunk are TSL and absent from an Apache-only build; merge_chunks
# arrived in 2.18, split_chunk in 2.20, attach and detach in 2.21, and their
# absence is found by discovery rather than by release (D120).
ROUTINES: dict[Maintenance, RoutineShape] = {
    "move": RoutineShape("move_chunk", "f", "2205 19", 2278),
    "reorder": RoutineShape("reorder_chunk", "f", "2205 2205", 2278),
    "detach": RoutineShape("detach_chunk", "p", "2205", 2278),
    "merge": RoutineShape("merge_chunks", "p", "2210", 2278, exclusive=False),
    # 2.29: a merge that lets reads go on, and commits by itself.
    "merge_concurrently": RoutineShape("merge_chunks_concurrently", "p", "2210", 2278),
    "split": RoutineShape("split_chunk", "p", "2205 2276", 2278),
    "attach": RoutineShape("attach_chunk", "p", "2205 2205 3802", 2278),
}
# A merge of compressed chunks has no routine of its own to inspect, so the
# release that learned it is declared; the matrix holds 2.18.0, which refuses
# it, and 2.19.3, which does it.
MERGE_COMPRESSED = (2, 19, 0)
# Each one rewrites or locks whole chunks, so one per job is a unit.
PER_CHUNK: frozenset[Maintenance] = frozenset({"drop", "move", "reorder", "detach"})
# What cannot be checked without knowing a chunk's hash partition, by what it does.
NEEDS_PARTITION: dict[Maintenance, str] = {"merge": "merged", "merge_concurrently": "merged", "attach": "attached"}

CHUNK_COLUMNS = (
    "hypertable_schema", "hypertable_name", "chunk_schema", "chunk_name",
    "range_start", "range_end", "range_start_integer", "range_end_integer", "is_compressed",
)

# Whole chunks only, with where each one is stored: a chunk in the database's
# default tablespace has no tablespace of its own in pg_class.
_WINDOW = """
SELECT chunk.chunk_schema AS schema_name, chunk.chunk_name AS name,
       chunk.{start}::text AS range_start, chunk.{end}::text AS range_end,
       chunk.is_compressed,
       COALESCE(own.spcname, fallback.spcname) AS tablespace
FROM timescaledb_information.chunks AS chunk
JOIN pg_catalog.pg_namespace AS namespace ON namespace.nspname = chunk.chunk_schema
JOIN pg_catalog.pg_class AS relation
  ON relation.relnamespace = namespace.oid AND relation.relname = chunk.chunk_name
JOIN pg_catalog.pg_database AS database ON database.datname = pg_catalog.current_database()
JOIN pg_catalog.pg_tablespace AS fallback ON fallback.oid = database.dattablespace
LEFT JOIN pg_catalog.pg_tablespace AS own ON own.oid = relation.reltablespace
WHERE chunk.hypertable_schema = %s AND chunk.hypertable_name = %s
  AND chunk.{end} <= %s::{bound}
  AND (%s::{bound} IS NULL OR chunk.{start} >= %s::{bound})
ORDER BY chunk.{start}, chunk.chunk_schema, chunk.chunk_name
LIMIT {limit}
"""

# The chunks somebody picked by name, read the way the window reads them.
_PICKED = """
SELECT chunk.chunk_schema AS schema_name, chunk.chunk_name AS name,
       chunk.{start}::text AS range_start, chunk.{end}::text AS range_end,
       chunk.is_compressed,
       COALESCE(own.spcname, fallback.spcname) AS tablespace
FROM timescaledb_information.chunks AS chunk
JOIN pg_catalog.pg_namespace AS namespace ON namespace.nspname = chunk.chunk_schema
JOIN pg_catalog.pg_class AS relation
  ON relation.relnamespace = namespace.oid AND relation.relname = chunk.chunk_name
JOIN pg_catalog.pg_database AS database ON database.datname = pg_catalog.current_database()
JOIN pg_catalog.pg_tablespace AS fallback ON fallback.oid = database.dattablespace
LEFT JOIN pg_catalog.pg_tablespace AS own ON own.oid = relation.reltablespace
WHERE chunk.hypertable_schema = %s AND chunk.hypertable_name = %s
  AND (chunk.chunk_schema::text, chunk.chunk_name::text) IN (
      SELECT * FROM ROWS FROM (pg_catalog.unnest(%s::text[]), pg_catalog.unnest(%s::text[]))
  )
ORDER BY chunk.{start}, chunk.chunk_schema, chunk.chunk_name
"""

# Compared in the column's own type, so a date or a timestamp without a time
# zone is read the way the source partitions it. A hypertable with hash
# dimensions has a chunk per partition here; LIMIT 2 still tells one from many.
_HOLDING = """
SELECT chunk.chunk_schema AS schema_name, chunk.chunk_name AS name,
       chunk.{start}::text AS range_start, chunk.{end}::text AS range_end,
       chunk.is_compressed
FROM timescaledb_information.chunks AS chunk
WHERE chunk.hypertable_schema = %s AND chunk.hypertable_name = %s
  AND chunk.{start} < %s::{bound} AND chunk.{end} > %s::{bound}
LIMIT 2
"""

_OVERLAP = """
SELECT chunk.chunk_name AS name
FROM timescaledb_information.chunks AS chunk
WHERE chunk.hypertable_schema = %s AND chunk.hypertable_name = %s
  AND chunk.{start} < %s::{bound} AND chunk.{end} > %s::{bound}
ORDER BY chunk.{start}
LIMIT 1
"""

# The index a move orders rows by when none is named: the one leading with the
# time column, as create_hypertable makes it; the oldest of several.
_TIME_INDEX = """
SELECT index_class.relname AS name
FROM pg_catalog.pg_index AS table_index
JOIN pg_catalog.pg_class AS index_class ON index_class.oid = table_index.indexrelid
JOIN pg_catalog.pg_attribute AS attribute
  ON attribute.attrelid = table_index.indrelid AND attribute.attnum = table_index.indkey[0]
WHERE table_index.indrelid = %s::pg_catalog.oid AND attribute.attname = %s
  AND table_index.indisvalid AND table_index.indisready
ORDER BY index_class.oid
LIMIT 1
"""

_TABLESPACE = """
SELECT spcname AS name FROM pg_catalog.pg_tablespace
WHERE spcname = %s AND spcname <> 'pg_global' AND pg_catalog.has_tablespace_privilege(oid, 'CREATE')
"""

_INDEX = """
SELECT index_class.relname AS name
FROM pg_catalog.pg_index AS table_index
JOIN pg_catalog.pg_class AS index_class ON index_class.oid = table_index.indexrelid
WHERE table_index.indrelid = %s::pg_catalog.oid AND index_class.relname = %s
  AND table_index.indisvalid AND table_index.indisready
"""

# A table that may become a chunk: ordinary, owned, alone, and nobody's chunk
# or hypertable yet. TimescaleDB checks its columns itself and refuses.
_ATTACHABLE = """
SELECT relation.relkind::text AS relkind,
       pg_catalog.pg_has_role(relation.relowner, 'USAGE') AS owned,
       EXISTS (
           SELECT 1 FROM pg_catalog.pg_inherits AS inheritance
           WHERE inheritance.inhrelid = relation.oid OR inheritance.inhparent = relation.oid
       ) AS inherits,
       EXISTS (
           SELECT 1 FROM timescaledb_information.hypertables AS hypertable
           WHERE hypertable.hypertable_schema = namespace.nspname
             AND hypertable.hypertable_name = relation.relname
       ) AS hypertable,
       EXISTS (
           SELECT 1 FROM timescaledb_information.chunks AS chunk
           WHERE chunk.chunk_schema = namespace.nspname AND chunk.chunk_name = relation.relname
       ) AS chunk
FROM pg_catalog.pg_class AS relation
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
WHERE namespace.nspname = %s AND relation.relname = %s
"""

_COLUMN_CAST = {
    "timestamp with time zone": "pg_catalog.timestamptz",
    "timestamp without time zone": "pg_catalog.timestamp",
    "date": "pg_catalog.date",
    "smallint": "pg_catalog.int2",
    "integer": "pg_catalog.int4",
    "bigint": "pg_catalog.int8",
}


# What the forms offer, read by name: the choices are a convenience the plan
# checks again, never what decides.
_TABLESPACE_CHOICES = """
SELECT spcname AS name FROM pg_catalog.pg_tablespace
WHERE spcname <> 'pg_global' AND pg_catalog.has_tablespace_privilege(oid, 'CREATE')
ORDER BY 1
"""

_INDEX_CHOICES = """
SELECT index_class.relname AS name
FROM pg_catalog.pg_index AS table_index
JOIN pg_catalog.pg_class AS index_class ON index_class.oid = table_index.indexrelid
JOIN pg_catalog.pg_class AS relation ON relation.oid = table_index.indrelid
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
WHERE namespace.nspname = %s AND relation.relname = %s
  AND table_index.indisvalid AND table_index.indisready
ORDER BY 1
"""


async def tablespace_names(reader: PostgresReader) -> list[str]:
    return [str(row["name"]) for row in await reader.query(_TABLESPACE_CHOICES, inspection=True)]


async def index_names(reader: PostgresReader, schema_name: str, table_name: str) -> list[str]:
    return [str(row["name"]) for row in await reader.query(_INDEX_CHOICES, (schema_name, table_name), inspection=True)]


def column_cast(target: MaintainedHypertable) -> sql.SQL:
    return sql.SQL(_COLUMN_CAST[target.column_type])


def _ranged(query: str, target: MaintainedHypertable) -> str:
    """A chunk query over the range columns the public view fills for this kind of column."""
    integer = target.integer
    return sql.SQL(query).format(
        start=sql.Identifier("range_start_integer" if integer else "range_start"),
        end=sql.Identifier("range_end_integer" if integer else "range_end"),
        bound=sql.SQL("pg_catalog.int8" if integer else "pg_catalog.timestamptz"),
        cast=column_cast(target),
        limit=sql.Literal(MAX_OPERATION_TARGETS + 1),
    ).as_string()


def require_kind(target: MaintainedHypertable, *bounds: int | datetime | None) -> None:
    """Instants for a hypertable over time, its values for one over an integer column."""
    for bound in bounds:
        if bound is None:
            continue
        if target.integer and isinstance(bound, datetime):
            raise _refuse(
                f'This hypertable is partitioned by the integer column "{target.column_name}"; '
                "give its values, not instants",
            )
        if not target.integer and not isinstance(bound, datetime):
            raise _refuse(
                f'This hypertable is partitioned by time on "{target.column_name}"; give instants, not numbers',
            )


class MaintenanceStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal["chunk_maintenance_v1"] = "chunk_maintenance_v1"
    extension_version: str = Field(min_length=1, max_length=50)
    # None for a drop, which is PostgreSQL's DROP TABLE on the chunk.
    function_schema: str | None = Field(default=None, min_length=1, max_length=63)
    function_oid: str | None = Field(default=None, pattern=_OID)


class MaintenanceArguments(BaseModel):
    """What every unit of one operation runs with, fixed at review."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tablespace: str | None = Field(default=None, min_length=1, max_length=63)
    index_tablespace: str | None = Field(default=None, min_length=1, max_length=63)
    index: str | None = Field(default=None, min_length=1, max_length=63)
    # The source's own text of an instant or a bound in the column's type.
    split_at: str | None = Field(default=None, min_length=1, max_length=100)
    table_schema: str | None = Field(default=None, min_length=1, max_length=63)
    table_name: str | None = Field(default=None, min_length=1, max_length=63)
    slices: str | None = Field(default=None, min_length=1, max_length=500)


class MaintenanceUnit(ReviewedPlan):
    """What each unit is checked against before it runs; the group is part of it."""

    operation: Literal["chunk_maintenance"] = "chunk_maintenance"
    maintenance: Maintenance
    target: MaintainedHypertable
    strategy: MaintenanceStrategy
    arguments: MaintenanceArguments = Field(default_factory=MaintenanceArguments)
    # A merge's chunks or a split's one: the unit is about exactly these.
    group: tuple[PlannedChunk, ...] = ()


# Whole chunks inside a window, or exactly the chunks somebody picked (D209).
Selection = BoundWindow | tuple[ChunkRef, ...]


class MaintenancePlan(ReviewedPlan):
    unit: MaintenanceUnit
    window: BoundWindow | None = None
    # Chosen by name in the Chunks report rather than by a window.
    picked: bool = False
    # The chunks the job changes, in time order; one per unit except for a merge.
    chunks: tuple[PlannedChunk, ...] = Field(default=(), max_length=MAX_OPERATION_TARGETS)
    # Chunks inside the window the operation leaves as they are, with why.
    skipped: int = Field(default=0, strict=True, ge=0)
    skipped_because: str | None = None


def _refuse(message: str) -> ActionRefused:
    return ActionRefused("not_applicable", message)


async def inspect_unit(
    reader: PostgresReader, schema_name: str, table_name: str, maintenance: Maintenance,
) -> MaintenanceUnit:
    """The hypertable and the API one operation uses, with no arguments yet."""
    version = require_available(await discover(reader))
    target = await maintained_hypertable(reader, schema_name, table_name)
    if target.hash_columns and maintenance in NEEDS_PARTITION:
        columns = ", ".join(f'"{column}"' for column in target.hash_columns)
        raise _refuse(
            f"Chunks of a hypertable partitioned by hash on {columns} are not {NEEDS_PARTITION[maintenance]} "
            "here: which partition a chunk is in is not public, so the result could not be checked first",
        )
    if target.hash_columns and maintenance == "split":
        raise _refuse("TimescaleDB splits no chunk of a hypertable partitioned by hash as well as by time")
    await require_public_view(reader, "chunks", CHUNK_COLUMNS)
    strategy = MaintenanceStrategy(extension_version=version)
    shape = ROUTINES.get(maintenance)
    if shape is not None:
        routine = await extension_routine(reader, version, shape)
        strategy = MaintenanceStrategy(
            extension_version=version, function_schema=routine.schema_name, function_oid=routine.oid,
        )
    return MaintenanceUnit(maintenance=maintenance, target=target, strategy=strategy)


async def _window(
    reader: PostgresReader, target: MaintainedHypertable, window: BoundWindow,
) -> list[dict[str, object]]:
    require_kind(target, window.ends_by, window.starts_from)
    rows = await reader.query(_ranged(_WINDOW, target), (
        target.schema_name, target.table_name, window.ends_by, window.starts_from, window.starts_from,
    ), inspection=True)
    if len(rows) > MAX_OPERATION_TARGETS:
        raise ActionRefused(
            "too_large", f"More than {MAX_OPERATION_TARGETS} chunks lie inside this window; narrow it",
        )
    if not rows:
        raise _refuse("No whole chunk lies inside this window")
    return rows


async def _picked(
    reader: PostgresReader, target: MaintainedHypertable, picked: tuple[ChunkRef, ...],
) -> list[dict[str, object]]:
    if not picked:
        raise _refuse("Pick at least one chunk")
    if len(picked) > MAX_OPERATION_TARGETS:
        raise ActionRefused("too_large", f"Pick at most {MAX_OPERATION_TARGETS} chunks at a time")
    rows = await reader.query(_ranged(_PICKED, target), (
        target.schema_name, target.table_name,
        [chunk.schema_name for chunk in picked], [chunk.name for chunk in picked],
    ), inspection=True)
    found = {(row["schema_name"], row["name"]) for row in rows}
    gone = next((chunk for chunk in picked if (chunk.schema_name, chunk.name) not in found), None)
    if gone is not None:
        raise _refuse(f'"{gone.name}" is not a chunk of this hypertable any more')
    return rows


async def picked_left(reader: PostgresReader, target: MaintainedHypertable, picked: tuple[ChunkRef, ...]) -> int:
    """How many of the picked chunks are still chunks of the hypertable."""
    rows = await reader.query(_ranged(_PICKED, target), (
        target.schema_name, target.table_name,
        [chunk.schema_name for chunk in picked], [chunk.name for chunk in picked],
    ), inspection=True)
    return len(rows)


def _planned(row: dict[str, object]) -> PlannedChunk:
    return PlannedChunk.model_validate({key: row[key] for key in ("schema_name", "name", "range_start", "range_end")})


async def _require_tablespace(reader: PostgresReader, name: str) -> None:
    if not await reader.query(_TABLESPACE, (name,), inspection=True):
        raise _refuse(f'Tablespace "{name}" does not exist or this connection may not create in it')


async def plan_window_maintenance(
    reader: PostgresReader, schema_name: str, table_name: str, maintenance: Maintenance,
    selection: Selection, arguments: MaintenanceArguments,
) -> MaintenancePlan:
    """The exact chunks a per-chunk operation or a merge would change."""
    try:
        async with asyncio.timeout(5):
            unit = await inspect_unit(reader, schema_name, table_name, maintenance)
            target = unit.target
            window = selection if isinstance(selection, BoundWindow) else None
            rows = (
                await _window(reader, target, window) if window is not None
                else await _picked(reader, target, selection if isinstance(selection, tuple) else ())
            )
            keep: list[dict[str, object]] = rows
            because: str | None = None
            match maintenance:
                case "move":
                    tablespace = arguments.tablespace or ""
                    await _require_tablespace(reader, tablespace)
                    if arguments.index_tablespace is not None:
                        await _require_tablespace(reader, arguments.index_tablespace)
                    arguments = await ordering_index(reader, target, arguments)
                    keep = [row for row in rows if row["tablespace"] != tablespace]
                    because = f"already in {sql.Identifier(tablespace).as_string()}"
                case "reorder":
                    if not await reader.query(_INDEX, (target.relation_oid, arguments.index), inspection=True):
                        raise _refuse(f'This hypertable has no index "{arguments.index}"')
                    keep = [row for row in rows if row["is_compressed"] is not True]
                    because = "compressed, which reorder_chunk does not rewrite"
                case "detach":
                    keep = [row for row in rows if row["is_compressed"] is not True]
                    because = "compressed; TimescaleDB detaches only uncompressed chunks"
                case "merge" | "merge_concurrently":
                    _require_mergeable(rows, unit.strategy.extension_version)
            if not keep:
                which = "whole chunk inside this window" if window is not None else "picked chunk"
                raise _refuse(f"Every {which} is {because}")
            chunks = tuple(_planned(row) for row in keep)
            if maintenance in MERGES:
                unit = unit.model_copy(update={"group": chunks})
            unit = unit.model_copy(update={"arguments": arguments})
            return MaintenancePlan(
                unit=unit, window=window, picked=window is None, chunks=chunks,
                skipped=len(rows) - len(keep), skipped_because=because if len(rows) > len(keep) else None,
            )
    except TimeoutError:
        raise _refuse("TimescaleDB chunk planning timed out") from None
    except (AdapterError, ValueError):
        raise _refuse("TimescaleDB chunk metadata could not be inspected safely") from None


async def ordering_index(
    reader: PostgresReader, target: MaintainedHypertable, arguments: MaintenanceArguments,
) -> MaintenanceArguments:
    if arguments.index is not None:
        if not await reader.query(_INDEX, (target.relation_oid, arguments.index), inspection=True):
            raise _refuse(f'This hypertable has no index "{arguments.index}"')
        return arguments
    found = await reader.query(_TIME_INDEX, (target.relation_oid, target.column_name), inspection=True)
    if not found:
        raise _refuse("Name an index: moving a chunk rewrites it in an index's order")
    return arguments.model_copy(update={"index": str(found[0]["name"])})


async def chunk_holds(reader: PostgresReader, target: MaintainedHypertable, at: int | datetime) -> bool:
    """Whether some chunk still holds this point strictly inside its range."""
    return bool(await reader.query(
        _ranged(_HOLDING, target), (target.schema_name, target.table_name, at, at), inspection=True,
    ))


async def window_count(reader: PostgresReader, target: MaintainedHypertable, window: BoundWindow) -> int:
    rows = await reader.query(_ranged(_WINDOW, target), (
        target.schema_name, target.table_name, window.ends_by, window.starts_from, window.starts_from,
    ), inspection=True)
    return len(rows)


def _require_mergeable(rows: list[dict[str, object]], version: str) -> None:
    if len(rows) < 2:
        raise _refuse("A merge needs at least two chunks")
    for before, after in zip(rows, rows[1:], strict=False):
        if before["range_end"] != after["range_start"]:
            raise _refuse(
                f'Chunks "{before["name"]}" and "{after["name"]}" are not adjacent; '
                "choose chunks that touch",
            )
    if any(row["is_compressed"] is True for row in rows) and release(version) < MERGE_COMPRESSED:
        raise _refuse(f"TimescaleDB {version} cannot merge compressed chunks; decompress them first")


async def plan_split(
    reader: PostgresReader, schema_name: str, table_name: str, at: int | datetime,
) -> MaintenancePlan:
    """The one chunk holding this point, split at it."""
    try:
        async with asyncio.timeout(5):
            unit = await inspect_unit(reader, schema_name, table_name, "split")
            target = unit.target
            require_kind(target, at)
            point = await reader.query(
                _ranged("SELECT (%s::{bound})::{cast}::text AS point", target),
                (at,), inspection=True,
            )
            rows = await reader.query(
                _ranged(_HOLDING, target), (target.schema_name, target.table_name, at, at), inspection=True,
            )
            if len(rows) != 1:
                raise _refuse("No chunk holds this point strictly inside its range")
            chunk = _planned(rows[0])
            return MaintenancePlan(
                unit=unit.model_copy(update={
                    "group": (chunk,), "arguments": MaintenanceArguments(split_at=str(point[0]["point"])),
                }),
                chunks=(chunk,),
            )
    except TimeoutError:
        raise _refuse("TimescaleDB chunk planning timed out") from None
    except (AdapterError, ValueError):
        raise _refuse("TimescaleDB chunk metadata could not be inspected safely") from None


async def plan_attach(
    reader: PostgresReader, schema_name: str, table_name: str,
    table_schema: str, table: str, starts_from: int | datetime, ends_by: int | datetime,
) -> MaintenancePlan:
    """A table made the hypertable's chunk for one range, which no chunk may already cover."""
    try:
        async with asyncio.timeout(5):
            unit = await inspect_unit(reader, schema_name, table_name, "attach")
            target = unit.target
            require_kind(target, starts_from, ends_by)
            await require_public_view(reader, "hypertables", ("hypertable_schema", "hypertable_name"))
            facts = await reader.query(_ATTACHABLE, (table_schema, table), inspection=True)
            if len(facts) != 1:
                raise _refuse(f'There is no table "{table_schema}"."{table}"')
            checks = (
                (facts[0]["relkind"] != "r", "Only an ordinary table can become a chunk"),
                (facts[0]["owned"] is not True, "Only the table's owner can attach it"),
                (facts[0]["hypertable"] is True, "A hypertable cannot become a chunk"),
                (facts[0]["chunk"] is True, "This table is already a chunk"),
                (facts[0]["inherits"] is True, "A table that uses inheritance cannot become a chunk"),
            )
            reason = next((message for failed, message in checks if failed), None)
            if reason is not None:
                raise _refuse(reason)
            overlap = await reader.query(
                _ranged(_OVERLAP, target), (target.schema_name, target.table_name, ends_by, starts_from),
                inspection=True,
            )
            if overlap:
                raise _refuse(f'Chunk "{overlap[0]["name"]}" already covers part of this range')
            bounds = await reader.query(
                _ranged(
                    "SELECT (%s::{bound})::{cast}::text AS range_start, (%s::{bound})::{cast}::text AS range_end",
                    target,
                ),
                (starts_from, ends_by), inspection=True,
            )
            start, end = str(bounds[0]["range_start"]), str(bounds[0]["range_end"])
            if start == end:
                raise _refuse("The range is empty once read in the column's type")
            # The slices are composed here from the source's own text, keyed by
            # the column the source names; nothing in them is the request's.
            # An integer column's bounds are JSON numbers, a time column's its text.
            ends: list[object] = [int(start), int(end)] if target.integer else [start, end]
            slices = json.dumps({target.column_name: ends}, separators=(",", ":"))
            planned = PlannedChunk(schema_name=table_schema, name=table, range_start=start, range_end=end)
            return MaintenancePlan(
                unit=unit.model_copy(update={
                    "group": (planned,),
                    "arguments": MaintenanceArguments(table_schema=table_schema, table_name=table, slices=slices),
                }),
                chunks=(planned,),
            )
    except TimeoutError:
        raise _refuse("TimescaleDB chunk planning timed out") from None
    except (AdapterError, ValueError):
        raise _refuse("TimescaleDB chunk metadata could not be inspected safely") from None
