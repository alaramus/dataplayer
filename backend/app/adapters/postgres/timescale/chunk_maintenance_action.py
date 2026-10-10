"""Chunk maintenance as reviewed jobs over a fixed set of chunks (D208, D123)."""

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar, Self

from psycopg import sql
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.adapters.actions import Action, ActionPreview, ActionRefused, ActsOn
from app.adapters.catalog import NodeKind
from app.adapters.features import FeatureCode
from app.adapters.operations import (
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
    Maintenance,
    MaintenanceArguments,
    MaintenancePlan,
    MaintenanceUnit,
    chunk_holds,
    inspect_unit,
    ordering_index,
    plan_attach,
    plan_split,
    plan_window_maintenance,
    window_count,
)
from app.adapters.postgres.timescale.chunk_storage_action import (
    LISTED_CHUNKS,
    ChunkWindowParams,
)
from app.adapters.postgres.timescale.names import TIMESCALE_MENU
from app.adapters.postgres.timescale.targets import user_table
from app.adapters.protocol import AdapterError, NodeNotFound
from app.core.access import Access

_UNREADABLE = "TimescaleDB chunk metadata could not be inspected safely"
_JOB = "Runs in Activity, one such job per connection at a time; access is checked again before every unit"


class MoveParams(ChunkWindowParams):
    tablespace: str = Field(
        min_length=1, max_length=63, title="Tablespace",
        description="An existing tablespace this connection may create in",
    )
    index: str | None = Field(
        default=None, min_length=1, max_length=63, title="Order rows by index",
        description="Leave empty for the index on the time column",
    )
    index_tablespace: str | None = Field(
        default=None, min_length=1, max_length=63, title="Index tablespace",
        description="Leave empty to move the indexes with the chunk",
    )


class ReorderParams(ChunkWindowParams):
    index: str = Field(
        min_length=1, max_length=63, title="Index", description="An index of this hypertable to order rows by",
    )


class SplitParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at: AwareDatetime = Field(
        title="Split at", description="With its time zone; the chunk holding this instant is split at it",
        examples=["2026-01-15T12:00:00Z"],
    )


class AttachParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table_schema: str = Field(min_length=1, max_length=63, title="Schema of the table")
    table_name: str = Field(
        min_length=1, max_length=63, title="Table",
        description="A table with the hypertable's columns, such as a detached chunk",
    )
    starts_from: AwareDatetime = Field(title="Covering from", examples=["2026-01-01T00:00:00Z"])
    ends_by: AwareDatetime = Field(title="Until", examples=["2026-01-08T00:00:00Z"])

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.starts_from >= self.ends_by:
            raise ValueError("The range must start before it ends")
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
        return dict.fromkeys(operations, _UNREADABLE)
    return reasons


def _chunk(schema_name: str, name: str) -> str:
    return sql.Identifier(schema_name, name).as_string()


class MaintainChunks[P: BaseModel](Action[P]):
    """One reviewed job; per chunk for most operations, one unit for the rest."""

    maintenance: ClassVar[Maintenance]
    verb: ClassVar[str]
    # What the operation does to the rows, said in the preview before it is reviewed.
    impact: ClassVar[str]
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "structure"
    feature_requirements: ClassVar[tuple[FeatureCode, ...]] = ("timescaledb",)
    menu_group: ClassVar[str | None] = TIMESCALE_MENU

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog

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
            return ActionPreview(summary=_UNREADABLE, blocked=True)
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
            raise ActionRefused("not_applicable", "The hypertable could not be found; nothing was changed") from None

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
        return f"{self.verb} {count} {'chunk' if count == 1 else 'chunks'} of {target} as a job"

    def _items(self, plan: MaintenancePlan) -> list[str]:
        items: list[str] = []
        if plan.window is not None:
            window = plan.window
            start = "the earliest chunk" if window.starts_from is None else window.starts_from.isoformat()
            items.append(f"Whole chunks from {start} to {window.ends_by.isoformat()}")
        items.extend(
            f"{_chunk(chunk.schema_name, chunk.name)}: {chunk.range_start} to {chunk.range_end}"
            for chunk in plan.chunks[:LISTED_CHUNKS]
        )
        if len(plan.chunks) > LISTED_CHUNKS:
            items.append(f"…and {len(plan.chunks) - LISTED_CHUNKS} more")
        if plan.skipped:
            items.append(f"Left as they are, {plan.skipped_because}: {plan.skipped}")
        items.extend((self.impact, _JOB))
        return items


class WindowMaintenance[W: ChunkWindowParams](MaintainChunks[W]):
    def _arguments(self, params: W) -> MaintenanceArguments:
        return MaintenanceArguments()

    async def _plan_with(
        self, reader: PostgresReader, schema_name: str, table_name: str, params: W,
    ) -> MaintenancePlan:
        return await plan_window_maintenance(
            reader, schema_name, table_name, self.maintenance, params.window(), self._arguments(params),
        )

    async def _reviewed_unit(
        self, reader: PostgresReader, schema_name: str, table_name: str, params: W,
    ) -> MaintenanceUnit:
        if self.maintenance == "merge":
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


class DropChunks(WindowMaintenance[ChunkWindowParams]):
    params_model = ChunkWindowParams
    name: ClassVar[str] = "timescale_drop_chunks"
    title: ClassVar[str] = "Drop chunks"
    maintenance: ClassVar[Maintenance] = "drop"
    verb: ClassVar[str] = "Drop"
    destructive: ClassVar[bool] = True
    question: ClassVar[str | None] = "Drop these chunks and every row in them? This cannot be undone."
    impact: ClassVar[str] = (
        "Every row in these chunks is deleted; each chunk is dropped by name, never by an age read when the job runs"
    )


