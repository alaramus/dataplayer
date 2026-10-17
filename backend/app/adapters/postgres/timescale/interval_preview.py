"""Render the interval plan through the shared reviewed-action preview transport."""

from psycopg import sql

from app.adapters.actions import ActionPreview, ActionRefused
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.interval_plan import plan_chunk_interval
from app.adapters.postgres.timescale.plans import TimeDuration
from app.adapters.protocol import AdapterError
from app.core.translation import say


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
            summary=say("TimescaleDB interval metadata could not be inspected safely"), blocked=True,
        )

    target = sql.Identifier(plan.target.schema_name, plan.target.table_name).as_string()
    column = sql.Identifier(plan.target.column_name).as_string()
    return ActionPreview(
        summary=say("Change the future chunk interval for {target}", target=target),
        items=[
            say("Time dimension: {column}", column=column),
            say("Current interval: {interval}", interval=plan.target.current_interval),
            say("Requested interval: {interval}", interval=plan.interval.label()),
            plan.said_impact,
            plan.said_coordination,
        ],
        fingerprint=plan.fingerprint(),
    )
