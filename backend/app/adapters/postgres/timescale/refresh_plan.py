"""Inspect a continuous aggregate's refresh policy without invoking its API."""

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any

from psycopg import sql
from pydantic import ValidationError

from app.adapters.actions import ActionRefused
from app.adapters.postgres.inspection import PostgresReader
from app.adapters.postgres.timescale.age_policy_plan import (
    JOBS_COLUMNS,
    RETENTION,
    TESTED_VERSIONS,
    read_age_policy,
)
from app.adapters.postgres.timescale.api import (
    RoutineShape,
    extension_routine,
    lockable_view,
    require_tested_server,
)
from app.adapters.postgres.timescale.plans import (
    AgePolicy,
    ContinuousAggregateTarget,
    RefreshPlan,
    RefreshPolicy,
    RefreshStrategy,
    RefreshWindow,
)
from app.adapters.postgres.timescale.policy_projection import (
    OWNED_POLICY_ROUTINE,
    validated_interval,
)
from app.adapters.postgres.timescale.profile import discover
from app.adapters.postgres.timescale.report_access import require_public_view
from app.adapters.postgres.timescale.targets import continuous_aggregate
from app.adapters.protocol import AdapterError

# sql/policy_api.sql: regclass, "any", "any", interval, boolean, timestamptz, text returning
# integer; 2.18.0 appends include_tiered_data boolean DEFAULT NULL, left unset. Removal takes
# regclass, if_not_exists and if_exists booleans and returns void in both.
_ADD_ARGUMENTS = "2205 2276 2276 1186 16 1184 25"
ADD_REFRESH = {
    "2.17.2": RoutineShape("add_continuous_aggregate_policy", "f", _ADD_ARGUMENTS, 23, 3),
    "2.18.0": RoutineShape("add_continuous_aggregate_policy", "f", f"{_ADD_ARGUMENTS} 16", 23, 4),
}
REMOVE_REFRESH = dict.fromkeys(
    TESTED_VERSIONS, RoutineShape("remove_continuous_aggregate_policy", "f", "2205 16 16", 2278, 2),
)

_SUBDAY = frozenset({"second", "minute", "hour"})

_EXISTING = sql.SQL("""
SELECT source.job_id::text AS job_id, source.scheduled,
       source.schedule_interval::text AS schedule_interval,
       {start} AS start_offset,
       pg_catalog.jsonb_typeof(source.config -> 'start_offset') AS start_offset_type,
       {end} AS end_offset,
       pg_catalog.jsonb_typeof(source.config -> 'end_offset') AS end_offset_type
FROM timescaledb_information.jobs AS source
WHERE source.hypertable_schema = %s AND source.hypertable_name = %s
  AND source.proc_name = 'policy_refresh_continuous_aggregate' AND {owned}
ORDER BY source.job_id
LIMIT 2
""").format(
    start=validated_interval("start_offset"),
    end=validated_interval("end_offset"),
    owned=OWNED_POLICY_ROUTINE,
).as_string()

_LESS = "SELECT %s::pg_catalog.interval < %s::pg_catalog.interval AS less"


@dataclass(frozen=True)
class RefreshState:
    target: ContinuousAggregateTarget
    existing: RefreshPolicy | None
    source_retention: AgePolicy | None
    strategy: RefreshStrategy


async def inspect_refresh(reader: PostgresReader, schema_name: str, view_name: str) -> RefreshState:
    return await _guarded(_inspect(reader, schema_name, view_name))


async def plan_refresh(
    reader: PostgresReader, schema_name: str, view_name: str, window: RefreshWindow | None,
) -> RefreshPlan:
    async def plan() -> RefreshPlan:
        return await _build(reader, await _inspect(reader, schema_name, view_name), window)

    return await _guarded(plan())


def setting_refusal(state: RefreshState) -> str | None:
    """What refuses any new window before one is chosen."""
    # A replacement is scheduled, so replacing a paused policy would resume it.
    if state.existing is not None and not state.existing.scheduled:
        return "The existing refresh policy is paused; remove it before setting a new one"
    return None


async def _guarded[T](work: Awaitable[T]) -> T:
    try:
        async with asyncio.timeout(5):
            return await work
    except TimeoutError:
        raise ActionRefused("not_applicable", "TimescaleDB refresh policy planning timed out") from None
    except (AdapterError, ValueError):
        raise ActionRefused(
            "not_applicable", "TimescaleDB refresh policy metadata could not be inspected safely",
        ) from None


