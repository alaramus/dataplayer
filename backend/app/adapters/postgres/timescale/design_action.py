"""Hypertable settings: one design, one reviewed plan, one transaction (D207)."""

from collections.abc import Mapping, Sequence
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
from app.adapters.catalog import NodeKind, SchemaNode, TableNode
from app.adapters.features import FeatureCode
from app.adapters.hypertable_design import (
    ChosenByTimescale,
    HypertableDesign,
    HypertableDesignState,
    NoColumns,
    NowTemplate,
    OrderBy,
    SegmentBy,
    SparseIndexes,
)
from app.adapters.operations import (
    ObservedState,
    OperationPlan,
    OperationTarget,
    UnitOutcome,
)
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.design_execution import (
    execute_design,
    execute_design_job,
)
from app.adapters.postgres.timescale.design_plan import (
    AddAgePolicy,
    AddCompactionPolicy,
    AddHashDimension,
    AddReorderPolicy,
    AttachTablespace,
    ConfigureColumnstore,
    ConvertTable,
    Count,
    CreateNowFunction,
    DesignStep,
    DetachTablespace,
    DisableColumnstore,
    HypertableDesignPlan,
    Length,
    RemovePolicy,
    SetChunkInterval,
    SetIntegerNow,
    SetPartitions,
    plan_design,
)
from app.adapters.postgres.timescale.design_state import (
    is_hypertable,
    read_current,
    read_state,
    read_table,
    row_estimate,
)
from app.adapters.postgres.timescale.names import TIMESCALE_MENU
from app.adapters.postgres.timescale.reports import TIMESCALE_SECTION_ID
from app.adapters.postgres.timescale.targets import user_table
from app.adapters.protocol import AdapterError, NodeNotFound
from app.core.access import Access
from app.core.config import settings
from app.core.translation import N_, say

_EXISTS = """
SELECT 1 FROM pg_catalog.pg_class AS relation
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
WHERE namespace.nspname = %s AND relation.relname = %s AND relation.relkind = 'r'
"""



class HypertableDesignParams(BaseModel):
    # A screen of its own: a hypertable's settings are one picture, and the editor
    # is registered against this workflow rather than the action's name (D73).
    model_config = ConfigDict(extra="forbid", json_schema_extra={"x-ui-workflow": "hypertable-settings"})

    design: HypertableDesign


def _unreadable() -> str:
    return say("The hypertable could not be inspected safely")


def _spoken(length: Length) -> str:
    """A length as a person reads it, a number and its unit."""
    if isinstance(length, Count):
        amount = f"{length.amount:,}"
        return say("{amount} value", amount=amount) if length.amount == 1 else say("{amount} values", amount=amount)
    amount = str(length.amount)
    if length.amount == 1:
        match length.unit:
            case "second":
                return say("{amount} second", amount=amount)
            case "minute":
                return say("{amount} minute", amount=amount)
            case "hour":
                return say("{amount} hour", amount=amount)
            case "day":
                return say("{amount} day", amount=amount)
            case "week":
                return say("{amount} week", amount=amount)
            case "month":
                return say("{amount} month", amount=amount)
        return say("{amount} year", amount=amount)
    match length.unit:
        case "second":
            return say("{amount} seconds", amount=amount)
        case "minute":
            return say("{amount} minutes", amount=amount)
        case "hour":
            return say("{amount} hours", amount=amount)
        case "day":
            return say("{amount} days", amount=amount)
        case "week":
            return say("{amount} weeks", amount=amount)
        case "month":
            return say("{amount} months", amount=amount)
    return say("{amount} years", amount=amount)


def _routine(schema_name: str, name: str) -> str:
    return sql.Identifier(schema_name, name).as_string() + "()"


def _columns(value: SegmentBy | OrderBy | None) -> str:
    """The columns of a list, or what stands for them, worded to follow "segment by"."""
    if value is None or isinstance(value, ChosenByTimescale):
        return say("TimescaleDB's choice for each chunk")
    if isinstance(value, NoColumns):
        return say("none")
    parts: list[str] = []
    for item in value.columns:
        if isinstance(item, str):
            parts.append(sql.Identifier(item).as_string())
        else:
            parts.append(sql.Identifier(item.column).as_string() + (" DESC" if item.descending else " ASC"))
    return ", ".join(parts)


