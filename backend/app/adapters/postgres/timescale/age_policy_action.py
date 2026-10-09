"""Reviewed retention and compression policy actions on one time hypertable."""

from collections.abc import Mapping
from typing import Any, ClassVar, Literal

from psycopg import sql
from pydantic import BaseModel, ConfigDict, Field

from app.adapters.actions import (
    Action,
    ActionPreview,
    ActionRefused,
    ActionResult,
    ActsOn,
)
from app.adapters.catalog import NodeKind
from app.adapters.features import FeatureCode
from app.adapters.layout import layout
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.age_policy_execution import execute_age_policy
from app.adapters.postgres.timescale.age_policy_plan import (
    COMPRESSION,
    RETENTION,
    AgePolicySpec,
    AgePolicyState,
    age_policy_plan,
    inspect_age_policy,
    plan_age_policy,
)
from app.adapters.postgres.timescale.names import TIMESCALE_MENU
from app.adapters.postgres.timescale.plans import (
    AgePolicyKind,
    AgePolicyPlan,
    TimeDuration,
)
from app.adapters.postgres.timescale.reports import TIMESCALE_SECTION_ID
from app.adapters.postgres.timescale.targets import user_table
from app.adapters.protocol import AdapterError
from app.core.access import Access

# What the job does to a chunk, as a present-tense verb and as an imperative.
_VERBS: dict[AgePolicyKind, tuple[str, str]] = {
    "retention": ("drops", "drop"),
    "compression": ("compresses", "compress"),
}


class ThresholdParams(TimeDuration):
    unit: Literal["hour", "day", "week", "month", "year"] = Field(
        title="Unit", json_schema_extra=layout(row="threshold"),
    )

    def duration(self) -> TimeDuration:
        return TimeDuration(amount=self.amount, unit=self.unit)


class RetentionParams(ThresholdParams):
    amount: int = Field(
        strict=True, gt=0, le=2_147_483_647, title="Drop chunks older than",
        json_schema_extra=layout(row="threshold"),
    )


class CompressionParams(ThresholdParams):
    amount: int = Field(
        strict=True, gt=0, le=2_147_483_647, title="Compress chunks older than",
        json_schema_extra=layout(row="threshold"),
    )


class NoParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _unreadable(spec: AgePolicySpec) -> str:
    return f"TimescaleDB {spec.noun} metadata could not be inspected safely"


async def preview_age_policy(
    session: PostgresSession, spec: AgePolicySpec, schema_name: str, table_name: str,
    older_than: TimeDuration | None,
) -> ActionPreview:
    try:
        async with session.inspection() as reader:
            plan = await plan_age_policy(reader, spec, schema_name, table_name, older_than)
    except ActionRefused as exc:
        return ActionPreview(summary=exc.message, blocked=True)
    except (AdapterError, ValueError, TimeoutError):
        return ActionPreview(summary=_unreadable(spec), blocked=True)
    target = sql.Identifier(plan.target.schema_name, plan.target.table_name).as_string()
    summary = (
        f"Set the {spec.noun} for {target}" if plan.older_than is not None
        else f"Remove the {spec.noun} from {target}"
    )
    return ActionPreview(summary=summary, items=_items(spec, plan), fingerprint=plan.fingerprint())


def _items(spec: AgePolicySpec, plan: AgePolicyPlan) -> list[str]:
    present, imperative = _VERBS[plan.kind]
    items = [f"Time dimension: {sql.Identifier(plan.target.column_name).as_string()}"]
    if plan.existing is None:
        items.append(f"No {spec.noun} exists yet")
    else:
        verb = "Removes" if plan.older_than is None else "Replaces"
        items.append(f"{verb} job {plan.existing.job_id}, which {present} chunks {plan.existing.threshold()}")
        if plan.older_than is not None:
            items.append(
                f"The current policy runs every {plan.existing.schedule_interval}; "
                "its replacement uses TimescaleDB's default schedule"
            )
    if plan.older_than is not None:
        items.append(f"New policy: {imperative} chunks older than {plan.older_than.interval_value()}")
    items.extend((plan.impact, plan.coordination))
    return items


async def age_policy_admission(
    session: PostgresSession, spec: AgePolicySpec, schema_name: str, table_name: str,
) -> tuple[str | None, str | None]:
    """Why setting, then removing, a policy cannot be offered, from one snapshot."""
    try:
        async with session.inspection() as reader:
            state = await inspect_age_policy(reader, spec, schema_name, table_name)
    except ActionRefused as exc:
        return exc.message, exc.message
    except (AdapterError, ValueError, TimeoutError):
        return _unreadable(spec), _unreadable(spec)
    # One day admits date and timestamp dimensions without choosing the user's threshold.
    return _refusal(spec, state, TimeDuration(amount=1, unit="day")), _refusal(spec, state, None)


