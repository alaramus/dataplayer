"""Chunk maintenance as reviewed jobs over a fixed set of chunks (D208, D123)."""

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar, Literal, Self

from psycopg import sql
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.adapters.actions import (
    Action,
    ActionPreview,
    ActionRefused,
    ActsOn,
    FieldChoice,
    FieldHints,
)
from app.adapters.catalog import NodeKind
from app.adapters.features import FeatureCode
from app.adapters.operations import (
    MAX_OPERATION_TARGETS,
    ObservedState,
    OperationPlan,
    OperationTarget,
    UnitOutcome,
)
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.inspection import PostgresReader
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.chunk_maintenance_execution import (
    observe,
    run_unit,
)
from app.adapters.postgres.timescale.chunk_maintenance_plan import (
    MERGES,
    Maintenance,
    MaintenanceArguments,
    MaintenancePlan,
    MaintenanceUnit,
    Selection,
    chunk_holds,
    index_names,
    inspect_unit,
    ordering_index,
    picked_left,
    plan_attach,
    plan_split,
    plan_window_maintenance,
    tablespace_names,
    window_count,
)
from app.adapters.postgres.timescale.chunk_storage_action import (
    chunk_lines,
    unreadable_chunks,
)
from app.adapters.postgres.timescale.names import TIMESCALE_MENU
from app.adapters.postgres.timescale.plans import (
    BoundWindow,
    ChunkBound,
    ChunkRef,
    MaintainedHypertable,
    bound_text,
    require_ordered,
)
from app.adapters.postgres.timescale.reports import DETACHED_CHUNKS
from app.adapters.postgres.timescale.targets import maintained_hypertable, user_table
from app.adapters.protocol import AdapterError, NodeNotFound
from app.core.access import Access
from app.core.translation import N_, say

# What a field holding a point of an integer time column adds to its description.
IntegerHint = Literal["plain", "earlier", "split"]


def _job() -> str:
    return say("Runs in Activity, one such job per connection at a time; access is checked again before every unit")


def _integer_hint(target: MaintainedHypertable, hint: IntegerHint) -> str:
    column, column_type = target.column_name, target.column_type
    if hint == "earlier":
        return say(
            'A value of "{column}", the {type} column the hypertable is partitioned by; '
            "leave empty for every earlier chunk",
            column=column, type=column_type,
        )
    if hint == "split":
        return say(
            'A value of "{column}", the {type} column the hypertable is partitioned by; '
            "the chunk holding it is split at it",
            column=column, type=column_type,
        )
    return say('A value of "{column}", the {type} column the hypertable is partitioned by', column=column, type=column_type)


def _choices(names: list[str]) -> list[FieldChoice]:
    return [FieldChoice(value=name, label=name) for name in names]


def _end_is_asked(schema: dict[str, Any]) -> None:
    # Optional only for chunks picked by name, whose form leaves the window out
    # (D209); a form that shows it asks for its end.
    required = schema.setdefault("required", [])
    if "ends_by" not in required:
        required.append("ends_by")


class WindowParams(BaseModel):
    """Whole chunks between two instants, or two values of an integer time column."""

    model_config = ConfigDict(extra="forbid", json_schema_extra=_end_is_asked)

    ends_by: ChunkBound | None = Field(
        default=None,
        title=N_("Chunks ending at or before"),
        description=N_("With its time zone; only chunks lying entirely inside the window are chosen"),
        examples=["2026-01-15T00:00:00Z"],
    )
    starts_from: ChunkBound | None = Field(
        default=None,
        title=N_("and starting at or after"),
        description=N_("Leave empty for every earlier chunk"),
        examples=["2026-01-01T00:00:00Z"],
    )
    # Exactly these chunks instead of a window, picked in the Chunks report (D209).
    chunks: list[ChunkRef] | None = Field(
        default=None, min_length=1, max_length=MAX_OPERATION_TARGETS, json_schema_extra={"x-ui-hidden": True},
    )

    @field_validator("starts_from", "ends_by", "chunks", mode="before")
    @classmethod
    def blank_is_unbounded(cls, value: object) -> object:
        # The form sends a text field somebody emptied, or a hidden one nobody
        # set, as an empty string.
        return None if isinstance(value, str) and not value.strip() else value

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.chunks is not None:
            if self.ends_by is not None or self.starts_from is not None:
                raise ValueError(say("Either a window or picked chunks, not both"))
            return self
        if self.ends_by is None:
            raise ValueError(say("Give where the window ends"))
        if self.starts_from is not None:
            require_ordered(self.starts_from, self.ends_by)
        return self

    def selection(self) -> Selection:
        if self.chunks is not None:
            return tuple(self.chunks)
        if self.ends_by is None:
            raise AssertionError("validated: a window has its end")
        return BoundWindow(ends_by=self.ends_by, starts_from=self.starts_from)


