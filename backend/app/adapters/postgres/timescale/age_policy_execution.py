"""Age policy strategy: one transaction under the public jobs metadata lock (D123)."""

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
from app.adapters.postgres.timescale.plans import AgePolicyPlan, TimeDuration

# Locking a view locks the relations it reads, so the catalogs the policy API writes
# are serialized without naming a private relation.
JOBS_LOCK = sql.SQL('LOCK TABLE ONLY "timescaledb_information"."jobs" IN SHARE ROW EXCLUSIVE MODE')


async def execute_age_policy(
    session: PostgresSession, spec: AgePolicySpec, schema_name: str, table_name: str,
    older_than: TimeDuration | None, reviewed_fingerprint: str,
) -> AgePolicyPlan:
    async def replan(reader: PostgresReader) -> AgePolicyPlan:
        return await plan_age_policy(reader, spec, schema_name, table_name, older_than)

    async def apply(connection: psycopg.AsyncConnection[Any], plan: AgePolicyPlan) -> None:
        version = plan.strategy.extension_version
        # Removal and addition share the transaction: a refused addition keeps the old policy.
        if plan.existing is not None:
            await connection.execute(
                sql.SQL("SELECT {}(%s::pg_catalog.regclass, false)").format(
                    sql.Identifier(plan.strategy.function_schema, spec.remove[version].name),
                ),
                (plan.target.relation_oid,),
            )
        if plan.older_than is not None:
            await connection.execute(
                sql.SQL("SELECT {}(%s::pg_catalog.regclass, %s::pg_catalog.interval, false)").format(
                    sql.Identifier(plan.strategy.function_schema, spec.add[version].name),
                ),
                (plan.target.relation_oid, plan.older_than.interval_value()),
            )

    return await run_reviewed(session, replan, _locks, apply, reviewed_fingerprint, f"{spec.noun} change")


def _locks(plan: AgePolicyPlan) -> list[sql.SQL | sql.Composed]:
    return [
        JOBS_LOCK,
        sql.SQL("LOCK TABLE ONLY {} IN SHARE UPDATE EXCLUSIVE MODE").format(
            sql.Identifier(plan.target.schema_name, plan.target.table_name),
        ),
    ]
