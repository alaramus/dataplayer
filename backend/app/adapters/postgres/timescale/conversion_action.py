"""Reviewed conversion of one empty ordinary table into a hypertable."""

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
from app.adapters.catalog import NodeKind, SchemaNode, TableNode
from app.adapters.features import FeatureCode
from app.adapters.layout import layout
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.conversion_execution import execute_conversion
from app.adapters.postgres.timescale.conversion_plan import (
    inspect_conversion,
    plan_conversion,
)
from app.adapters.postgres.timescale.names import TIMESCALE_MENU
from app.adapters.postgres.timescale.plans import ConversionPlan, TimeDuration
from app.adapters.postgres.timescale.reports import TIMESCALE_SECTION_ID
from app.adapters.postgres.timescale.targets import user_table
from app.adapters.protocol import AdapterError
from app.core.access import Access

_UNREADABLE = "The table could not be inspected safely for conversion"


class ConversionParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time_column: str = Field(
        min_length=1, max_length=63, title="Time column",
        description="A timestamp or date column of this table",
    )
    amount: int = Field(
        strict=True, gt=0, le=100_000, title="Chunk interval", json_schema_extra=layout(row="interval"),
    )
    unit: Literal["hour", "day", "week"] = Field(title="Unit", json_schema_extra=layout(row="interval"))

    def interval(self) -> TimeDuration:
        return TimeDuration(amount=self.amount, unit=self.unit)


async def preview_conversion(
    session: PostgresSession, schema_name: str, table_name: str, column_name: str, interval: TimeDuration,
) -> ActionPreview:
    try:
        async with session.inspection() as reader:
            plan = await plan_conversion(reader, schema_name, table_name, column_name, interval)
    except ActionRefused as exc:
        return ActionPreview(summary=exc.message, blocked=True)
    except (AdapterError, ValueError, TimeoutError):
        return ActionPreview(summary=_UNREADABLE, blocked=True)
    target = sql.Identifier(plan.target.schema_name, plan.target.table_name).as_string()
    return ActionPreview(
        summary=f"Convert {target} into a hypertable", items=_items(plan), fingerprint=plan.fingerprint(),
    )


def _items(plan: ConversionPlan) -> list[str]:
    column = sql.Identifier(plan.column.name).as_string()
    items = [
        f"Time column: {column} ({plan.column.type})",
        f"Chunk interval: {plan.interval.interval_value()}",
        "The table is empty, and the conversion refuses if a row arrives before it runs",
    ]
    if not plan.column.not_null:
        items.append(f"{column} becomes NOT NULL")
    items.append(
        f"An index on {column} alone already exists, so TimescaleDB adds none" if plan.time_index_exists
        else f"TimescaleDB adds an index on {column}, newest first"
    )
    items.extend((plan.impact, plan.coordination))
    return items


async def conversion_admission(session: PostgresSession, schema_name: str, table_name: str) -> str | None:
    """Why this table cannot be converted whatever column and interval are chosen."""
    try:
        async with session.inspection() as reader:
            await inspect_conversion(reader, schema_name, table_name)
    except ActionRefused as exc:
        return exc.message
    except (AdapterError, ValueError, TimeoutError):
        return _UNREADABLE
    return None


class ConvertToHypertable(Action[ConversionParams]):
    name: ClassVar[str] = "timescale_convert_to_hypertable"
    title: ClassVar[str] = "Convert to hypertable"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "structure"
    destructive: ClassVar[bool] = True
    question: ClassVar[str | None] = (
        "The table becomes a hypertable, which DataPlayer cannot turn back into an ordinary table. Convert it?"
    )
    feature_requirements: ClassVar[tuple[FeatureCode, ...]] = ("timescaledb",)
    menu_group: ClassVar[str | None] = TIMESCALE_MENU
    params_model = ConversionParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def _target(self, node_id: str | None) -> tuple[SchemaNode, TableNode]:
        schema, node = await user_table(self._catalog, node_id)
        # Ordinary protections still apply: an extension-owned or protected table is refused here too.
        reason = await self._catalog.relation_action_reason(schema.name, node.name)
        if reason is not None:
            raise ActionRefused("not_applicable", reason)
        return schema, node

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        params = self._validated(raw)
        schema, node = await self._target(node_id)
        return await preview_conversion(self._session, schema.name, node.name, params.time_column, params.interval())

    async def perform(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionResult:
        raise ActionRefused("conflict", "Review the conversion plan before applying it")

    async def perform_reviewed(
        self, node_id: str | None, raw: Mapping[str, Any], fingerprint: str,
    ) -> ActionResult:
        params = self._validated(raw)
        schema, node = await self._target(node_id)
        await execute_conversion(
            self._session, schema.name, node.name, params.time_column, params.interval(), fingerprint,
        )
        return ActionResult(
            message="Converted to a hypertable; rows added from now on are stored in chunks",
            reload_node_ids=[schema.id, node.id, TIMESCALE_SECTION_ID],
        )