class MoveParams(WindowParams):
    tablespace: str = Field(
        min_length=1, max_length=63, title=N_("Tablespace"),
        description=N_("An existing tablespace this connection may create in"),
    )
    index: str | None = Field(
        default=None, min_length=1, max_length=63, title=N_("Order rows by index"),
        description=N_("Leave empty for the index on the time column"),
    )

    @field_validator("index_tablespace", "index", mode="before")
    @classmethod
    def blank_is_unset(cls, value: object) -> object:
        # A choice of "the default" travels as an empty string.
        return None if isinstance(value, str) and not value.strip() else value
    index_tablespace: str | None = Field(
        default=None, min_length=1, max_length=63, title=N_("Index tablespace"),
        description=N_("Leave empty to move the indexes with the chunk"),
    )


class ReorderParams(WindowParams):
    index: str = Field(
        min_length=1, max_length=63, title=N_("Index"), description=N_("An index of this hypertable to order rows by"),
    )


class SplitParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at: ChunkBound = Field(
        title=N_("Split at"), description=N_("With its time zone; the chunk holding this instant is split at it"),
        examples=["2026-01-15T12:00:00Z"],
    )


class AttachParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table_schema: str = Field(min_length=1, max_length=63, title=N_("Schema of the table"))
    table_name: str = Field(
        min_length=1, max_length=63, title=N_("Table"),
        description=N_("A table with the hypertable's columns, such as a detached chunk"),
    )
    starts_from: ChunkBound = Field(title=N_("Covering from"), examples=["2026-01-01T00:00:00Z"])
    ends_by: ChunkBound = Field(title=N_("Until"), examples=["2026-01-08T00:00:00Z"])

    @model_validator(mode="after")
    def ordered(self) -> Self:
        require_ordered(self.starts_from, self.ends_by)
        return self


async def maintenance_admission(
    session: PostgresSession, schema_name: str, table_name: str, operations: Sequence[Maintenance],
) -> dict[Maintenance, str | None]:
    """Why each operation cannot be offered on this hypertable, from one snapshot."""
    reasons: dict[Maintenance, str | None] = {}
    try:
        async with session.inspection() as reader:
            for operation in operations:
                try:
                    await inspect_unit(reader, schema_name, table_name, operation)
                except ActionRefused as exc:
                    reasons[operation] = exc.message
                else:
                    reasons[operation] = None
    except (AdapterError, ValueError, TimeoutError):
        return dict.fromkeys(operations, unreadable_chunks())
    return reasons


def _chunk(schema_name: str, name: str) -> str:
    return sql.Identifier(schema_name, name).as_string()


