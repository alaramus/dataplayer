"""One unit of chunk maintenance, checked against what was reviewed (D208, D123).

Nothing here retries. A unit the source refused rolled back; one whose
connection was lost after its statement was sent is reported as unknown,
because its commit may have landed without an answer. `move_chunk` and
`reorder_chunk` refuse a transaction block and commit by themselves, so they
run with none, the way VACUUM does in the query runner (D206).
"""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

import psycopg
from psycopg import sql

from app.adapters.actions import ActionRefused, RefusalReason
from app.adapters.operations import ObservedState, OperationTarget, UnitOutcome
from app.adapters.postgres.inspection import InspectionReader, PostgresReader
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.chunk_maintenance_plan import (
    MERGES,
    ROUTINES,
    Maintenance,
    MaintenanceUnit,
    column_cast,
)
from app.adapters.protocol import AdapterError

# A chunk's live membership in its parent and where it is stored now.
_MEMBERS = """
SELECT chunk.chunk_schema AS schema_name, chunk.chunk_name AS name,
       relation.oid::text AS relation_oid, chunk.is_compressed,
       -- The view fills one pair of range columns, by the kind of the time column.
       COALESCE(chunk.range_start::text, chunk.range_start_integer::text) AS range_start,
       COALESCE(chunk.range_end::text, chunk.range_end_integer::text) AS range_end,
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
"""

_TABLE = """
SELECT relation.oid::text AS relation_oid
FROM pg_catalog.pg_class AS relation
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
WHERE namespace.nspname = %s AND relation.relname = %s AND relation.relkind = 'r'
"""

_INDEX = """
SELECT index_class.oid::text AS index_oid
FROM pg_catalog.pg_index AS table_index
JOIN pg_catalog.pg_class AS index_class ON index_class.oid = table_index.indexrelid
WHERE table_index.indrelid = %s::pg_catalog.oid AND index_class.relname = %s
"""

_REFUSED: dict[str, tuple[RefusalReason, str]] = {
    "55P03": ("conflict", "This chunk is in use; nothing was changed"),
    "40P01": ("conflict", "This chunk is in use; nothing was changed"),
    "57014": ("not_applicable", "The source cancelled this unit after its fifteen minutes; it was rolled back"),
    "42501": ("not_applicable", "This connection may not change this chunk"),
}
_UNCONFIRMED = "The connection was lost while this unit was running; its outcome is unknown"
_VERBS: dict[Maintenance, str] = {
    "drop": "dropped", "move": "moved", "reorder": "reordered", "detach": "detached",
    "merge": "merged", "merge_concurrently": "merged", "split": "split", "attach": "attached",
}

Reviewed = Callable[[PostgresReader], Awaitable[MaintenanceUnit]]
OUTSIDE_A_TRANSACTION: frozenset[Maintenance] = frozenset({"move", "reorder", "merge_concurrently"})


async def _members(
    reader: PostgresReader, unit: MaintenanceUnit, chunks: Sequence[OperationTarget],
) -> dict[tuple[str, str], dict[str, Any]]:
    rows = await reader.query(_MEMBERS, (
        unit.target.schema_name, unit.target.table_name,
        [chunk.schema_name for chunk in chunks], [chunk.name for chunk in chunks],
    ), inspection=True)
    return {(row["schema_name"], row["name"]): row for row in rows}


async def _checked(reader: PostgresReader, reviewed: Reviewed, unit_fingerprint: str) -> MaintenanceUnit:
    try:
        async with asyncio.timeout(5):
            unit = await reviewed(reader)
    except TimeoutError:
        raise ActionRefused("conflict", "The hypertable could not be checked in time; nothing was changed") from None
    except ActionRefused:
        raise ActionRefused(
            "conflict", "The hypertable or its chunks changed after review; nothing was changed",
        ) from None
    except (AdapterError, ValueError):
        raise ActionRefused(
            "not_applicable", "The hypertable could not be checked safely; nothing was changed",
        ) from None
    try:
        unit.require_unchanged(unit_fingerprint)
    except ActionRefused:
        raise ActionRefused(
            "conflict", "The hypertable or its chunks changed after review; nothing was changed",
        ) from None
    return unit