def _columnstore_change(step: ConfigureColumnstore) -> str:
    # Each change is a phrase of its own, listed after the lead the way a
    # preview lists its lines; none takes its words from another.
    changes = []
    if step.segment_changed:
        changes.append(say("segment by {columns}", columns=_columns(step.segment_by)))
    if step.order_changed:
        changes.append(say("order by {columns}", columns=_columns(step.order_by)))
    if step.sparse_changed:
        changes.append(say("sparse indexes {indexes}", indexes=_sparse(step.sparse_indexes)))
    if step.merge_changed:
        changes.append(
            say("no merging of chunks") if step.merge_interval is None
            else say("merge chunks into {length} as they are compressed", length=_spoken(step.merge_interval))
        )
    listed = "; ".join(changes)
    if step.enable:
        return say("Turn the columnstore on: {changes}", changes=listed)
    return say("Columnstore settings for chunks compressed from now on: {changes}", changes=listed)


def _sparse(value: SparseIndexes) -> str:
    if isinstance(value, ChosenByTimescale):
        return say("TimescaleDB's choice")
    if isinstance(value, NoColumns):
        return say("none")
    return ", ".join(
        say("{kind} on {column}", kind=index.kind, column=sql.Identifier(index.column).as_string())
        for index in value.indexes
    )


def _conversion(step: ConvertTable) -> str:
    column = sql.Identifier(step.column).as_string()
    length = _spoken(step.interval)
    if step.migrate:
        return say(
            "Convert the table into a hypertable by {column} ({type}), chunks of {length}, "
            "and move its rows into chunks",
            column=column, type=step.column_type, length=length,
        )
    return say(
        "Convert the table into a hypertable by {column} ({type}), chunks of {length}, while it is empty",
        column=column, type=step.column_type, length=length,
    )


def _describe(step: DesignStep) -> str:
    match step:
        case ConvertTable():
            return _conversion(step)
        case RemovePolicy(kind="retention", job_id=job_id):
            return say("Remove the retention policy (job {job})", job=job_id)
        case RemovePolicy(kind="compression", job_id=job_id):
            return say("Remove the columnstore policy (job {job})", job=job_id)
        case RemovePolicy(kind="reorder", job_id=job_id):
            return say("Remove the reorder policy (job {job})", job=job_id)
        case RemovePolicy(job_id=job_id):
            return say("Remove the compaction policy (job {job})", job=job_id)
        case AddAgePolicy(kind="retention", older_than=older_than):
            return say("Add a retention policy: drop chunks older than {length}", length=_spoken(older_than))
        case AddAgePolicy(older_than=older_than):
            return say("Add a columnstore policy: compress chunks older than {length}", length=_spoken(older_than))
        case AddCompactionPolicy():
            return say("Add a compaction policy: merge small compressed chunks on TimescaleDB's schedule")
        case AddReorderPolicy(index=index):
            return say("Add a reorder policy by index {index}", index=sql.Identifier(index).as_string())
        case SetChunkInterval(interval=interval):
            return say("New chunks cover {length}; existing chunks keep their range", length=_spoken(interval))
        case SetPartitions(column=column, partitions=partitions):
            return say(
                "Hash {column} into {partitions} partitions for new chunks",
                column=sql.Identifier(column).as_string(), partitions=partitions,
            )
        case AddHashDimension(column=column, partitions=partitions):
            return say(
                "Add a hash dimension on {column} with {partitions} partitions",
                column=sql.Identifier(column).as_string(), partitions=partitions,
            )
        case ConfigureColumnstore():
            return _columnstore_change(step)
        case DisableColumnstore():
            return say("Turn the columnstore off")
        case AttachTablespace(name=name):
            return say("Place new chunks in tablespace {tablespace} too", tablespace=sql.Identifier(name).as_string())
        case DetachTablespace(name=name):
            return say("Stop placing new chunks in tablespace {tablespace}", tablespace=sql.Identifier(name).as_string())
        case CreateNowFunction(schema_name=schema_name, name=name, template=template, column_type=column_type):
            return _now_function(_routine(schema_name, name), template, column_type)
        case SetIntegerNow(schema_name=schema_name, name=name):
            return say(
                "Policies take the current value of the time column from {function}",
                function=_routine(schema_name, name),
            )
    raise AssertionError("every step is described")


