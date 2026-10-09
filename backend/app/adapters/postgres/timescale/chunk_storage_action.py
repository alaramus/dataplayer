"""Compress or decompress a reviewed, fixed set of whole chunks as an owned job (D123)."""

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar, Self

from psycopg import sql
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

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
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.chunk_storage_execution import (
    convert_chunk,
    observe_chunks,
)
from app.adapters.postgres.timescale.chunk_storage_plan import (
    STORAGES,
    inspect_chunk_unit,
    plan_chunk_storage,
)
from app.adapters.postgres.timescale.names import TIMESCALE_MENU
from app.adapters.postgres.timescale.plans import (
    ChunkStorage,
    ChunkStoragePlan,
    ChunkWindow,
)
from app.adapters.postgres.timescale.targets import user_table
from app.adapters.protocol import AdapterError, NodeNotFound
from app.core.access import Access

# How many chunks the preview names before it counts the rest.
LISTED_CHUNKS = 10
_UNREADABLE = "TimescaleDB chunk metadata could not be inspected safely"


class ChunkWindowParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ends_by: AwareDatetime = Field(
        title="Chunks ending at or before",
        description="With its time zone; only chunks lying entirely inside the window are chosen",
        examples=["2026-01-15T00:00:00Z"],
    )
    starts_from: AwareDatetime | None = Field(
        default=None,
        title="and starting at or after",
        description="Leave empty for every earlier chunk",
        examples=["2026-01-01T00:00:00Z"],
    )

    @field_validator("starts_from", mode="before")
    @classmethod
    def blank_is_unbounded(cls, value: object) -> object:
        # The form sends a text field somebody emptied as an empty string.
        return None if isinstance(value, str) and not value.strip() else value

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.starts_from is not None and self.starts_from >= self.ends_by:
            raise ValueError("The window must start before it ends")
        return self

    def window(self) -> ChunkWindow:
        return ChunkWindow(ends_by=self.ends_by, starts_from=self.starts_from)


async def chunk_storage_admission(
    session: PostgresSession, schema_name: str, table_name: str,
) -> dict[ChunkStorage, str | None]:
    """Why compressing, then decompressing, cannot be offered, from one snapshot."""
    reasons: dict[ChunkStorage, str | None] = {}
    try:
        async with session.inspection() as reader:
            for storage in STORAGES:
                try:
                    await inspect_chunk_unit(reader, schema_name, table_name, storage)
                except ActionRefused as exc:
                    reasons[storage] = exc.message
                else:
                    reasons[storage] = None
    except (AdapterError, ValueError, TimeoutError):
        return dict.fromkeys(STORAGES, _UNREADABLE)
    return reasons


class ConvertChunks(Action[ChunkWindowParams]):
    """Rewrite whole chunks of one time hypertable, one source transaction each."""

    storage: ClassVar[ChunkStorage]
    verb: ClassVar[str]
    # What a chunk already stored as requested is called.
    state: ClassVar[str]
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "structure"
    feature_requirements: ClassVar[tuple[FeatureCode, ...]] = ("timescaledb",)
    menu_group: ClassVar[str | None] = TIMESCALE_MENU
    params_model = ChunkWindowParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        params = self._validated(raw)
        schema, node = await user_table(self._catalog, node_id)
        try:
            plan = await self._plan(schema.name, node.name, params)
        except ActionRefused as exc:
            return ActionPreview(summary=exc.message, blocked=True)
        except (AdapterError, TimeoutError):
            return ActionPreview(summary=_UNREADABLE, blocked=True)
        return ActionPreview(
            summary=self._summary(plan), items=self._items(plan), fingerprint=plan.fingerprint(),
        )

    async def plan_job(
        self, node_id: str | None, raw: Mapping[str, Any], reviewed_fingerprint: str,
    ) -> OperationPlan:
        params = self._validated(raw)
        schema, node = await user_table(self._catalog, node_id)
        plan = await self._plan(schema.name, node.name, params)
        plan.require_unchanged(reviewed_fingerprint)
        return OperationPlan(
            summary=self._summary(plan),
            unit_fingerprint=plan.unit.fingerprint(),
            targets=tuple(
                OperationTarget(schema_name=chunk.schema_name, name=chunk.name)
                for chunk in plan.chunks
            ),
        )

    async def run_unit(
        self, node_id: str | None, raw: Mapping[str, Any], unit_fingerprint: str,
        target: OperationTarget,
    ) -> UnitOutcome:
        self._validated(raw)
        try:
            schema, node = await user_table(self._catalog, node_id)
        except (AdapterError, NodeNotFound):
            raise ActionRefused(
                "not_applicable", "The hypertable could not be found; nothing was converted",
            ) from None
        return await convert_chunk(
            self._session, schema.name, node.name, self.storage, unit_fingerprint, target,
        )

    async def observe(
        self, node_id: str | None, raw: Mapping[str, Any], targets: Sequence[OperationTarget],
    ) -> list[ObservedState]:
        self._validated(raw)
        schema, node = await user_table(self._catalog, node_id)
        return await observe_chunks(self._session, schema.name, node.name, self.storage, targets)

    async def _plan(
        self, schema_name: str, table_name: str, params: ChunkWindowParams,
    ) -> ChunkStoragePlan:
        async with self._session.inspection() as reader:
            return await plan_chunk_storage(
                reader, schema_name, table_name, self.storage, params.window(),
            )

    def _summary(self, plan: ChunkStoragePlan) -> str:
        count = len(plan.chunks)
        target = sql.Identifier(plan.unit.target.schema_name, plan.unit.target.table_name).as_string()
        return f"{self.verb} {count} {'chunk' if count == 1 else 'chunks'} of {target} as a job"

    def _items(self, plan: ChunkStoragePlan) -> list[str]:
        window = plan.window
        start = "the earliest chunk" if window.starts_from is None else window.starts_from.isoformat()
        items = [f"Whole chunks from {start} to {window.ends_by.isoformat()}"]
        items.extend(
            f"{sql.Identifier(chunk.schema_name, chunk.name).as_string()}: "
            f"{chunk.range_start} to {chunk.range_end}"
            for chunk in plan.chunks[:LISTED_CHUNKS]
        )
        if len(plan.chunks) > LISTED_CHUNKS:
            items.append(f"…and {len(plan.chunks) - LISTED_CHUNKS} more")
        if plan.already:
            items.append(f"Already {self.state} and left as they are: {plan.already}")
        items.extend((
            plan.impact,
            plan.coordination,
            "Runs in Activity, one such job per connection at a time; "
            "access is checked again before every chunk",
        ))
        return items


class CompressChunks(ConvertChunks):
    name: ClassVar[str] = "timescale_compress_chunks"
    title: ClassVar[str] = "Compress chunks"
    storage: ClassVar[ChunkStorage] = "columnstore"
    verb: ClassVar[str] = "Compress"
    state: ClassVar[str] = "compressed"


class DecompressChunks(ConvertChunks):
    name: ClassVar[str] = "timescale_decompress_chunks"
    title: ClassVar[str] = "Decompress chunks"
    storage: ClassVar[ChunkStorage] = "rowstore"
    verb: ClassVar[str] = "Decompress"
    state: ClassVar[str] = "decompressed"