class MaintainChunks[P: BaseModel](Action[P]):
    """One reviewed job; per chunk for most operations, one unit for the rest."""

    maintenance: ClassVar[Maintenance]
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "structure"
    feature_requirements: ClassVar[tuple[FeatureCode, ...]] = ("timescaledb",)
    menu_group: ClassVar[str | None] = TIMESCALE_MENU
    # The fields holding a point of the time column, with what each adds when
    # that column is an integer one.
    bound_fields: ClassVar[dict[str, IntegerHint]]

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def field_hints(self, node_id: str | None) -> FieldHints:
        schema, node = await user_table(self._catalog, node_id)
        async with self._session.inspection() as reader:
            choices = await self._choices(reader, schema.name, node.name)
            try:
                target = await maintained_hypertable(reader, schema.name, node.name)
            except ActionRefused:
                # The preview says why; the form stays as the schema declares it.
                return FieldHints(choices=choices)
        if not target.integer:
            return FieldHints(choices=choices)
        return FieldHints(
            choices=choices, integers={field: _integer_hint(target, hint) for field, hint in self.bound_fields.items()},
        )

    def impact(self) -> str:
        """What the operation does to the rows, said in the preview before it is reviewed."""
        raise NotImplementedError

    async def _choices(
        self, reader: PostgresReader, schema_name: str, table_name: str,
    ) -> dict[str, list[FieldChoice]]:
        return {}

    async def _plan_with(self, reader: PostgresReader, schema_name: str, table_name: str, params: P) -> MaintenancePlan:
        raise NotImplementedError

    async def _plan(self, node_id: str | None, params: P) -> MaintenancePlan:
        schema, node = await user_table(self._catalog, node_id)
        async with self._session.inspection() as reader:
            return await self._plan_with(reader, schema.name, node.name, params)

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        params = self._validated(raw)
        try:
            plan = await self._plan(node_id, params)
        except ActionRefused as exc:
            return ActionPreview(summary=exc.message, blocked=True)
        except (AdapterError, TimeoutError):
            return ActionPreview(summary=unreadable_chunks(), blocked=True)
        return ActionPreview(summary=self._summary(plan), items=self._items(plan), fingerprint=plan.fingerprint())

    async def plan_job(
        self, node_id: str | None, raw: Mapping[str, Any], reviewed_fingerprint: str,
    ) -> OperationPlan:
        plan = await self._plan(node_id, self._validated(raw))
        plan.require_unchanged(reviewed_fingerprint)
        chunks = plan.chunks[:1] if len(plan.unit.group) else plan.chunks
        return OperationPlan(
            summary=self._summary(plan),
            unit_fingerprint=plan.unit.fingerprint(),
            targets=tuple(OperationTarget(schema_name=chunk.schema_name, name=chunk.name) for chunk in chunks),
        )

    async def _reviewed_unit(self, reader: PostgresReader, schema_name: str, table_name: str, params: P) -> MaintenanceUnit:
        """What a unit is checked against when it runs: the plan's unit, read again."""
        return (await self._plan_with(reader, schema_name, table_name, params)).unit

    async def run_unit(
        self, node_id: str | None, raw: Mapping[str, Any], unit_fingerprint: str, target: OperationTarget,
    ) -> UnitOutcome:
        params = self._validated(raw)
        try:
            schema, node = await user_table(self._catalog, node_id)
        except (AdapterError, NodeNotFound):
            raise ActionRefused("not_applicable", say("The hypertable could not be found; nothing was changed")) from None

        async def reviewed(reader: PostgresReader) -> MaintenanceUnit:
            return await self._reviewed_unit(reader, schema.name, node.name, params)

        return await run_unit(self._session, reviewed, unit_fingerprint, target)

    async def observe(
        self, node_id: str | None, raw: Mapping[str, Any], targets: Sequence[OperationTarget],
    ) -> list[ObservedState]:
        params = self._validated(raw)
        schema, node = await user_table(self._catalog, node_id)
        async with self._session.inspection() as reader:
            unit = await self._observed_unit(reader, schema.name, node.name, params)
        return await observe(self._session, unit, targets)

    async def _observed_unit(
        self, reader: PostgresReader, schema_name: str, table_name: str, params: P,
    ) -> MaintenanceUnit:
        return await inspect_unit(reader, schema_name, table_name, self.maintenance)

    def _summary(self, plan: MaintenancePlan) -> str:
        count = len(plan.chunks)
        target = _chunk(plan.unit.target.schema_name, plan.unit.target.table_name)
        one = count == 1
        match self.maintenance:
            case "drop":
                if one:
                    return say("Drop 1 chunk of {target} as a job", target=target)
                return say("Drop {count} chunks of {target} as a job", count=count, target=target)
            case "move":
                if one:
                    return say("Move 1 chunk of {target} as a job", target=target)
                return say("Move {count} chunks of {target} as a job", count=count, target=target)
            case "reorder":
                if one:
                    return say("Reorder 1 chunk of {target} as a job", target=target)
                return say("Reorder {count} chunks of {target} as a job", count=count, target=target)
            case "detach":
                if one:
                    return say("Detach 1 chunk of {target} as a job", target=target)
                return say("Detach {count} chunks of {target} as a job", count=count, target=target)
        raise AssertionError("an operation without a count of its own says its summary itself")

    def _items(self, plan: MaintenancePlan) -> list[str]:
        items: list[str] = []
        if plan.window is not None:
            window = plan.window
            end = bound_text(window.ends_by)
            items.append(
                say("Whole chunks from the earliest chunk to {end}", end=end) if window.starts_from is None
                else say("Whole chunks from {start} to {end}", start=bound_text(window.starts_from), end=end)
            )
        if plan.picked:
            items.append(say("Exactly the chunks picked in the Chunks report, each read again by name"))
        items.extend(chunk_lines(plan.chunks))
        if plan.skipped:
            items.append(_skipped(plan))
        items.extend((self.impact(), _job()))
        return items


