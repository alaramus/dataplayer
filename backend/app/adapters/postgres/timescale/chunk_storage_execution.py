"""One chunk per source transaction, checked against what was admitted (D123).

Nothing here retries. A unit the source refused rolled back; a unit whose
connection was lost after the conversion was sent is reported as unknown rather
than run again, because its commit may have landed without an answer.
"""

import asyncio
from collections.abc import Sequence

import psycopg
from psycopg import sql

from app.adapters.actions import ActionRefused, RefusalReason
from app.adapters.operations import ObservedState, OperationTarget, UnitOutcome
from app.adapters.postgres.inspection import InspectionReader, PostgresReader
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.chunk_storage_plan import (
    ROUTINES,
    inspect_chunk_unit,
)
from app.adapters.postgres.timescale.plans import ChunkStorage, ChunkStorageUnit
from app.adapters.protocol import AdapterError

# The chunk's live membership in its parent, re-resolved by name for every unit.
_MEMBER = """
SELECT relation.oid::text AS relation_oid, chunk.is_compressed
FROM timescaledb_information.chunks AS chunk
JOIN pg_catalog.pg_namespace AS namespace ON namespace.nspname = chunk.chunk_schema
JOIN pg_catalog.pg_class AS relation
  ON relation.relnamespace = namespace.oid AND relation.relname = chunk.chunk_name
WHERE chunk.hypertable_schema = %s AND chunk.hypertable_name = %s
  AND chunk.chunk_schema = %s AND chunk.chunk_name = %s
LIMIT 2
"""

# ROWS FROM pairs the two arrays: the multi-argument form of unnest is a
# parser construct that cannot be schema-qualified, and every function this
# file names is qualified on purpose.
_OBSERVED = """
SELECT chunk.chunk_schema AS schema_name, chunk.chunk_name AS name, chunk.is_compressed
FROM timescaledb_information.chunks AS chunk
WHERE chunk.hypertable_schema = %s AND chunk.hypertable_name = %s
  AND (chunk.chunk_schema::text, chunk.chunk_name::text) IN (
      SELECT * FROM ROWS FROM (pg_catalog.unnest(%s::text[]), pg_catalog.unnest(%s::text[]))
  )
"""

# A chunk the source cannot lock quickly is refused rather than waited for; one
# taking longer than the statement timeout is rolled back and stops the job.
_REFUSED: dict[str, tuple[RefusalReason, str]] = {
    "55P03": ("conflict", "This chunk is in use; nothing was converted"),
    "40P01": ("conflict", "This chunk is in use; nothing was converted"),
    "57014": (
        "not_applicable",
        "The source cancelled converting this chunk after its fifteen minutes; it was rolled back",
    ),
    "42501": ("not_applicable", "This connection may not convert this chunk"),
}
_UNCONFIRMED = "The connection was lost while this chunk was being converted; its outcome is unknown"


async def convert_chunk(
    session: PostgresSession, schema_name: str, table_name: str, storage: ChunkStorage,
    unit_fingerprint: str, chunk: OperationTarget,
) -> UnitOutcome:
    dispatched = False
    try:
        async with session.acquire() as connection:
            async with connection.transaction():
                await connection.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED, READ WRITE")
                await connection.execute("SET LOCAL lock_timeout = '5s'")
                await connection.execute("SET LOCAL statement_timeout = '15min'")
                unit, relation_oid, compressed = await member(
                    InspectionReader(connection), schema_name, table_name, storage,
                    unit_fingerprint, chunk,
                )
                if compressed is (storage == "columnstore"):
                    return "already"
                routine = ROUTINES[storage].name
                dispatched = True
                await connection.execute(
                    sql.SQL("SELECT {}(%s::pg_catalog.regclass, true)").format(
                        sql.Identifier(unit.strategy.function_schema, routine),
                    ),
                    (relation_oid,),
                )
        return "completed"
    except psycopg.Error as exc:
        raise _failure(exc.sqlstate, dispatched) from None
    except AdapterError:
        if dispatched:
            raise AdapterError("unknown", _UNCONFIRMED) from None
        raise ActionRefused("not_applicable", "The source could not be reached; nothing was converted") from None


async def member(
    reader: PostgresReader, schema_name: str, table_name: str, storage: ChunkStorage,
    unit_fingerprint: str, chunk: OperationTarget,
) -> tuple[ChunkStorageUnit, str, bool]:
    """The admitted unit, and the chunk's relation and storage as its parent holds it now."""
    try:
        async with asyncio.timeout(5):
            unit = await inspect_chunk_unit(reader, schema_name, table_name, storage)
            rows = await reader.query(_MEMBER, (
                unit.target.schema_name, unit.target.table_name, chunk.schema_name, chunk.name,
            ), inspection=True)
    except TimeoutError:
        raise ActionRefused(
            "conflict", "The hypertable could not be checked in time; nothing was converted",
        ) from None
    except (AdapterError, ValueError):
        raise ActionRefused(
            "not_applicable", "The hypertable could not be checked safely; nothing was converted",
        ) from None
    try:
        unit.require_unchanged(unit_fingerprint)
    except ActionRefused:
        raise ActionRefused(
            "conflict",
            "The hypertable or its TimescaleDB API changed after review; nothing was converted",
        ) from None
    relation_oid = rows[0].get("relation_oid") if len(rows) == 1 else None
    compressed = rows[0].get("is_compressed") if len(rows) == 1 else None
    if not isinstance(relation_oid, str) or not isinstance(compressed, bool):
        raise ActionRefused("not_applicable", "This chunk is no longer part of the hypertable")
    return unit, relation_oid, compressed


def _failure(sqlstate: str | None, dispatched: bool) -> Exception:
    state = sqlstate or ""
    if state in _REFUSED:
        reason, message = _REFUSED[state]
        return ActionRefused(reason, message)
    if not dispatched:
        return ActionRefused(
            "not_applicable", "The source could not be reached or prepared; nothing was converted",
        )
    # Whatever the server itself refused rolled the transaction back; only a
    # lost connection can have lost the answer to COMMIT.
    if not state or state[:2] in {"08", "57", "58"}:
        return AdapterError("unknown", _UNCONFIRMED)
    return ActionRefused("not_applicable", "The source refused to convert this chunk")


async def observe_chunks(
    session: PostgresSession, schema_name: str, table_name: str, storage: ChunkStorage,
    targets: Sequence[OperationTarget],
) -> list[ObservedState]:
    """What each chunk holds now; one no longer in the hypertable is gone."""
    async with session.inspection() as reader:
        rows = await reader.query(_OBSERVED, (
            schema_name, table_name,
            [target.schema_name for target in targets], [target.name for target in targets],
        ), inspection=True)
    found = {(row["schema_name"], row["name"]): row["is_compressed"] for row in rows}
    wanted = storage == "columnstore"
    return [_observed(found.get((target.schema_name, target.name)), wanted) for target in targets]


def _observed(compressed: object, wanted: bool) -> ObservedState:
    if not isinstance(compressed, bool):
        return "gone"
    return "as_requested" if compressed is wanted else "unchanged"
