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
    PlannedChunk,
)
from app.adapters.postgres.timescale.targets import user_table
from app.adapters.protocol import AdapterError, NodeNotFound
from app.core.access import Access
from app.core.translation import N_, say

# How many chunks the preview names before it counts the rest.
LISTED_CHUNKS = 10


def unreadable_chunks() -> str:
    return say("TimescaleDB chunk metadata could not be inspected safely")


def chunk_lines(chunks: Sequence[PlannedChunk]) -> list[str]:
    """The first chunks of a plan by name and range, and how many more there are."""
    lines = [
        say(
            "{chunk}: {start} to {end}",
            chunk=sql.Identifier(chunk.schema_name, chunk.name).as_string(),
            start=chunk.range_start, end=chunk.range_end,
        )
        for chunk in chunks[:LISTED_CHUNKS]
    ]
    if len(chunks) > LISTED_CHUNKS:
        lines.append(say("…and {count} more", count=len(chunks) - LISTED_CHUNKS))
    return lines


class ChunkWindowParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ends_by: AwareDatetime = Field(
        title=N_("Chunks ending at or before"),
        description=N_("With its time zone; only chunks lying entirely inside the window are chosen"),
        examples=["2026-01-15T00:00:00Z"],
    )
    starts_from: AwareDatetime | None = Field(
        default=None,
        title=N_("and starting at or after"),
        description=N_("Leave empty for every earlier chunk"),
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
            raise ValueError(say("The window must start before it ends"))
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
        return dict.fromkeys(STORAGES, unreadable_chunks())
    return reasons


class ConvertChunks(Action[ChunkWindowParams]):
    """Rewrite whole chunks of one time hypertable, one source transaction each."""

    storage: ClassVar[ChunkStorage]
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
            return ActionPreview(summary=unreadable_chunks(), blocked=True)
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
                "not_applicable", say("The hypertable could not be found; nothing was converted"),
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
        if self.storage == "columnstore":
            if count == 1:
                return say("Compress 1 chunk of {target} as a job", target=target)
            return say("Compress {count} chunks of {target} as a job", count=count, target=target)
        if count == 1:
            return say("Decompress 1 chunk of {target} as a job", target=target)
        return say("Decompress {count} chunks of {target} as a job", count=count, target=target)

    def _items(self, plan: ChunkStoragePlan) -> list[str]:
        window = plan.window
        end = window.ends_by.isoformat()
        items = [
            say("Whole chunks from the earliest chunk to {end}", end=end) if window.starts_from is None
            else say("Whole chunks from {start} to {end}", start=window.starts_from.isoformat(), end=end)
        ]
        items.extend(chunk_lines(plan.chunks))
        if plan.already:
            items.append(
                say("Already compressed and left as they are: {count}", count=plan.already)
                if self.storage == "columnstore"
                else say("Already decompressed and left as they are: {count}", count=plan.already)
            )
        items.extend((
            plan.impact,
            plan.said_coordination,
            say(
                "Runs in Activity, one such job per connection at a time; "
                "access is checked again before every chunk"
            ),
        ))
        return items


class CompressChunks(ConvertChunks):
    name: ClassVar[str] = "timescale_compress_chunks"
    title: ClassVar[str] = N_("Compress chunks")
    storage: ClassVar[ChunkStorage] = "columnstore"


class DecompressChunks(ConvertChunks):
    name: ClassVar[str] = "timescale_decompress_chunks"
    title: ClassVar[str] = N_("Decompress chunks")
    storage: ClassVar[ChunkStorage] = "rowstore"