def _skipped(plan: MaintenancePlan) -> str:
    count = plan.skipped
    match plan.skipped_because:
        case "in_tablespace":
            return say(
                "Left as they are, already in {tablespace}: {count}",
                tablespace=sql.Identifier(plan.unit.arguments.tablespace or "").as_string(), count=count,
            )
        case "compressed_reorder":
            return say("Left as they are, compressed, which reorder_chunk does not rewrite: {count}", count=count)
        case "compressed_detach":
            return say(
                "Left as they are, compressed; TimescaleDB detaches only uncompressed chunks: {count}", count=count,
            )
    return say("Left as they are: {count}", count=count)


class WindowMaintenance[W: WindowParams](MaintainChunks[W]):
    bound_fields: ClassVar[dict[str, IntegerHint]] = {"ends_by": "plain", "starts_from": "earlier"}

    def _arguments(self, params: W) -> MaintenanceArguments:
        return MaintenanceArguments()

    async def _plan_with(
        self, reader: PostgresReader, schema_name: str, table_name: str, params: W,
    ) -> MaintenancePlan:
        return await plan_window_maintenance(
            reader, schema_name, table_name, self.maintenance, params.selection(), self._arguments(params),
        )

    async def _reviewed_unit(
        self, reader: PostgresReader, schema_name: str, table_name: str, params: W,
    ) -> MaintenanceUnit:
        if self.maintenance in MERGES:
            return (await self._plan_with(reader, schema_name, table_name, params)).unit
        # Per chunk: the window's other chunks may be done already, so only what
        # every unit runs with is read again, never the list.
        unit = await inspect_unit(reader, schema_name, table_name, self.maintenance)
        arguments = self._arguments(params)
        if self.maintenance == "move":
            # The index a move orders by was chosen at review when none was named.
            arguments = await ordering_index(reader, unit.target, arguments)
        return unit.model_copy(update={"arguments": arguments})

    async def _observed_unit(
        self, reader: PostgresReader, schema_name: str, table_name: str, params: W,
    ) -> MaintenanceUnit:
        return await self._reviewed_unit(reader, schema_name, table_name, params)


class DropChunks(WindowMaintenance[WindowParams]):
    params_model = WindowParams
    name: ClassVar[str] = "timescale_drop_chunks"
    title: ClassVar[str] = N_("Drop chunks")
    maintenance: ClassVar[Maintenance] = "drop"
    destructive: ClassVar[bool] = True
    question: ClassVar[str | None] = N_("Drop these chunks and every row in them? This cannot be undone.")

    def impact(self) -> str:
        return say(
            "Every row in these chunks is deleted; each chunk is dropped by name, never by an age read when the job runs"
        )