def _routine(unit: MaintenanceUnit) -> sql.Identifier:
    schema = unit.strategy.function_schema
    if schema is None:
        raise RuntimeError("A routine operation was planned without its schema")
    return sql.Identifier(schema, ROUTINES[unit.maintenance].name)


async def run_unit(
    session: PostgresSession, reviewed: Reviewed, unit_fingerprint: str, target: OperationTarget,
) -> UnitOutcome:
    dispatched = False
    try:
        async with session.acquire() as connection:
            async with connection.transaction():
                await connection.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED, READ WRITE")
                await connection.execute("SET LOCAL lock_timeout = '5s'")
                await connection.execute("SET LOCAL statement_timeout = '15min'")
                reader = InspectionReader(connection)
                unit = await _checked(reader, reviewed, unit_fingerprint)
                statement = await _statement(reader, unit, target)
                if statement is None:
                    return "already"
                if unit.maintenance not in OUTSIDE_A_TRANSACTION:
                    dispatched = True
                    await connection.execute(*statement)
                    return "completed"
            dispatched = True
            await _without_transaction(connection, statement)
        return "completed"
    except psycopg.Error as exc:
        raise _failure(exc.sqlstate, dispatched) from None
    except AdapterError:
        if dispatched:
            raise AdapterError("unknown", _UNCONFIRMED) from None
        raise ActionRefused("not_applicable", "The source could not be reached; nothing was changed") from None


async def _without_transaction(
    connection: psycopg.AsyncConnection[Any], statement: tuple[sql.Composed, tuple[object, ...]],
) -> None:
    """Checked in the transaction before, sent with none; the pool gets the session back as it was."""
    await connection.set_autocommit(True)
    try:
        await connection.execute("SET lock_timeout = '5s'")
        await connection.execute("SET statement_timeout = '15min'")
        await connection.execute(*statement)
    finally:
        try:
            await connection.execute("RESET lock_timeout")
            await connection.execute("RESET statement_timeout")
            await connection.set_autocommit(False)
        except psycopg.Error:
            # A connection that cannot be put back as it was is not put back.
            await connection.close()


async def _statement(
    reader: PostgresReader, unit: MaintenanceUnit, target: OperationTarget,
) -> tuple[sql.Composed, tuple[object, ...]] | None:
    """The one statement this unit sends, or None when its chunk is already as requested."""
    arguments = unit.arguments
    if unit.maintenance == "attach":
        table = await reader.query(_TABLE, (target.schema_name, target.name), inspection=True)
        if len(table) != 1:
            raise ActionRefused("not_applicable", "The table to attach is gone; nothing was changed")
        return (
            sql.SQL("CALL {}(%s::pg_catalog.regclass, %s::pg_catalog.regclass, %s::pg_catalog.jsonb)").format(
                _routine(unit),
            ),
            (unit.target.relation_oid, table[0]["relation_oid"], arguments.slices),
        )
    chunks = list(unit.group) if unit.maintenance in MERGES else [target]
    found = await _members(reader, unit, [OperationTarget(schema_name=c.schema_name, name=c.name) for c in chunks])
    rows = [found.get((chunk.schema_name, chunk.name)) for chunk in chunks]
    if any(row is None for row in rows):
        raise ActionRefused("not_applicable", "This chunk is no longer part of the hypertable")
    live = [row for row in rows if row is not None]
    member = live[0]
    oid = member["relation_oid"]
    match unit.maintenance:
        case "drop":
            return sql.SQL("DROP TABLE {}").format(sql.Identifier(target.schema_name, target.name)), ()
        case "move":
            if member["tablespace"] == arguments.tablespace:
                return None
            # move_chunk rewrites the chunk in an index's order and refuses without one.
            index_oid = await _index_oid(reader, unit)
            return (
                sql.SQL(
                    "SELECT {}(%s::pg_catalog.regclass, %s::pg_catalog.name, %s::pg_catalog.name, "
                    "%s::pg_catalog.regclass)"
                ).format(_routine(unit)),
                (oid, arguments.tablespace, arguments.index_tablespace or arguments.tablespace, index_oid),
            )
        case "reorder":
            index_oid = await _index_oid(reader, unit)
            if member["is_compressed"] is True:
                raise ActionRefused("not_applicable", "This chunk was compressed after review; it was left as it is")
            # reorder_chunk takes the hypertable's index and finds the chunk's own.
            return (
                sql.SQL("SELECT {}(%s::pg_catalog.regclass, %s::pg_catalog.regclass)").format(_routine(unit)),
                (oid, index_oid),
            )
        case "detach":
            if member["is_compressed"] is True:
                raise ActionRefused("not_applicable", "This chunk was compressed after review; it was left as it is")
            return sql.SQL("CALL {}(%s::pg_catalog.regclass)").format(_routine(unit)), (oid,)
        case "merge" | "merge_concurrently":
            if [(row["range_start"], row["range_end"]) for row in live] != [
                (chunk.range_start, chunk.range_end) for chunk in unit.group
            ]:
                raise ActionRefused("conflict", "These chunks changed after review; nothing was merged")
            return (
                sql.SQL("CALL {}(%s::pg_catalog.regclass[])").format(_routine(unit)),
                ([row["relation_oid"] for row in live],),
            )
        case "split":
            return (
                sql.SQL("CALL {}(%s::pg_catalog.regclass, %s::{})").format(
                    _routine(unit), column_cast(unit.target),
                ),
                (oid, arguments.split_at),
            )
    raise AssertionError("every operation has a statement")


