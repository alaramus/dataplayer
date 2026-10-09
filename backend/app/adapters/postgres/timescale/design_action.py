"""Hypertable settings: one design, one reviewed plan, one transaction (D207)."""

from collections.abc import Mapping
from typing import Any, ClassVar

from psycopg import sql
from pydantic import BaseModel, ConfigDict

from app.adapters.actions import (
    Action,
    ActionPreview,
    ActionRefused,
    ActionResult,
    ActsOn,
)
from app.adapters.catalog import NodeKind
from app.adapters.features import FeatureCode
from app.adapters.hypertable_design import (
    ChosenByTimescale,
    HypertableDesign,
    HypertableDesignState,
    NoColumns,
    OrderBy,
    SegmentBy,
)
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.design_execution import execute_design
from app.adapters.postgres.timescale.design_plan import (
    AddAgePolicy,
    AddHashDimension,
    AddReorderPolicy,
    AttachTablespace,
    ConfigureColumnstore,
    DesignStep,
    DetachTablespace,
    DisableColumnstore,
    Duration,
    HypertableDesignPlan,
    RemovePolicy,
    SetChunkInterval,
    SetPartitions,
    plan_design,
)
from app.adapters.postgres.timescale.design_state import read_current, read_state
from app.adapters.postgres.timescale.names import TIMESCALE_MENU
from app.adapters.postgres.timescale.reports import TIMESCALE_SECTION_ID
from app.adapters.postgres.timescale.targets import user_table
from app.adapters.protocol import AdapterError
from app.core.access import Access

_UNREADABLE = "The hypertable could not be inspected safely"
_POLICY_NOUNS = {"retention": "retention policy", "compression": "columnstore policy", "reorder": "reorder policy"}
_RETENTION_WARNING = (
    "TimescaleDB keeps dropping whole chunks past the retention age on its own schedule, "
    "after this session ends"
)


class HypertableDesignParams(BaseModel):
    # A screen of its own: a hypertable's settings are one picture, and the editor
    # is registered against this workflow rather than the action's name (D73).
    model_config = ConfigDict(extra="forbid", json_schema_extra={"x-ui-workflow": "hypertable-settings"})

    design: HypertableDesign


def _spoken(duration: Duration) -> str:
    return f"{duration.amount} {duration.unit}{'' if duration.amount == 1 else 's'}"


def _columns(value: SegmentBy | OrderBy | None) -> str:
    if value is None or isinstance(value, ChosenByTimescale):
        return "TimescaleDB's choice for each chunk"
    if isinstance(value, NoColumns):
        return "none"
    parts: list[str] = []
    for item in value.columns:
        if isinstance(item, str):
            parts.append(sql.Identifier(item).as_string())
        else:
            parts.append(sql.Identifier(item.column).as_string() + (" DESC" if item.descending else " ASC"))
    return ", ".join(parts)


def _columnstore_change(step: ConfigureColumnstore) -> str:
    changes = []
    if step.segment_changed:
        changes.append(f"segment by {_columns(step.segment_by)}")
    if step.order_changed:
        changes.append(f"order by {_columns(step.order_by)}")
    if step.merge_changed:
        changes.append(
            "no merging of chunks" if step.merge_interval is None
            else f"merge chunks into {_spoken(step.merge_interval)} as they are compressed"
        )
    lead = "Turn the columnstore on" if step.enable else "Columnstore settings for chunks compressed from now on"
    return f"{lead}: " + "; ".join(changes)