class DetachChunks(WindowMaintenance[WindowParams]):
    params_model = WindowParams
    name: ClassVar[str] = "timescale_detach_chunks"
    title: ClassVar[str] = N_("Detach chunks")
    maintenance: ClassVar[Maintenance] = "detach"

    def impact(self) -> str:
        return say(
            "Each chunk becomes an ordinary table under its own name and leaves the hypertable's queries; "
            "Detached chunks lists it, and Attach chunk brings it back"
        )


class MergeChunks(WindowMaintenance[WindowParams]):
    params_model = WindowParams
    name: ClassVar[str] = "timescale_merge_chunks"
    title: ClassVar[str] = N_("Merge chunks")
    maintenance: ClassVar[Maintenance] = "merge"

    def impact(self) -> str:
        return say("The chunks become one, covering their whole range; the table is locked while they merge")

    def _summary(self, plan: MaintenancePlan) -> str:
        target = _chunk(plan.unit.target.schema_name, plan.unit.target.table_name)
        return say("Merge {count} chunks of {target} into one as a job", count=len(plan.chunks), target=target)

    async def observe(
        self, node_id: str | None, raw: Mapping[str, Any], targets: Sequence[OperationTarget],
    ) -> list[ObservedState]:
        params = self._validated(raw)
        schema, node = await user_table(self._catalog, node_id)
        async with self._session.inspection() as reader:
            unit = await inspect_unit(reader, schema.name, node.name, self.maintenance)

        selection = params.selection()

        async def merged(reader: PostgresReader) -> bool:
            # Merged, one of the chunks is left covering them all.
            if isinstance(selection, BoundWindow):
                return await window_count(reader, unit.target, selection) == 1
            return await picked_left(reader, unit.target, selection) == 1

        return await observe(self._session, unit, targets, merged)


class MergeChunksConcurrently(MergeChunks):
    name: ClassVar[str] = "timescale_merge_chunks_concurrently"
    title: ClassVar[str] = N_("Merge chunks, reads going on")
    maintenance: ClassVar[Maintenance] = "merge_concurrently"

    def impact(self) -> str:
        return say("The chunks become one, covering their whole range; reads go on meanwhile, writes to them wait")


class MoveChunks(WindowMaintenance[MoveParams]):
    name: ClassVar[str] = "timescale_move_chunks"
    title: ClassVar[str] = N_("Move chunks to a tablespace")
    maintenance: ClassVar[Maintenance] = "move"
    params_model = MoveParams

    def impact(self) -> str:
        return say(
            "Each chunk is copied to the tablespace and the old copy removed; reads and writes to it wait meanwhile"
        )

    async def _choices(
        self, reader: PostgresReader, schema_name: str, table_name: str,
    ) -> dict[str, list[FieldChoice]]:
        spaces = await tablespace_names(reader)
        indexes = await index_names(reader, schema_name, table_name)
        return {
            "tablespace": _choices(spaces),
            "index_tablespace": [FieldChoice(value="", label=say("With the chunk")), *_choices(spaces)],
            "index": [FieldChoice(value="", label=say("The index on the time column")), *_choices(indexes)],
        }

    def _arguments(self, params: MoveParams) -> MaintenanceArguments:
        return MaintenanceArguments(
            tablespace=params.tablespace, index_tablespace=params.index_tablespace, index=params.index,
        )


class ReorderChunks(WindowMaintenance[ReorderParams]):
    name: ClassVar[str] = "timescale_reorder_chunks"
    title: ClassVar[str] = N_("Reorder chunks by an index")
    maintenance: ClassVar[Maintenance] = "reorder"
    params_model = ReorderParams

    def impact(self) -> str:
        return say(
            "Each chunk is rewritten in the index's order, which speeds reads along it; reads and writes wait meanwhile"
        )

    async def _choices(
        self, reader: PostgresReader, schema_name: str, table_name: str,
    ) -> dict[str, list[FieldChoice]]:
        return {"index": _choices(await index_names(reader, schema_name, table_name))}

    def _arguments(self, params: ReorderParams) -> MaintenanceArguments:
        return MaintenanceArguments(index=params.index)


