"""Interval strategy validated on the pinned PostgreSQL 16 sources (D123)."""

import asyncio

import psycopg
from psycopg import sql

from app.adapters.actions import ActionRefused
from app.adapters.postgres.inspection import InspectionReader
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.interval_plan import plan_chunk_interval
from app.adapters.postgres.timescale.plans import ChunkIntervalPlan, TimeDuration
from app.adapters.protocol import AdapterError

_METADATA_LOCK = (
    'LOCK TABLE ONLY "timescaledb_information"."dimensions" IN SHARE ROW EXCLUSIVE MODE'
)
_UNCONFIRMED = "The interval change could not be confirmed; reload the source before reviewing again"


async def execute_chunk_interval(
    session: PostgresSession, schema_name: str, table_name: str,
    interval: TimeDuration, reviewed_fingerprint: str,
) -> ChunkIntervalPlan:
    mutation_started = False
    try:
        async with asyncio.timeout(5):
            async with session.acquire() as connection:
                async with connection.transaction():
                    await connection.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED, READ WRITE")
                    await connection.execute("SET LOCAL lock_timeout = '2s'")
                    await connection.execute("SET LOCAL statement_timeout = '5s'")
                    reader = InspectionReader(connection)
                    preliminary = await plan_chunk_interval(reader, schema_name, table_name, interval)
                    preliminary.require_unchanged(reviewed_fingerprint)

                    # The native setter writes dimension metadata without a root-table lock (D123).
                    await connection.execute(_METADATA_LOCK)
                    await connection.execute(sql.SQL(
                        "LOCK TABLE ONLY {} IN SHARE UPDATE EXCLUSIVE MODE"
                    ).format(sql.Identifier(
                        preliminary.target.schema_name, preliminary.target.table_name,
                    )))
                    current = await plan_chunk_interval(reader, schema_name, table_name, interval)
                    current.require_unchanged(reviewed_fingerprint)
                    statement = sql.SQL(
                        "SELECT {}(%s::pg_catalog.regclass, %s::pg_catalog.interval, %s::pg_catalog.name)"
                    ).format(sql.Identifier(current.strategy.function_schema, "set_chunk_time_interval"))
                    mutation_started = True
                    await connection.execute(statement, (
                        current.target.relation_oid, current.interval.interval_value(), current.target.column_name,
                    ))
        return current
    except TimeoutError:
        if mutation_started:
            raise AdapterError("unknown", _UNCONFIRMED) from None
        raise ActionRefused("conflict", "Interval validation timed out; review the plan again") from None
    except psycopg.Error as exc:
        if exc.sqlstate in {"55P03", "40P01", "40001", "42P01", "42704"}:
            raise ActionRefused("conflict", "The source changed or is busy; review the plan again") from None
        if exc.sqlstate == "42501":
            raise ActionRefused("not_applicable", "This connection may not change the interval or lock its metadata") from None
        if exc.sqlstate and exc.sqlstate[:2] not in {"08", "57", "58"}:
            raise ActionRefused("not_applicable", "The source refused the interval change") from None
        raise AdapterError("unknown", _UNCONFIRMED) from None
