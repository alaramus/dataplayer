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

_UNREADABLE = "TimescaleDB refresh policy metadata could not be inspected safely"
OffsetUnit = Literal["minute", "hour", "day", "week", "month", "year"]


class RefreshParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Bounded so every offset converts to a PostgreSQL interval without overflow.
    start_amount: int = Field(
        strict=True, gt=0, le=100_000, title="Window starts",
        description="How long ago the refreshed window begins",
        json_schema_extra=layout(row="start"),
    )
    start_unit: OffsetUnit = Field(title="Unit", json_schema_extra=layout(row="start"))
    end_amount: int = Field(
        strict=True, gt=0, le=100_000, title="Window ends",
        description="How long ago it ends; more recent than the start",
        json_schema_extra=layout(row="end"),
    )
    end_unit: OffsetUnit = Field(title="Unit", json_schema_extra=layout(row="end"))
    schedule_amount: int = Field(
        strict=True, gt=0, le=100_000, title="Refresh every", json_schema_extra=layout(row="schedule"),
    )
    schedule_unit: Literal["minute", "hour", "day", "week"] = Field(
        title="Unit", json_schema_extra=layout(row="schedule"),
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
        return ActionPreview(summary=_UNREADABLE, blocked=True)
    target = sql.Identifier(plan.target.view_schema, plan.target.view_name).as_string()
    summary = (
        f"Set the refresh policy for {target}" if plan.window is not None
        else f"Remove the refresh policy from {target}"
    )
    return ActionPreview(summary=summary, items=_items(plan), fingerprint=plan.fingerprint())


def _items(plan: RefreshPlan) -> list[str]:
    source = sql.Identifier(plan.target.source_schema, plan.target.source_name).as_string()
    items = [f"Source hypertable: {source}"]
    if plan.existing is None:
        items.append("No refresh policy exists yet")
    else:
        verb = "Removes" if plan.window is None else "Replaces"
        items.append(
            f"{verb} job {plan.existing.job_id}, which refreshes {plan.existing.window()} "
            f"every {plan.existing.schedule_interval}"
        )
    if plan.window is not None:
        window = plan.window
        items.append(
            f"New policy: refresh from {window.start_offset.interval_value()} ago to "
            f"{window.end_offset.interval_value()} ago, every {window.schedule_interval.interval_value()}"
        )
        retention = plan.source_retention
        if retention is None:
            items.append("The source hypertable has no retention policy")
        elif retention.older_than is not None:
            items.append(
                f"The source drops chunks older than {retention.older_than}; the window starts after that"
            )
        else:
            items.append(
                f"The source drops chunks {retention.threshold()}; "
                "check that it keeps the raw data this window refreshes"
            )
    items.extend((plan.impact, plan.coordination))
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
        return _UNREADABLE, _UNREADABLE
    removing = None if state.existing is not None else "This continuous aggregate has no refresh policy"
    return setting_refusal(state), removing


class SetRefreshPolicy(Action[RefreshParams]):
    name: ClassVar[str] = "timescale_set_refresh_policy"
    title: ClassVar[str] = "Set refresh policy"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"view"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "structure"
    feature_requirements: ClassVar[tuple[FeatureCode, ...]] = ("timescaledb",)
    params_model = RefreshParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        params = self._validated(raw)
        schema, node = await user_view(self._catalog, node_id)
        return await preview_refresh(self._session, schema.name, node.name, params.window())

    async def perform(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionResult:
        raise ActionRefused("conflict", "Review the refresh policy plan before applying it")

    async def perform_reviewed(
        self, node_id: str | None, raw: Mapping[str, Any], fingerprint: str,
    ) -> ActionResult:
        params = self._validated(raw)
        schema, node = await user_view(self._catalog, node_id)
        await execute_refresh(self._session, schema.name, node.name, params.window(), fingerprint)
        return ActionResult(
            message="Refresh policy set: TimescaleDB refreshes this aggregate on its own schedule",
            reload_node_ids=[schema.id, node.id, TIMESCALE_SECTION_ID],
        )


class RemoveRefreshPolicy(Action[NoParams]):
    name: ClassVar[str] = "timescale_remove_refresh_policy"
    title: ClassVar[str] = "Remove refresh policy"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"view"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "structure"
    feature_requirements: ClassVar[tuple[FeatureCode, ...]] = ("timescaledb",)
    params_model = NoParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        self._validated(raw)
        schema, node = await user_view(self._catalog, node_id)
        return await preview_refresh(self._session, schema.name, node.name, None)

    async def perform(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionResult:
        raise ActionRefused("conflict", "Review the refresh policy plan before applying it")

    async def perform_reviewed(
        self, node_id: str | None, raw: Mapping[str, Any], fingerprint: str,
    ) -> ActionResult:
        self._validated(raw)
        schema, node = await user_view(self._catalog, node_id)
        await execute_refresh(self._session, schema.name, node.name, None, fingerprint)
        return ActionResult(
            message="Refresh policy removed; TimescaleDB no longer refreshes this aggregate automatically",
            reload_node_ids=[schema.id, node.id, TIMESCALE_SECTION_ID],
        )