class SplitChunk(MaintainChunks[SplitParams]):
    name: ClassVar[str] = "timescale_split_chunk"
    title: ClassVar[str] = N_("Split a chunk")
    maintenance: ClassVar[Maintenance] = "split"
    params_model = SplitParams
    bound_fields: ClassVar[dict[str, IntegerHint]] = {"at": "split"}

    def impact(self) -> str:
        return say("The chunk becomes two, divided at this point; the table is locked while it splits")

    async def _plan_with(
        self, reader: PostgresReader, schema_name: str, table_name: str, params: SplitParams,
    ) -> MaintenancePlan:
        return await plan_split(reader, schema_name, table_name, params.at)

    def _summary(self, plan: MaintenancePlan) -> str:
        (chunk,) = plan.chunks
        return say(
            "Split {chunk} at {point} as a job",
            chunk=_chunk(chunk.schema_name, chunk.name), point=plan.unit.arguments.split_at,
        )

    async def observe(
        self, node_id: str | None, raw: Mapping[str, Any], targets: Sequence[OperationTarget],
    ) -> list[ObservedState]:
        params = self._validated(raw)
        schema, node = await user_table(self._catalog, node_id)
        async with self._session.inspection() as reader:
            unit = await inspect_unit(reader, schema.name, node.name, self.maintenance)

        async def split(reader: PostgresReader) -> bool:
            # Split, the point is where two chunks meet rather than inside one.
            return not await chunk_holds(reader, unit.target, params.at)

        return await observe(self._session, unit, targets, split)


class AttachChunk(MaintainChunks[AttachParams]):
    name: ClassVar[str] = "timescale_attach_chunk"
    title: ClassVar[str] = N_("Attach a table as a chunk")
    maintenance: ClassVar[Maintenance] = "attach"
    params_model = AttachParams
    bound_fields: ClassVar[dict[str, IntegerHint]] = {"starts_from": "plain", "ends_by": "plain"}

    def impact(self) -> str:
        return say(
            "Its rows join the hypertable's queries; TimescaleDB refuses a table whose columns or rows do not fit"
        )

    async def _plan_with(
        self, reader: PostgresReader, schema_name: str, table_name: str, params: AttachParams,
    ) -> MaintenancePlan:
        return await plan_attach(
            reader, schema_name, table_name, params.table_schema, params.table_name,
            params.starts_from, params.ends_by,
        )

    def _summary(self, plan: MaintenancePlan) -> str:
        (chunk,) = plan.chunks
        target = _chunk(plan.unit.target.schema_name, plan.unit.target.table_name)
        return say(
            "Attach {table} to {target} as a chunk as a job", table=_chunk(chunk.schema_name, chunk.name), target=target,
        )

    async def _choices(
        self, reader: PostgresReader, schema_name: str, table_name: str,
    ) -> dict[str, list[FieldChoice]]:
        """The tables the Detached chunks report lists: the likeliest ones, never the only ones."""
        rows = await reader.query(DETACHED_CHUNKS.statement.as_string(), inspection=True)
        schemas = sorted({str(row["table_schema"]) for row in rows})
        return {
            "table_schema": _choices(schemas),
            "table_name": [
                FieldChoice(value=str(row["table_name"]), label=f'{row["table_name"]} ({row["table_schema"]})')
                for row in rows
            ],
        }


MAINTENANCE_TYPES: tuple[type[MaintainChunks[Any]], ...] = (
    DropChunks, MergeChunks, MergeChunksConcurrently, SplitChunk, MoveChunks, ReorderChunks, DetachChunks,
    AttachChunk,
)
