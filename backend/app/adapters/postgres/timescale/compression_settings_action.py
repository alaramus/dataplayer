"""Reviewed compression settings on one time hypertable; nothing is compressed by it."""

from collections.abc import Mapping
from typing import Any, ClassVar

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
from app.adapters.postgres.timescale.compression_settings_execution import (
    execute_compression_settings,
)
from app.adapters.postgres.timescale.compression_settings_plan import (
    order_option,
    plan_compression_settings,
    segment_option,
)
from app.adapters.postgres.timescale.plans import CompressionSettingsPlan
from app.adapters.postgres.timescale.reports import TIMESCALE_SECTION_ID
from app.adapters.postgres.timescale.targets import user_table
from app.adapters.protocol import AdapterError
from app.core.access import Access

_UNREADABLE = "TimescaleDB compression settings could not be inspected safely"


class CompressionSettingsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_by: str = Field(
        default="", max_length=4096, title="Segment by",
        description="One column per line; leave empty for none",
        json_schema_extra=layout(multiline=True),
    )
    order_by: str = Field(
        default="", max_length=4096, title="Order by",
        description=(
            "One column per line, optionally followed by ASC or DESC and NULLS FIRST or NULLS LAST; "
            "the time column is added descending when neither list names it"
        ),
        json_schema_extra=layout(multiline=True),
    )


async def preview_compression_settings(
    session: PostgresSession, schema_name: str, table_name: str, segment_text: str, order_text: str,
) -> ActionPreview:
    try:
        async with session.inspection() as reader:
            plan = await plan_compression_settings(reader, schema_name, table_name, segment_text, order_text)
    except ActionRefused as exc:
        return ActionPreview(summary=exc.message, blocked=True)
    except (AdapterError, ValueError, TimeoutError):
        return ActionPreview(summary=_UNREADABLE, blocked=True)
    target = sql.Identifier(plan.target.schema_name, plan.target.table_name).as_string()
    summary = (
        f"Change the compression settings of {target}" if plan.enabled
        else f"Enable compression on {target}"
    )
    return ActionPreview(summary=summary, items=_items(plan), fingerprint=plan.fingerprint())


def _items(plan: CompressionSettingsPlan) -> list[str]:
    items = [f"Time dimension: {sql.Identifier(plan.target.column_name).as_string()}"]
    if plan.enabled:
        items.append(f"Current segment by: {plan.current_segment_by or 'none'}")
        items.append(f"Current order by: {plan.current_order_by or 'none'}")
    else:
        items.append("Compression is not enabled yet")
    items.append(f"New segment by: {segment_option(plan.segment_by) or 'none'}")
    items.append(f"New order by: {order_option(plan.order_by)}")
    if plan.any_compressed:
        items.append("Already compressed chunks keep the settings they were compressed with")
    items.extend(
        f"TimescaleDB recommends segmenting or ordering by the unique column {sql.Identifier(name).as_string()}"
        for name in plan.unsegmented_unique
    )
    items.extend((plan.impact, plan.coordination))
    return items


async def compression_settings_admission(
    session: PostgresSession, schema_name: str, table_name: str,
) -> str | None:
    """Why the settings cannot be offered here, planned from the default settings."""
    try:
        async with session.inspection() as reader:
            await plan_compression_settings(reader, schema_name, table_name, "", "")
    except ActionRefused as exc:
        return exc.message
    except (AdapterError, ValueError, TimeoutError):
        return _UNREADABLE
    return None


class ConfigureCompression(Action[CompressionSettingsParams]):
    name: ClassVar[str] = "timescale_configure_compression"
    title: ClassVar[str] = "Configure compression"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "structure"
    feature_requirements: ClassVar[tuple[FeatureCode, ...]] = ("timescaledb",)
    params_model = CompressionSettingsParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        params = self._validated(raw)
        schema, node = await user_table(self._catalog, node_id)
        return await preview_compression_settings(
            self._session, schema.name, node.name, params.segment_by, params.order_by,
        )

    async def perform(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionResult:
        raise ActionRefused("conflict", "Review the compression settings plan before applying it")

    async def perform_reviewed(
        self, node_id: str | None, raw: Mapping[str, Any], fingerprint: str,
    ) -> ActionResult:
        params = self._validated(raw)
        schema, node = await user_table(self._catalog, node_id)
        plan = await execute_compression_settings(
            self._session, schema.name, node.name, params.segment_by, params.order_by, fingerprint,
        )
        message = (
            "Compression settings changed; only chunks compressed from now on use them" if plan.enabled
            else "Compression enabled; chunks are compressed by a compression policy or on request"
        )
        return ActionResult(message=message, reload_node_ids=[schema.id, node.id, TIMESCALE_SECTION_ID])
