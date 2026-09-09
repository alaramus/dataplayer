"""Render the interval plan through the shared reviewed-action preview transport."""

from psycopg import sql

from app.adapters.actions import ActionPreview, ActionRefused
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.interval_plan import plan_chunk_interval
from app.adapters.postgres.timescale.plans import TimeDuration
from app.adapters.protocol import AdapterError


async def preview_chunk_interval(
    session: PostgresSession, schema_name: str, table_name: str, interval: TimeDuration,
) -> ActionPreview:
    try:
        async with session.inspection() as reader:
            plan = await plan_chunk_interval(reader, schema_name, table_name, interval)
    except ActionRefused as exc:
        return ActionPreview(summary=exc.message, blocked=True)
    except (AdapterError, ValueError, TimeoutError):
        return ActionPreview(
            summary="TimescaleDB interval metadata could not be inspected safely", blocked=True,
        )

    target = sql.Identifier(plan.target.schema_name, plan.target.table_name).as_string()
    column = sql.Identifier(plan.target.column_name).as_string()
    return ActionPreview(
        summary=f"Change the future chunk interval for {target}",
        items=[
            f"Time dimension: {column}",
            f"Current interval: {plan.target.current_interval}",
            f"Requested interval: {plan.interval.interval_value()}",
            plan.impact,
            plan.coordination,
        ],
        fingerprint=plan.fingerprint(),
    )
