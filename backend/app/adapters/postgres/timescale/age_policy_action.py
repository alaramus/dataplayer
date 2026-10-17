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
    unreadable,
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
from app.core.translation import N_, say


class ThresholdParams(TimeDuration):
    unit: Literal["hour", "day", "week", "month", "year"] = Field(
        title=N_("Unit"), json_schema_extra=layout(row="threshold"),
    )

    def duration(self) -> TimeDuration:
        return TimeDuration(amount=self.amount, unit=self.unit)


class RetentionParams(ThresholdParams):
    amount: int = Field(
        strict=True, gt=0, le=2_147_483_647, title=N_("Drop chunks older than"),
        json_schema_extra=layout(row="threshold"),
    )


class CompressionParams(ThresholdParams):
    amount: int = Field(
        strict=True, gt=0, le=2_147_483_647, title=N_("Compress chunks older than"),
        json_schema_extra=layout(row="threshold"),
    )


class NoParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


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
        return ActionPreview(summary=unreadable(spec), blocked=True)
    return ActionPreview(summary=_summary(plan), items=_items(plan), fingerprint=plan.fingerprint())


def _summary(plan: AgePolicyPlan) -> str:
    target = sql.Identifier(plan.target.schema_name, plan.target.table_name).as_string()
    if plan.kind == "retention":
        if plan.older_than is not None:
            return say("Set the retention policy for {target}", target=target)
        return say("Remove the retention policy from {target}", target=target)
    if plan.older_than is not None:
        return say("Set the compression policy for {target}", target=target)
    return say("Remove the compression policy from {target}", target=target)


def _items(plan: AgePolicyPlan) -> list[str]:
    retention = plan.kind == "retention"
    items = [say("Time dimension: {column}", column=sql.Identifier(plan.target.column_name).as_string())]
    if plan.existing is None:
        items.append(say("No retention policy exists yet") if retention else say("No compression policy exists yet"))
    else:
        items.append(_existing(plan.kind, plan.existing.job_id, plan.existing.threshold(), plan.older_than is None))
        if plan.older_than is not None:
            items.append(say(
                "The current policy runs every {every}; its replacement uses TimescaleDB's default schedule",
                every=plan.existing.schedule_interval,
            ))
    if plan.older_than is not None:
        age = plan.older_than.label()
        items.append(
            say("New policy: drop chunks older than {age}", age=age) if retention
            else say("New policy: compress chunks older than {age}", age=age)
        )
    items.extend((plan.impact, plan.said_coordination))
    return items


def _existing(kind: AgePolicyKind, job: str, chunks: str, removing: bool) -> str:
    if kind == "retention":
        if removing:
            return say("Removes job {job}, which drops chunks {chunks}", job=job, chunks=chunks)
        return say("Replaces job {job}, which drops chunks {chunks}", job=job, chunks=chunks)
    if removing:
        return say("Removes job {job}, which compresses chunks {chunks}", job=job, chunks=chunks)
    return say("Replaces job {job}, which compresses chunks {chunks}", job=job, chunks=chunks)


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
        return unreadable(spec), unreadable(spec)
    # One day admits date and timestamp dimensions without choosing the user's threshold.
    return _refusal(spec, state, TimeDuration(amount=1, unit="day")), _refusal(spec, state, None)


def _refusal(spec: AgePolicySpec, state: AgePolicyState, older_than: TimeDuration | None) -> str | None:
    try:
        age_policy_plan(spec, state, older_than)
    except ActionRefused as exc:
        return exc.message
    return None


def _review_first(spec: AgePolicySpec) -> ActionRefused:
    if spec.kind == "retention":
        return ActionRefused("conflict", say("Review the retention policy plan before applying it"))
    return ActionRefused("conflict", say("Review the compression policy plan before applying it"))


class SetAgePolicy[P: ThresholdParams](Action[P]):
    spec: ClassVar[AgePolicySpec]
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
        raise _review_first(self.spec)

    def done(self, age: str) -> str:
        """The result message, with the requested threshold."""
        raise NotImplementedError

    async def perform_reviewed(
        self, node_id: str | None, raw: Mapping[str, Any], fingerprint: str,
    ) -> ActionResult:
        params = self._validated(raw)
        schema, node = await user_table(self._catalog, node_id)
        await execute_age_policy(
            self._session, self.spec, schema.name, node.name, params.duration(), fingerprint,
        )
        return ActionResult(
            message=self.done(params.label()),
            reload_node_ids=[schema.id, node.id, TIMESCALE_SECTION_ID],
        )


class RemoveAgePolicy(Action[NoParams]):
    spec: ClassVar[AgePolicySpec]
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
        raise _review_first(self.spec)

    def done(self) -> str:
        raise NotImplementedError

    async def perform_reviewed(
        self, node_id: str | None, raw: Mapping[str, Any], fingerprint: str,
    ) -> ActionResult:
        self._validated(raw)
        schema, node = await user_table(self._catalog, node_id)
        await execute_age_policy(self._session, self.spec, schema.name, node.name, None, fingerprint)
        return ActionResult(message=self.done(), reload_node_ids=[schema.id, node.id, TIMESCALE_SECTION_ID])


class SetRetentionPolicy(SetAgePolicy[RetentionParams]):
    name: ClassVar[str] = "timescale_set_retention_policy"
    title: ClassVar[str] = N_("Set retention policy")
    destructive: ClassVar[bool] = True
    question: ClassVar[str | None] = N_(
        "TimescaleDB will keep dropping old chunks by itself, even after this session ends. "
        "Set this policy?"
    )
    spec: ClassVar[AgePolicySpec] = RETENTION
    params_model = RetentionParams

    def done(self, age: str) -> str:
        return say("Retention policy set: TimescaleDB drops chunks older than {age} on its own schedule", age=age)


class RemoveRetentionPolicy(RemoveAgePolicy):
    name: ClassVar[str] = "timescale_remove_retention_policy"
    title: ClassVar[str] = N_("Remove retention policy")
    spec: ClassVar[AgePolicySpec] = RETENTION

    def done(self) -> str:
        return say("Retention policy removed; TimescaleDB no longer drops old chunks automatically")


class SetCompressionPolicy(SetAgePolicy[CompressionParams]):
    name: ClassVar[str] = "timescale_set_compression_policy"
    title: ClassVar[str] = N_("Set compression policy")
    spec: ClassVar[AgePolicySpec] = COMPRESSION
    params_model = CompressionParams

    def done(self, age: str) -> str:
        return say(
            "Compression policy set: TimescaleDB compresses chunks older than {age} on its own schedule", age=age,
        )


class RemoveCompressionPolicy(RemoveAgePolicy):
    name: ClassVar[str] = "timescale_remove_compression_policy"
    title: ClassVar[str] = N_("Remove compression policy")
    spec: ClassVar[AgePolicySpec] = COMPRESSION

    def done(self) -> str:
        return say("Compression policy removed; TimescaleDB no longer compresses chunks automatically")
