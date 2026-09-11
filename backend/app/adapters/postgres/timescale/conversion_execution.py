"""Empty-table conversion: exclusive lock first, emptiness replanned under it (D123)."""

from typing import Any

import psycopg
from psycopg import sql

from app.adapters.postgres.inspection import PostgresReader
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.conversion_plan import plan_conversion
from app.adapters.postgres.timescale.execution import run_reviewed
from app.adapters.postgres.timescale.plans import ConversionPlan, TimeDuration


async def execute_conversion(
    session: PostgresSession, schema_name: str, table_name: str,
    column_name: str, interval: TimeDuration, reviewed_fingerprint: str,
) -> ConversionPlan:
    async def replan(reader: PostgresReader) -> ConversionPlan:
        return await plan_conversion(reader, schema_name, table_name, column_name, interval)

    return await run_reviewed(session, replan, _locks, _apply, reviewed_fingerprint, "hypertable conversion")


def _locks(plan: ConversionPlan) -> list[sql.SQL | sql.Composed]:
    # The lock create_hypertable takes; held first, no row can arrive after the emptiness replan.
    return [sql.SQL("LOCK TABLE ONLY {} IN ACCESS EXCLUSIVE MODE").format(
        sql.Identifier(plan.target.schema_name, plan.target.table_name),
    )]


async def _apply(connection: psycopg.AsyncConnection[Any], plan: ConversionPlan) -> None:
    schema = plan.strategy.function_schema
    # Default indexes on, if_not_exists and migrate_data off: the source refuses rows too.
    await connection.execute(
        sql.SQL(
            "SELECT hypertable_id FROM {}(%s::pg_catalog.regclass, "
            "{}(%s::pg_catalog.name, %s::pg_catalog.interval), true, false, false)"
        ).format(sql.Identifier(schema, "create_hypertable"), sql.Identifier(schema, "by_range")),
        (plan.target.relation_oid, plan.column.name, plan.interval.interval_value()),
    )