class DetachChunks(WindowMaintenance[ChunkWindowParams]):
    params_model = ChunkWindowParams
    name: ClassVar[str] = "timescale_detach_chunks"
    title: ClassVar[str] = "Detach chunks"
    maintenance: ClassVar[Maintenance] = "detach"
    verb: ClassVar[str] = "Detach"
    impact: ClassVar[str] = (
        "Each chunk becomes an ordinary table under its own name and leaves the hypertable's queries; "
        "Detached chunks lists it, and Attach chunk brings it back"
    )


class MergeChunks(WindowMaintenance[ChunkWindowParams]):
    params_model = ChunkWindowParams
    name: ClassVar[str] = "timescale_merge_chunks"
    title: ClassVar[str] = "Merge chunks"
    maintenance: ClassVar[Maintenance] = "merge"
    verb: ClassVar[str] = "Merge"
    impact: ClassVar[str] = "The chunks become one, covering their whole range; the table is locked while they merge"

    def _summary(self, plan: MaintenancePlan) -> str:
        target = _chunk(plan.unit.target.schema_name, plan.unit.target.table_name)
        return f"Merge {len(plan.chunks)} chunks of {target} into one as a job"

    async def observe(
        self, node_id: str | None, raw: Mapping[str, Any], targets: Sequence[OperationTarget],
    ) -> list[ObservedState]:
        params = self._validated(raw)
        schema, node = await user_table(self._catalog, node_id)
        async with self._session.inspection() as reader:
            unit = await inspect_unit(reader, schema.name, node.name, self.maintenance)

        async def merged(reader: PostgresReader) -> bool:
            return await window_count(reader, unit.target, params.window()) == 1

        return await observe(self._session, unit, targets, merged)


class MoveChunks(WindowMaintenance[MoveParams]):
    name: ClassVar[str] = "timescale_move_chunks"
    title: ClassVar[str] = "Move chunks to a tablespace"
    maintenance: ClassVar[Maintenance] = "move"
    verb: ClassVar[str] = "Move"
    impact: ClassVar[str] = (
        "Each chunk is copied to the tablespace and the old copy removed; reads and writes to it wait meanwhile"
    )
    params_model = MoveParams

    def _arguments(self, params: MoveParams) -> MaintenanceArguments:
        return MaintenanceArguments(
            tablespace=params.tablespace, index_tablespace=params.index_tablespace, index=params.index,
        )


class ReorderChunks(WindowMaintenance[ReorderParams]):
    name: ClassVar[str] = "timescale_reorder_chunks"
    title: ClassVar[str] = "Reorder chunks by an index"
    maintenance: ClassVar[Maintenance] = "reorder"
    verb: ClassVar[str] = "Reorder"
    impact: ClassVar[str] = (
        "Each chunk is rewritten in the index's order, which speeds reads along it; reads and writes wait meanwhile"
    )
    params_model = ReorderParams

    def _arguments(self, params: ReorderParams) -> MaintenanceArguments:
        return MaintenanceArguments(index=params.index)


class SplitChunk(MaintainChunks[SplitParams]):
    name: ClassVar[str] = "timescale_split_chunk"
    title: ClassVar[str] = "Split a chunk"
    maintenance: ClassVar[Maintenance] = "split"
    verb: ClassVar[str] = "Split"
    impact: ClassVar[str] = "The chunk becomes two, divided at this point; the table is locked while it splits"
    params_model = SplitParams

    async def _plan_with(
        self, reader: PostgresReader, schema_name: str, table_name: str, params: SplitParams,
    ) -> MaintenancePlan:
        return await plan_split(reader, schema_name, table_name, params.at)

    def _summary(self, plan: MaintenancePlan) -> str:
        (chunk,) = plan.chunks
        return f"Split {_chunk(chunk.schema_name, chunk.name)} at {plan.unit.arguments.split_at} as a job"

    async def observe(
        self, node_id: str | None, raw: Mapping[str, Any], targets: Sequence[OperationTarget],
    ) -> list[ObservedState]:
        params = self._validated(raw)
        schema, node = await user_table(self._catalog, node_id)
        async with self._session.inspection() as reader:
            unit = await inspect_unit(reader, schema.name, node.name, self.maintenance)

        async def split(reader: PostgresReader) -> bool:
            # Split, the instant is where two chunks meet rather than inside one.
            return not await chunk_holds(reader, unit.target, params.at)

        return await observe(self._session, unit, targets, split)


class AttachChunk(MaintainChunks[AttachParams]):
    name: ClassVar[str] = "timescale_attach_chunk"
    title: ClassVar[str] = "Attach a table as a chunk"
    maintenance: ClassVar[Maintenance] = "attach"
    verb: ClassVar[str] = "Attach"
    impact: ClassVar[str] = (
        "Its rows join the hypertable's queries; TimescaleDB refuses a table whose columns or rows do not fit"
    )
    params_model = AttachParams

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
        return f"Attach {_chunk(chunk.schema_name, chunk.name)} to {target} as a chunk as a job"


MAINTENANCE_TYPES: tuple[type[MaintainChunks[Any]], ...] = (
    DropChunks, MergeChunks, SplitChunk, MoveChunks, ReorderChunks, DetachChunks, AttachChunk,
)
