"""Refresh policy strategy: one transaction under the public jobs metadata lock (D123)."""

from typing import Any

import psycopg
from psycopg import sql

from app.adapters.postgres.inspection import PostgresReader
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.age_policy_execution import JOBS_LOCK
from app.adapters.postgres.timescale.execution import run_reviewed
from app.adapters.postgres.timescale.plans import RefreshPlan, RefreshWindow
from app.adapters.postgres.timescale.refresh_plan import (
    ADD_REFRESH,
    REMOVE_REFRESH,
    plan_refresh,
)


async def execute_refresh(
    session: PostgresSession, schema_name: str, view_name: str,
    window: RefreshWindow | None, reviewed_fingerprint: str,
) -> RefreshPlan:
    async def replan(reader: PostgresReader) -> RefreshPlan:
        return await plan_refresh(reader, schema_name, view_name, window)

    return await run_reviewed(session, replan, _locks, _apply, reviewed_fingerprint, "refresh policy change")


def _locks(plan: RefreshPlan) -> list[sql.SQL | sql.Composed]:
    return [
        JOBS_LOCK,
        sql.SQL("LOCK TABLE ONLY {} IN SHARE UPDATE EXCLUSIVE MODE").format(
            sql.Identifier(plan.target.materialization_schema, plan.target.materialization_name),
        ),
    ]


async def _apply(connection: psycopg.AsyncConnection[Any], plan: RefreshPlan) -> None:
    version = plan.strategy.extension_version
    schema = plan.strategy.function_schema
    # Removal and addition share the transaction: a refused addition keeps the old policy.
    if plan.existing is not None:
        await connection.execute(
            sql.SQL("SELECT {}(%s::pg_catalog.regclass, false, false)").format(
                sql.Identifier(schema, REMOVE_REFRESH[version].name),
            ),
            (plan.target.view_oid,),
        )
    if plan.window is not None:
        await connection.execute(
            sql.SQL(
                "SELECT {}(%s::pg_catalog.regclass, %s::pg_catalog.interval, "
                "%s::pg_catalog.interval, %s::pg_catalog.interval, false)"
            ).format(sql.Identifier(schema, ADD_REFRESH[version].name)),
            (
                plan.target.view_oid, plan.window.start_offset.interval_value(),
                plan.window.end_offset.interval_value(), plan.window.schedule_interval.interval_value(),
            ),
        )