def _describe(step: DesignStep) -> str:
    match step:
        case RemovePolicy(kind=kind, job_id=job_id):
            return f"Remove the {_POLICY_NOUNS[kind]} (job {job_id})"
        case AddAgePolicy(kind="retention", older_than=older_than):
            return f"Add a retention policy: drop chunks older than {_spoken(older_than)}"
        case AddAgePolicy(older_than=older_than):
            return f"Add a columnstore policy: compress chunks older than {_spoken(older_than)}"
        case AddReorderPolicy(index=index):
            return f"Add a reorder policy by index {sql.Identifier(index).as_string()}"
        case SetChunkInterval(interval=interval):
            return f"New chunks cover {_spoken(interval)}; existing chunks keep their range"
        case SetPartitions(column=column, partitions=partitions):
            return (
                f"Hash {sql.Identifier(column).as_string()} into {partitions} partitions "
                "for new chunks"
            )
        case AddHashDimension(column=column, partitions=partitions):
            return f"Add a hash dimension on {sql.Identifier(column).as_string()} with {partitions} partitions"
        case ConfigureColumnstore():
            return _columnstore_change(step)
        case DisableColumnstore():
            return "Turn the columnstore off"
        case AttachTablespace(name=name):
            return f"Place new chunks in tablespace {sql.Identifier(name).as_string()} too"
        case DetachTablespace(name=name):
            return f"Stop placing new chunks in tablespace {sql.Identifier(name).as_string()}"
    raise AssertionError("every step is described")


def _items(plan: HypertableDesignPlan) -> list[str]:
    items = [_describe(step) for step in plan.steps]
    if any(isinstance(step, AddAgePolicy) and step.kind == "retention" for step in plan.steps):
        items.append(_RETENTION_WARNING)
    items.append(plan.coordination)
    return items


async def preview_design(
    session: PostgresSession, schema_name: str, table_name: str, requested: HypertableDesign,
) -> ActionPreview:
    try:
        async with session.inspection() as reader:
            plan = await plan_design(reader, schema_name, table_name, requested)
    except ActionRefused as exc:
        return ActionPreview(summary=exc.message, blocked=True)
    except (AdapterError, ValueError, TimeoutError):
        return ActionPreview(summary=_UNREADABLE, blocked=True)
    target = sql.Identifier(plan.current.target.schema_name, plan.current.target.table_name).as_string()
    if not plan.steps:
        return ActionPreview(summary=f"{target} already matches these settings", blocked=True)
    return ActionPreview(summary=f"Change {target}", items=_items(plan), fingerprint=plan.fingerprint())


async def design_state(
    session: PostgresSession, node_id: str, schema_name: str, table_name: str,
) -> HypertableDesignState:
    try:
        async with session.inspection() as reader:
            return await read_state(reader, node_id, schema_name, table_name)
    except (AdapterError, ValueError):
        return HypertableDesignState(node_id=node_id, reason=_UNREADABLE)


async def design_admission(session: PostgresSession, schema_name: str, table_name: str) -> str | None:
    """Why the editor cannot be offered for this hypertable, from one read of it."""
    try:
        async with session.inspection() as reader:
            await read_current(reader, schema_name, table_name)
    except ActionRefused as exc:
        return exc.message
    except (AdapterError, ValueError, TimeoutError):
        return _UNREADABLE
    return None


class DesignHypertable(Action[HypertableDesignParams]):
    name: ClassVar[str] = "timescale_design_hypertable"
    title: ClassVar[str] = "Hypertable settings"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "structure"
    feature_requirements: ClassVar[tuple[FeatureCode, ...]] = ("timescaledb",)
    menu_group: ClassVar[str | None] = TIMESCALE_MENU
    params_model = HypertableDesignParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def state(self, node_id: str) -> HypertableDesignState:
        try:
            schema, node = await user_table(self._catalog, node_id)
        except ActionRefused as exc:
            return HypertableDesignState(node_id=node_id, reason=exc.message)
        return await design_state(self._session, node_id, schema.name, node.name)

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        params = self._validated(raw)
        schema, node = await user_table(self._catalog, node_id)
        return await preview_design(self._session, schema.name, node.name, params.design)

    async def perform(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionResult:
        raise ActionRefused("conflict", "Review the hypertable plan before applying it")

    async def perform_reviewed(
        self, node_id: str | None, raw: Mapping[str, Any], fingerprint: str,
    ) -> ActionResult:
        params = self._validated(raw)
        schema, node = await user_table(self._catalog, node_id)
        plan = await execute_design(self._session, schema.name, node.name, params.design, fingerprint)
        count = len(plan.steps)
        return ActionResult(
            message=f"Hypertable changed: {count} {'change' if count == 1 else 'changes'} applied",
            reload_node_ids=[schema.id, node.id, TIMESCALE_SECTION_ID],
        )
