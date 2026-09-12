"""Inspect a time hypertable's retention or compression policy without invoking its API."""

import asyncio
from dataclasses import dataclass

from psycopg import sql
from pydantic import ValidationError

from app.adapters.actions import ActionRefused
from app.adapters.postgres.inspection import PostgresReader
from app.adapters.postgres.timescale.api import (
    RoutineShape,
    extension_routine,
    lockable_view,
)
from app.adapters.postgres.timescale.plans import (
    AgePolicy,
    AgePolicyKind,
    AgePolicyPlan,
    AgePolicyStrategy,
    TimeDuration,
    TimeHypertable,
)
from app.adapters.postgres.timescale.policy_projection import (
    OWNED_POLICY_ROUTINE,
    validated_interval,
)
from app.adapters.postgres.timescale.profile import discover, require_available
from app.adapters.postgres.timescale.report_access import require_public_view
from app.adapters.postgres.timescale.targets import time_hypertable
from app.adapters.protocol import AdapterError


@dataclass(frozen=True)
class AgePolicySpec:
    kind: AgePolicyKind
    noun: str
    routine: str
    older_than_key: str
    created_before_key: str
    add: RoutineShape
    remove: RoutineShape
    requires_compression: bool = False


# sql/policy_api.sql. Both routines are called with the relation, the threshold
# and if_not_exists; what a release appends after those is left at its default.
# regclass 2205, "any" 2276, boolean 16; results integer 23, void 2278.
_ADD_ARGUMENTS = "2205 2276 16"

RETENTION = AgePolicySpec(
    kind="retention", noun="retention policy", routine="policy_retention",
    older_than_key="drop_after", created_before_key="drop_created_before",
    add=RoutineShape("add_retention_policy", "f", _ADD_ARGUMENTS, 23),
    remove=RoutineShape("remove_retention_policy", "f", "2205 16", 2278),
)
COMPRESSION = AgePolicySpec(
    kind="compression", noun="compression policy", routine="policy_compression",
    older_than_key="compress_after", created_before_key="compress_created_before",
    add=RoutineShape("add_compression_policy", "f", _ADD_ARGUMENTS, 23),
    remove=RoutineShape("remove_compression_policy", "f", "2205 16", 16),
    requires_compression=True,
)

JOBS_COLUMNS = (
    "job_id", "hypertable_schema", "hypertable_name", "proc_schema", "proc_name",
    "scheduled", "schedule_interval", "config",
)
_SUBDAY = frozenset({"second", "minute", "hour"})

_COMPRESSION_ENABLED = """
SELECT compression_enabled FROM timescaledb_information.hypertables
WHERE hypertable_schema = %s AND hypertable_name = %s
"""


def _existing_statement(spec: AgePolicySpec) -> str:
    return sql.SQL("""
SELECT source.job_id::text AS job_id, source.scheduled,
       source.schedule_interval::text AS schedule_interval,
       {older_than} AS older_than, {created_before} AS created_before
FROM timescaledb_information.jobs AS source
WHERE source.hypertable_schema = %s AND source.hypertable_name = %s
  AND source.proc_name = {routine} AND {owned}
ORDER BY source.job_id
LIMIT 2
""").format(
        older_than=validated_interval(spec.older_than_key),
        created_before=validated_interval(spec.created_before_key),
        routine=sql.Literal(spec.routine),
        owned=OWNED_POLICY_ROUTINE,
    ).as_string()


_EXISTING = {spec.kind: _existing_statement(spec) for spec in (RETENTION, COMPRESSION)}


@dataclass(frozen=True)
class AgePolicyState:
    target: TimeHypertable
    existing: AgePolicy | None
    strategy: AgePolicyStrategy


async def read_age_policy(
    reader: PostgresReader, spec: AgePolicySpec, schema_name: str, table_name: str,
) -> AgePolicy | None:
    """The one extension-owned job of this kind; the caller has checked the jobs view."""
    policies = await reader.query(_EXISTING[spec.kind], (schema_name, table_name), inspection=True)
    if len(policies) > 1:
        raise ActionRefused(
            "not_applicable", f"This hypertable has several {spec.noun} jobs; manage them with SQL",
        )
    try:
        return AgePolicy.model_validate(policies[0]) if policies else None
    except ValidationError:
        raise ActionRefused(
            "not_applicable", f"The existing {spec.noun} could not be read safely; manage it with SQL",
        ) from None


async def inspect_age_policy(
    reader: PostgresReader, spec: AgePolicySpec, schema_name: str, table_name: str,
) -> AgePolicyState:
    try:
        async with asyncio.timeout(5):
            version = require_available(await discover(reader))
            target = await time_hypertable(reader, schema_name, table_name)
            if spec.requires_compression:
                await require_compression(reader, target)
            await require_public_view(reader, "jobs", JOBS_COLUMNS)
            existing = await read_age_policy(reader, spec, target.schema_name, target.table_name)
            add = await extension_routine(reader, version, spec.add)
            remove = await extension_routine(reader, version, spec.remove)
            strategy = AgePolicyStrategy.model_validate({
                "kind": spec.kind,
                "extension_version": version,
                "function_schema": add.schema_name,
                "add_function_oid": add.oid,
                "remove_function_oid": remove.oid,
                "jobs_view_oid": await lockable_view(reader, version, "jobs"),
            })
            return AgePolicyState(target=target, existing=existing, strategy=strategy)
    except TimeoutError:
        raise ActionRefused("not_applicable", f"TimescaleDB {spec.noun} planning timed out") from None
    except (AdapterError, ValueError):
        raise ActionRefused(
            "not_applicable", f"TimescaleDB {spec.noun} metadata could not be inspected safely",
        ) from None


async def require_compression(reader: PostgresReader, target: TimeHypertable) -> None:
    await require_public_view(
        reader, "hypertables", ("hypertable_schema", "hypertable_name", "compression_enabled"),
    )
    rows = await reader.query(
        _COMPRESSION_ENABLED, (target.schema_name, target.table_name), inspection=True,
    )
    if len(rows) != 1 or rows[0].get("compression_enabled") is not True:
        raise ActionRefused("not_applicable", "Enable compression on this hypertable first")


def age_policy_plan(
    spec: AgePolicySpec, state: AgePolicyState, older_than: TimeDuration | None,
) -> AgePolicyPlan:
    """Setting when a threshold is given, removing otherwise; replacement is explicit in the plan."""
    if older_than is None:
        if state.existing is None:
            raise ActionRefused("not_applicable", f"This hypertable has no {spec.noun}")
        return AgePolicyPlan(
            operation="remove_policy", kind=spec.kind, target=state.target,
            existing=state.existing, older_than=None, strategy=state.strategy,
        )
    if state.target.column_type == "date" and older_than.unit in _SUBDAY:
        raise ActionRefused("not_applicable", "Date dimensions require whole days, weeks, months or years")
    # A replacement is scheduled by default, so replacing a paused policy would resume it.
    if state.existing is not None and not state.existing.scheduled:
        raise ActionRefused(
            "not_applicable", f"The existing {spec.noun} is paused; remove it before setting a new one",
        )
    return AgePolicyPlan(
        operation="set_policy", kind=spec.kind, target=state.target,
        existing=state.existing, older_than=older_than, strategy=state.strategy,
    )


async def plan_age_policy(
    reader: PostgresReader, spec: AgePolicySpec, schema_name: str, table_name: str,
    older_than: TimeDuration | None,
) -> AgePolicyPlan:
    return age_policy_plan(spec, await inspect_age_policy(reader, spec, schema_name, table_name), older_than)
