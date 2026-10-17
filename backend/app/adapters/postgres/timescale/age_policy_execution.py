"""Age policy strategy: one transaction behind DataPlayer's job guard (D123, D211)."""

from typing import Any

import psycopg
from psycopg import sql

from app.adapters.postgres.inspection import PostgresReader
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.age_policy_plan import (
    AgePolicySpec,
    plan_age_policy,
)
from app.adapters.postgres.timescale.execution import run_reviewed
from app.adapters.postgres.timescale.job_locks import JOBS_GUARD
from app.adapters.postgres.timescale.plans import AgePolicyPlan, TimeDuration


async def execute_age_policy(
    session: PostgresSession, spec: AgePolicySpec, schema_name: str, table_name: str,
    older_than: TimeDuration | None, reviewed_fingerprint: str,
) -> AgePolicyPlan:
    async def replan(reader: PostgresReader) -> AgePolicyPlan:
        return await plan_age_policy(reader, spec, schema_name, table_name, older_than)

    async def apply(connection: psycopg.AsyncConnection[Any], plan: AgePolicyPlan) -> None:
        # Removal and addition share the transaction: a refused addition keeps the old policy.
        if plan.existing is not None:
            await connection.execute(
                sql.SQL("SELECT {}(%s::pg_catalog.regclass, false)").format(
                    sql.Identifier(plan.strategy.function_schema, spec.remove.name),
                ),
                (plan.target.relation_oid,),
            )
        if plan.older_than is not None:
            await connection.execute(
                sql.SQL("SELECT {}(%s::pg_catalog.regclass, %s::pg_catalog.interval, false)").format(
                    sql.Identifier(plan.strategy.function_schema, spec.add.name),
                ),
                (plan.target.relation_oid, plan.older_than.interval_value()),
            )

    return await run_reviewed(session, replan, _locks, apply, reviewed_fingerprint)


def _locks(plan: AgePolicyPlan) -> list[sql.SQL | sql.Composed]:
    return [
        JOBS_GUARD,
        sql.SQL("LOCK TABLE ONLY {} IN SHARE UPDATE EXCLUSIVE MODE").format(
            sql.Identifier(plan.target.schema_name, plan.target.table_name),
        ),
    ]