def _refusal(spec: AgePolicySpec, state: AgePolicyState, older_than: TimeDuration | None) -> str | None:
    try:
        age_policy_plan(spec, state, older_than)
    except ActionRefused as exc:
        return exc.message
    return None


class SetAgePolicy[P: ThresholdParams](Action[P]):
    spec: ClassVar[AgePolicySpec]
    # The result message, formatted with the requested threshold.
    done: ClassVar[str]
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "structure"
    feature_requirements: ClassVar[tuple[FeatureCode, ...]] = ("timescaledb",)
    menu_group: ClassVar[str | None] = TIMESCALE_MENU

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        params = self._validated(raw)
        schema, node = await user_table(self._catalog, node_id)
        return await preview_age_policy(self._session, self.spec, schema.name, node.name, params.duration())

    async def perform(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionResult:
        raise ActionRefused("conflict", f"Review the {self.spec.noun} plan before applying it")

    async def perform_reviewed(
        self, node_id: str | None, raw: Mapping[str, Any], fingerprint: str,
    ) -> ActionResult:
        params = self._validated(raw)
        schema, node = await user_table(self._catalog, node_id)
        await execute_age_policy(
            self._session, self.spec, schema.name, node.name, params.duration(), fingerprint,
        )
        return ActionResult(
            message=self.done.format(params.interval_value()),
            reload_node_ids=[schema.id, node.id, TIMESCALE_SECTION_ID],
        )


class RemoveAgePolicy(Action[NoParams]):
    spec: ClassVar[AgePolicySpec]
    done: ClassVar[str]
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "structure"
    feature_requirements: ClassVar[tuple[FeatureCode, ...]] = ("timescaledb",)
    menu_group: ClassVar[str | None] = TIMESCALE_MENU
    params_model = NoParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        self._validated(raw)
        schema, node = await user_table(self._catalog, node_id)
        return await preview_age_policy(self._session, self.spec, schema.name, node.name, None)

    async def perform(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionResult:
        raise ActionRefused("conflict", f"Review the {self.spec.noun} plan before applying it")

    async def perform_reviewed(
        self, node_id: str | None, raw: Mapping[str, Any], fingerprint: str,
    ) -> ActionResult:
        self._validated(raw)
        schema, node = await user_table(self._catalog, node_id)
        await execute_age_policy(self._session, self.spec, schema.name, node.name, None, fingerprint)
        return ActionResult(message=self.done, reload_node_ids=[schema.id, node.id, TIMESCALE_SECTION_ID])


class SetRetentionPolicy(SetAgePolicy[RetentionParams]):
    name: ClassVar[str] = "timescale_set_retention_policy"
    title: ClassVar[str] = "Set retention policy"
    destructive: ClassVar[bool] = True
    question: ClassVar[str | None] = (
        "TimescaleDB will keep dropping old chunks by itself, even after this session ends. "
        "Set this policy?"
    )
    spec: ClassVar[AgePolicySpec] = RETENTION
    done: ClassVar[str] = "Retention policy set: TimescaleDB drops chunks older than {} on its own schedule"
    params_model = RetentionParams


class RemoveRetentionPolicy(RemoveAgePolicy):
    name: ClassVar[str] = "timescale_remove_retention_policy"
    title: ClassVar[str] = "Remove retention policy"
    spec: ClassVar[AgePolicySpec] = RETENTION
    done: ClassVar[str] = "Retention policy removed; TimescaleDB no longer drops old chunks automatically"


class SetCompressionPolicy(SetAgePolicy[CompressionParams]):
    name: ClassVar[str] = "timescale_set_compression_policy"
    title: ClassVar[str] = "Set compression policy"
    spec: ClassVar[AgePolicySpec] = COMPRESSION
    done: ClassVar[str] = "Compression policy set: TimescaleDB compresses chunks older than {} on its own schedule"
    params_model = CompressionParams


class RemoveCompressionPolicy(RemoveAgePolicy):
    name: ClassVar[str] = "timescale_remove_compression_policy"
    title: ClassVar[str] = "Remove compression policy"
    spec: ClassVar[AgePolicySpec] = COMPRESSION
    done: ClassVar[str] = "Compression policy removed; TimescaleDB no longer compresses chunks automatically"