def _now_function(function: str, template: NowTemplate, column_type: str) -> str:
    match template:
        case "epoch_seconds":
            return say(
                "Create function {function} returning the seconds since 1970 as {type}",
                function=function, type=column_type,
            )
        case "epoch_milliseconds":
            return say(
                "Create function {function} returning the milliseconds since 1970 as {type}",
                function=function, type=column_type,
            )
    return say(
        "Create function {function} returning the microseconds since 1970 as {type}",
        function=function, type=column_type,
    )


def _conversion_notes(step: ConvertTable, row_estimate: int | None) -> list[str]:
    column = sql.Identifier(step.column).as_string()
    notes = []
    if not step.column_not_null:
        notes.append(
            say("{column} becomes NOT NULL; a row without a time makes the conversion fail and roll back", column=column)
            if step.migrate else say("{column} becomes NOT NULL", column=column)
        )
    notes.append(
        say("An index on {column} alone already exists, so TimescaleDB adds none", column=column)
        if step.time_index_exists
        else say("TimescaleDB adds an index on {column}, newest first", column=column)
    )
    if step.migrate:
        notes.extend((
            say(
                "Moves an unknown number of rows into chunks as a job in Activity; the table is locked against "
                "reads and writes until it ends"
            ) if row_estimate is None else say(
                "Moves about {count} rows into chunks as a job in Activity; the table is locked against "
                "reads and writes until it ends",
                count=f"{row_estimate:,}",
            ),
            say(
                "Rolled back whole if it fails, is cancelled or runs past {seconds} seconds; "
                "nothing is left half converted",
                seconds=settings.TIMESCALE_CONVERSION_TIMEOUT_SECONDS,
            ),
        ))
    notes.append(say("DataPlayer cannot turn a hypertable back into an ordinary table"))
    return notes


def _items(plan: HypertableDesignPlan, row_estimate: int | None = None) -> list[str]:
    items = [_describe(step) for step in plan.steps]
    for step in plan.steps:
        if isinstance(step, ConvertTable):
            items.extend(_conversion_notes(step, row_estimate))
    if any(isinstance(step, AddAgePolicy) and step.kind == "retention" for step in plan.steps):
        items.append(say(
            "TimescaleDB keeps dropping whole chunks past the retention age on its own schedule, "
            "after this session ends"
        ))
    if not plan.migrates:
        items.append(plan.coordination)
    return items


async def preview_design(
    session: PostgresSession, schema_name: str, table_name: str, requested: HypertableDesign,
) -> ActionPreview:
    try:
        async with session.inspection() as reader:
            plan = await plan_design(reader, schema_name, table_name, requested)
            estimate = await row_estimate(reader, plan.current.target.relation_oid) if plan.migrates else None
    except ActionRefused as exc:
        return ActionPreview(summary=exc.message, blocked=True)
    except (AdapterError, ValueError, TimeoutError):
        return ActionPreview(summary=_unreadable(), blocked=True)
    target = sql.Identifier(plan.current.target.schema_name, plan.current.target.table_name).as_string()
    if not plan.steps:
        return ActionPreview(summary=say("{target} already matches these settings", target=target), blocked=True)
    converts = any(isinstance(step, ConvertTable) for step in plan.steps)
    return ActionPreview(
        summary=(
            say("Convert {target} into a hypertable", target=target) if converts
            else say("Change {target}", target=target)
        ),
        items=_items(plan, estimate), fingerprint=plan.fingerprint(), runs_as_job=plan.migrates,
    )


async def design_state(
    session: PostgresSession, node_id: str, schema_name: str, table_name: str,
) -> HypertableDesignState:
    try:
        async with session.inspection() as reader:
            return await read_state(reader, node_id, schema_name, table_name)
    except (AdapterError, ValueError):
        return HypertableDesignState(node_id=node_id, reason=_unreadable())


async def design_admission(session: PostgresSession, schema_name: str, table_name: str) -> str | None:
    """Why the editor cannot be offered for this table, from one read of it.

    A hypertable is read as it is; an ordinary table as a conversion would find it.
    """
    try:
        async with session.inspection() as reader:
            if await is_hypertable(reader, schema_name, table_name):
                await read_current(reader, schema_name, table_name)
            else:
                await read_table(reader, schema_name, table_name)
    except ActionRefused as exc:
        return exc.message
    except (AdapterError, ValueError, TimeoutError):
        return _unreadable()
    return None


