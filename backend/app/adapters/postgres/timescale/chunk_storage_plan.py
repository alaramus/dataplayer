"""Plan converting whole chunks of one time hypertable between rowstore and columnstore."""

import asyncio

from psycopg import sql

from app.adapters.actions import ActionRefused
from app.adapters.operations import MAX_OPERATION_TARGETS
from app.adapters.postgres.inspection import PostgresReader
from app.adapters.postgres.timescale.age_policy_plan import require_compression
from app.adapters.postgres.timescale.api import RoutineShape, extension_routine
from app.adapters.postgres.timescale.plans import (
    ChunkStorage,
    ChunkStoragePlan,
    ChunkStorageUnit,
    ChunkWindow,
)
from app.adapters.postgres.timescale.profile import discover, require_available
from app.adapters.postgres.timescale.report_access import require_public_view
from app.adapters.postgres.timescale.targets import time_hypertable
from app.adapters.protocol import AdapterError
from app.core.translation import say

STORAGES: tuple[ChunkStorage, ...] = ("columnstore", "rowstore")

# sql/maintenance_utils.sql: the chunk and one boolean, returning the chunk.
# regclass 2205, boolean 16. 2.18 and 2.19 append hypercore_use_access_method to
# compress_chunk and later releases drop it again, so it is left at its default;
# the convert_to_* procedures call the same C functions and are not used.
ROUTINES: dict[ChunkStorage, RoutineShape] = {
    "columnstore": RoutineShape("compress_chunk", "f", "2205 16", 2205),
    "rowstore": RoutineShape("decompress_chunk", "f", "2205 16", 2205),
}

CHUNK_COLUMNS = (
    "hypertable_schema", "hypertable_name", "chunk_schema", "chunk_name",
    "range_start", "range_end", "is_compressed",
)

# Whole chunks only: one reaching outside the window is not selected. One row
# more than a job may hold, so a larger window is refused rather than cut.
_SELECTED = sql.SQL("""
SELECT chunk.chunk_schema AS schema_name, chunk.chunk_name AS name,
       chunk.range_start::text AS range_start, chunk.range_end::text AS range_end
FROM timescaledb_information.chunks AS chunk
WHERE chunk.hypertable_schema = %s AND chunk.hypertable_name = %s
  AND chunk.is_compressed = %s
  AND chunk.range_end <= %s::pg_catalog.timestamptz
  AND (%s::pg_catalog.timestamptz IS NULL OR chunk.range_start >= %s::pg_catalog.timestamptz)
ORDER BY chunk.range_start, chunk.chunk_schema, chunk.chunk_name
LIMIT {}
""").format(sql.Literal(MAX_OPERATION_TARGETS + 1)).as_string()

_ALREADY = """
SELECT count(*) AS already
FROM timescaledb_information.chunks AS chunk
WHERE chunk.hypertable_schema = %s AND chunk.hypertable_name = %s
  AND chunk.is_compressed = %s
  AND chunk.range_end <= %s::pg_catalog.timestamptz
  AND (%s::pg_catalog.timestamptz IS NULL OR chunk.range_start >= %s::pg_catalog.timestamptz)
"""


async def inspect_chunk_unit(
    reader: PostgresReader, schema_name: str, table_name: str, storage: ChunkStorage,
) -> ChunkStorageUnit:
    """The hypertable and the storage API a unit uses; the caller bounds the time."""
    version = require_available(await discover(reader))
    target = await time_hypertable(reader, schema_name, table_name)
    await require_compression(reader, target)
    await require_public_view(reader, "chunks", CHUNK_COLUMNS)
    routine = await extension_routine(reader, version, ROUTINES[storage])
    return ChunkStorageUnit.model_validate({
        "target": target,
        "strategy": {
            "storage": storage,
            "extension_version": version,
            "function_schema": routine.schema_name,
            "function_oid": routine.oid,
        },
    })


async def plan_chunk_storage(
    reader: PostgresReader, schema_name: str, table_name: str, storage: ChunkStorage,
    window: ChunkWindow,
) -> ChunkStoragePlan:
    """The exact chunks a job would convert, fixed now rather than when it runs."""
    try:
        async with asyncio.timeout(5):
            unit = await inspect_chunk_unit(reader, schema_name, table_name, storage)
            identity = (unit.target.schema_name, unit.target.table_name)
            bounds = (window.ends_by, window.starts_from, window.starts_from)
            chunks = await reader.query(
                _SELECTED, (*identity, storage == "rowstore", *bounds), inspection=True,
            )
            counted = await reader.query(
                _ALREADY, (*identity, storage == "columnstore", *bounds), inspection=True,
            )
            already = counted[0].get("already") if len(counted) == 1 else None
            if not isinstance(already, int) or isinstance(already, bool):
                raise ActionRefused("not_applicable", say("TimescaleDB chunk metadata could not be read"))
            if len(chunks) > MAX_OPERATION_TARGETS:
                raise ActionRefused("too_large", say(
                    "More than {count} chunks lie inside this window; narrow it", count=MAX_OPERATION_TARGETS,
                ))
            if not chunks:
                raise ActionRefused("not_applicable", _nothing_left(storage, already))
            return ChunkStoragePlan.model_validate({
                "unit": unit, "window": window, "chunks": chunks, "already": already,
            })
    except TimeoutError:
        raise ActionRefused("not_applicable", say("TimescaleDB chunk planning timed out")) from None
    except (AdapterError, ValueError):
        raise ActionRefused(
            "not_applicable", say("TimescaleDB chunk metadata could not be inspected safely"),
        ) from None


def _nothing_left(storage: ChunkStorage, already: int) -> str:
    if not already:
        return say("No whole chunk lies inside this window")
    if storage == "columnstore":
        return say("Every whole chunk inside this window is already compressed")
    return say("No whole chunk inside this window is compressed")