async def _inspect(reader: PostgresReader, schema_name: str, view_name: str) -> RefreshState:
    profile = await discover(reader)
    version = profile.feature.installed_version
    if not profile.available or version is None or version not in TESTED_VERSIONS:
        raise ActionRefused("not_applicable", "No supported TimescaleDB refresh policy API")
    await require_tested_server(reader)
    target = await continuous_aggregate(reader, schema_name, view_name)
    await require_public_view(reader, "jobs", JOBS_COLUMNS)
    existing = await _read_refresh(reader, target)
    source_retention = await read_age_policy(reader, RETENTION, target.source_schema, target.source_name)
    add = await extension_routine(reader, version, ADD_REFRESH[version])
    remove = await extension_routine(reader, version, REMOVE_REFRESH[version])
    strategy = RefreshStrategy.model_validate({
        "extension_version": version,
        "function_schema": add.schema_name,
        "add_function_oid": add.oid,
        "remove_function_oid": remove.oid,
        "jobs_view_oid": await lockable_view(reader, version, "jobs"),
    })
    return RefreshState(target=target, existing=existing, source_retention=source_retention, strategy=strategy)


async def _read_refresh(reader: PostgresReader, target: ContinuousAggregateTarget) -> RefreshPolicy | None:
    # The job belongs to the materialization hypertable, not to the view.
    rows = await reader.query(
        _EXISTING, (target.materialization_schema, target.materialization_name), inspection=True,
    )
    if len(rows) > 1:
        raise ActionRefused(
            "not_applicable", "This continuous aggregate has several refresh policy jobs; manage them with SQL",
        )
    if not rows:
        return None
    try:
        return RefreshPolicy.model_validate(_readable_offsets(rows[0]))
    except (ValidationError, ValueError):
        raise ActionRefused(
            "not_applicable", "The existing refresh policy could not be read safely; manage it with SQL",
        ) from None


def _readable_offsets(row: dict[str, Any]) -> dict[str, Any]:
    """Absent or JSON null is an unbounded edge; any other unreadable value refuses."""
    policy = {key: value for key, value in row.items() if not key.endswith("_type")}
    for edge in ("start_offset", "end_offset"):
        kind = row.get(f"{edge}_type")
        if kind in {None, "null"} and policy.get(edge) is None:
            continue
        if kind != "string" or policy.get(edge) is None:
            raise ValueError(f"Unreadable {edge}")
    return policy


async def _build(reader: PostgresReader, state: RefreshState, window: RefreshWindow | None) -> RefreshPlan:
    if window is None:
        if state.existing is None:
            raise ActionRefused("not_applicable", "This continuous aggregate has no refresh policy")
        return RefreshPlan(
            operation="remove_policy", target=state.target, existing=state.existing, window=None,
            source_retention=state.source_retention, strategy=state.strategy,
        )
    if state.target.column_type == "date" and {
        window.start_offset.unit, window.end_offset.unit,
    } & _SUBDAY:
        raise ActionRefused("not_applicable", "Date dimensions require offsets in whole days, weeks, months or years")
    refusal = setting_refusal(state)
    if refusal is not None:
        raise ActionRefused("not_applicable", refusal)
    # PostgreSQL compares the intervals, months counted as thirty days, so no rule is restated here.
    if not await _less(reader, window.end_offset.interval_value(), window.start_offset.interval_value()):
        raise ActionRefused("not_applicable", "The window must start further back than it ends")
    retention = state.source_retention
    if retention is not None and retention.older_than is not None and not await _less(
        reader, window.start_offset.interval_value(), retention.older_than,
    ):
        raise ActionRefused(
            "not_applicable",
            f"The window reaches data the source's retention policy drops (older than {retention.older_than}); "
            "refreshing there would remove aggregated rows",
        )
    return RefreshPlan(
        operation="set_policy", target=state.target, existing=state.existing, window=window,
        source_retention=state.source_retention, strategy=state.strategy,
    )


async def _less(reader: PostgresReader, lower: str, upper: str) -> bool:
    rows = await reader.query(_LESS, (lower, upper), inspection=True)
    return len(rows) == 1 and rows[0].get("less") is True
