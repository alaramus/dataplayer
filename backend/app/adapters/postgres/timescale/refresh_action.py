"""Reviewed refresh policy actions on an existing continuous aggregate."""

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
from app.adapters.postgres.timescale.age_policy_action import NoParams
from app.adapters.postgres.timescale.names import TIMESCALE_MENU
from app.adapters.postgres.timescale.plans import (
    RefreshPlan,
    RefreshWindow,
    TimeDuration,
)
from app.adapters.postgres.timescale.refresh_execution import execute_refresh
from app.adapters.postgres.timescale.refresh_plan import (
    inspect_refresh,
    plan_refresh,
    setting_refusal,
)
from app.adapters.postgres.timescale.reports import TIMESCALE_SECTION_ID
from app.adapters.postgres.timescale.targets import user_view
from app.adapters.protocol import AdapterError
from app.core.access import Access
from app.core.translation import N_, say

OffsetUnit = Literal["minute", "hour", "day", "week", "month", "year"]


class RefreshParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Bounded so every offset converts to a PostgreSQL interval without overflow.
    start_amount: int = Field(
        strict=True, gt=0, le=100_000, title=N_("Window starts"),
        description=N_("How long ago the refreshed window begins"),
        json_schema_extra=layout(row="start"),
    )
    start_unit: OffsetUnit = Field(title=N_("Unit"), json_schema_extra=layout(row="start"))
    end_amount: int = Field(
        strict=True, gt=0, le=100_000, title=N_("Window ends"),
        description=N_("How long ago it ends; more recent than the start"),
        json_schema_extra=layout(row="end"),
    )
    end_unit: OffsetUnit = Field(title=N_("Unit"), json_schema_extra=layout(row="end"))
    schedule_amount: int = Field(
        strict=True, gt=0, le=100_000, title=N_("Refresh every"), json_schema_extra=layout(row="schedule"),
    )
    schedule_unit: Literal["minute", "hour", "day", "week"] = Field(
        title=N_("Unit"), json_schema_extra=layout(row="schedule"),
    )

    def window(self) -> RefreshWindow:
        return RefreshWindow(
            start_offset=TimeDuration(amount=self.start_amount, unit=self.start_unit),
            end_offset=TimeDuration(amount=self.end_amount, unit=self.end_unit),
            schedule_interval=TimeDuration(amount=self.schedule_amount, unit=self.schedule_unit),
        )


async def preview_refresh(
    session: PostgresSession, schema_name: str, view_name: str, window: RefreshWindow | None,
) -> ActionPreview:
    try:
        async with session.inspection() as reader:
            plan = await plan_refresh(reader, schema_name, view_name, window)
    except ActionRefused as exc:
        return ActionPreview(summary=exc.message, blocked=True)
    except (AdapterError, ValueError, TimeoutError):
        return ActionPreview(summary=_unreadable(), blocked=True)
    target = sql.Identifier(plan.target.view_schema, plan.target.view_name).as_string()
    summary = (
        say("Set the refresh policy for {target}", target=target) if plan.window is not None
        else say("Remove the refresh policy from {target}", target=target)
    )
    return ActionPreview(summary=summary, items=_items(plan), fingerprint=plan.fingerprint())


def _unreadable() -> str:
    return say("TimescaleDB refresh policy metadata could not be inspected safely")


def _items(plan: RefreshPlan) -> list[str]:
    source = sql.Identifier(plan.target.source_schema, plan.target.source_name).as_string()
    items = [say("Source hypertable: {source}", source=source)]
    if plan.existing is None:
        items.append(say("No refresh policy exists yet"))
    else:
        job, refreshed, every = plan.existing.job_id, plan.existing.window(), plan.existing.schedule_interval
        items.append(
            say("Removes job {job}, which refreshes {window} every {every}", job=job, window=refreshed, every=every)
            if plan.window is None
            else say("Replaces job {job}, which refreshes {window} every {every}", job=job, window=refreshed, every=every)
        )
    if plan.window is not None:
        window = plan.window
        items.append(say(
            "New policy: refresh from {start} ago to {end} ago, every {every}",
            start=window.start_offset.label(), end=window.end_offset.label(), every=window.schedule_interval.label(),
        ))
        retention = plan.source_retention
        if retention is None:
            items.append(say("The source hypertable has no retention policy"))
        elif retention.older_than is not None:
            items.append(say(
                "The source drops chunks older than {age}; the window starts after that", age=retention.older_than,
            ))
        else:
            items.append(say(
                "The source drops chunks {chunks}; check that it keeps the raw data this window refreshes",
                chunks=retention.threshold(),
            ))
    items.extend((plan.impact, plan.said_coordination))
    return items


async def refresh_admission(
    session: PostgresSession, schema_name: str, view_name: str,
) -> tuple[str | None, str | None]:
    """Why setting, then removing, a refresh policy cannot be offered, from one snapshot."""
    try:
        async with session.inspection() as reader:
            state = await inspect_refresh(reader, schema_name, view_name)
    except ActionRefused as exc:
        return exc.message, exc.message
    except (AdapterError, ValueError, TimeoutError):
        return _unreadable(), _unreadable()
    removing = None if state.existing is not None else say("This continuous aggregate has no refresh policy")
    return setting_refusal(state), removing


class SetRefreshPolicy(Action[RefreshParams]):
    name: ClassVar[str] = "timescale_set_refresh_policy"
    title: ClassVar[str] = N_("Set refresh policy")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"view"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "structure"
    feature_requirements: ClassVar[tuple[FeatureCode, ...]] = ("timescaledb",)
    menu_group: ClassVar[str | None] = TIMESCALE_MENU
    params_model = RefreshParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        params = self._validated(raw)
        schema, node = await user_view(self._catalog, node_id)
        return await preview_refresh(self._session, schema.name, node.name, params.window())

    async def perform(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionResult:
        raise ActionRefused("conflict", say("Review the refresh policy plan before applying it"))

    async def perform_reviewed(
        self, node_id: str | None, raw: Mapping[str, Any], fingerprint: str,
    ) -> ActionResult:
        params = self._validated(raw)
        schema, node = await user_view(self._catalog, node_id)
        await execute_refresh(self._session, schema.name, node.name, params.window(), fingerprint)
        return ActionResult(
            message=say("Refresh policy set: TimescaleDB refreshes this aggregate on its own schedule"),
            reload_node_ids=[schema.id, node.id, TIMESCALE_SECTION_ID],
        )


class RemoveRefreshPolicy(Action[NoParams]):
    name: ClassVar[str] = "timescale_remove_refresh_policy"
    title: ClassVar[str] = N_("Remove refresh policy")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"view"})
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
        schema, node = await user_view(self._catalog, node_id)
        return await preview_refresh(self._session, schema.name, node.name, None)

    async def perform(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionResult:
        raise ActionRefused("conflict", say("Review the refresh policy plan before applying it"))

    async def perform_reviewed(
        self, node_id: str | None, raw: Mapping[str, Any], fingerprint: str,
    ) -> ActionResult:
        self._validated(raw)
        schema, node = await user_view(self._catalog, node_id)
        await execute_refresh(self._session, schema.name, node.name, None, fingerprint)
        return ActionResult(
            message=say("Refresh policy removed; TimescaleDB no longer refreshes this aggregate automatically"),
            reload_node_ids=[schema.id, node.id, TIMESCALE_SECTION_ID],
        )