class DesignHypertable(Action[HypertableDesignParams]):
    name: ClassVar[str] = "timescale_design_hypertable"
    title: ClassVar[str] = N_("Hypertable settings")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "structure"
    feature_requirements: ClassVar[tuple[FeatureCode, ...]] = ("timescaledb",)
    menu_group: ClassVar[str | None] = TIMESCALE_MENU
    params_model = HypertableDesignParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def _target(self, node_id: str | None) -> tuple[SchemaNode, TableNode]:
        schema, node = await user_table(self._catalog, node_id)
        # An ordinary table keeps its ordinary protections; a hypertable's are
        # what refuse generic writes to it, so they are not asked of one.
        if node.specialization is None:
            reason = await self._catalog.relation_action_reason(schema.name, node.name)
            if reason is not None:
                raise ActionRefused("not_applicable", reason)
        return schema, node

    async def state(self, node_id: str) -> HypertableDesignState:
        try:
            schema, node = await self._target(node_id)
        except ActionRefused as exc:
            return HypertableDesignState(node_id=node_id, reason=exc.message)
        return await design_state(self._session, node_id, schema.name, node.name)

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        params = self._validated(raw)
        schema, node = await self._target(node_id)
        return await preview_design(self._session, schema.name, node.name, params.design)

    async def perform(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionResult:
        raise ActionRefused("conflict", say("Review the hypertable plan before applying it"))

    async def perform_reviewed(
        self, node_id: str | None, raw: Mapping[str, Any], fingerprint: str,
    ) -> ActionResult:
        params = self._validated(raw)
        schema, node = await self._target(node_id)
        async with self._session.inspection() as reader:
            reviewed = await plan_design(reader, schema.name, node.name, params.design)
        if reviewed.migrates:
            raise ActionRefused("conflict", say("Moving rows into chunks runs as a job; start it from the plan"))
        plan = await execute_design(self._session, schema.name, node.name, params.design, fingerprint)
        count = len(plan.steps)
        converts = any(isinstance(step, ConvertTable) for step in plan.steps)
        return ActionResult(
            message=(
                say("Converted to a hypertable") if converts
                else say("Hypertable changed: 1 change applied") if count == 1
                else say("Hypertable changed: {count} changes applied", count=count)
            ),
            reload_node_ids=[schema.id, node.id, TIMESCALE_SECTION_ID],
        )

    async def plan_job(
        self, node_id: str | None, raw: Mapping[str, Any], reviewed_fingerprint: str,
    ) -> OperationPlan:
        """A conversion that moves rows: one unit, the whole design in its transaction (D207)."""
        params = self._validated(raw)
        schema, node = await self._target(node_id)
        async with self._session.inspection() as reader:
            plan = await plan_design(reader, schema.name, node.name, params.design)
        plan.require_unchanged(reviewed_fingerprint)
        if not plan.migrates:
            raise ActionRefused("conflict", say("This change is applied at once rather than as a job"))
        target = sql.Identifier(schema.name, node.name).as_string()
        return OperationPlan(
            summary=say("Convert {target} into a hypertable", target=target),
            unit_fingerprint=plan.fingerprint(),
            targets=(OperationTarget(schema_name=schema.name, name=node.name),),
        )

    async def run_unit(
        self, node_id: str | None, raw: Mapping[str, Any], unit_fingerprint: str,
        target: OperationTarget,
    ) -> UnitOutcome:
        params = self._validated(raw)
        try:
            schema, node = await self._target(node_id)
        except (AdapterError, NodeNotFound):
            raise ActionRefused("not_applicable", say("The table could not be found; nothing was converted")) from None
        if (schema.name, node.name) != (target.schema_name, target.name):
            raise ActionRefused("conflict", say("The table was renamed after review; nothing was converted"))
        await execute_design_job(self._session, schema.name, node.name, params.design, unit_fingerprint)
        return "completed"

    async def observe(
        self, node_id: str | None, raw: Mapping[str, Any], targets: Sequence[OperationTarget],
    ) -> list[ObservedState]:
        self._validated(raw)
        states: list[ObservedState] = []
        async with self._session.inspection() as reader:
            for target in targets:
                exists = await reader.query(_EXISTS, (target.schema_name, target.name), inspection=True)
                if not exists:
                    states.append("gone")
                elif await is_hypertable(reader, target.schema_name, target.name):
                    states.append("as_requested")
                else:
                    states.append("unchanged")
        return states