async def _index_oid(reader: PostgresReader, unit: MaintenanceUnit) -> str:
    index = await reader.query(_INDEX, (unit.target.relation_oid, unit.arguments.index), inspection=True)
    if len(index) != 1:
        raise ActionRefused("not_applicable", "The index to order rows by is gone; nothing was changed")
    return str(index[0]["index_oid"])


def _failure(sqlstate: str | None, dispatched: bool) -> Exception:
    state = sqlstate or ""
    if state in _REFUSED:
        reason, message = _REFUSED[state]
        return ActionRefused(reason, message)
    if not dispatched:
        return ActionRefused("not_applicable", "The source could not be reached or prepared; nothing was changed")
    if not state or state[:2] in {"08", "57", "58"}:
        return AdapterError("unknown", _UNCONFIRMED)
    return ActionRefused("not_applicable", "The source refused this unit; nothing was changed")


async def observe(
    session: PostgresSession, unit: MaintenanceUnit, targets: Sequence[OperationTarget],
    done: Callable[[PostgresReader], Awaitable[bool]] | None = None,
) -> list[ObservedState]:
    """What each target is now, read back after an interrupted job.

    A merge or a split changes its chunk's range rather than where it is, and
    the range it was reviewed with cannot be read back once it changed, so
    those say themselves, through `done`, whether what was asked now holds.
    """
    async with session.inspection() as reader:
        found = await _members(reader, unit, targets)
        tables = [
            bool(await reader.query(_TABLE, (target.schema_name, target.name), inspection=True))
            for target in targets
        ]
        finished = await done(reader) if done is not None else False
    states: list[ObservedState] = []
    for target, exists in zip(targets, tables, strict=True):
        member = found.get((target.schema_name, target.name))
        if done is not None:
            states.append("gone" if member is None else "as_requested" if finished else "unchanged")
        else:
            states.append(_observed(unit, member, exists))
    return states


def _observed(unit: MaintenanceUnit, member: dict[str, Any] | None, exists: bool) -> ObservedState:
    match unit.maintenance:
        case "drop":
            return "as_requested" if not exists else "unchanged"
        case "detach":
            if not exists:
                return "gone"
            return "as_requested" if member is None else "unchanged"
        case "attach":
            if not exists:
                return "gone"
            return "as_requested" if member is not None else "unchanged"
    if member is None:
        return "gone"
    if unit.maintenance == "move":
        return "as_requested" if member["tablespace"] == unit.arguments.tablespace else "unchanged"
    # A reorder leaves nothing a public view can tell apart; running it again is harmless.
    return "unchanged"


def verb(maintenance: Maintenance) -> str:
    return _VERBS[maintenance]
