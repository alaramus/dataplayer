"""Typed read-only plans; a fingerprint detects change, never grants access (D123)."""

import hashlib
import hmac
import json
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.adapters.actions import ActionRefused
from app.adapters.operations import MAX_OPERATION_TARGETS

_OID = r"^[1-9][0-9]{0,9}$"


class TimeDuration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    amount: int = Field(strict=True, gt=0, le=2_147_483_647)
    unit: Literal["second", "minute", "hour", "day", "week", "month", "year"]

    def interval_value(self) -> str:
        return f"{self.amount} {self.unit}"


class IntervalTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    database_oid: str = Field(pattern=r"^[1-9][0-9]{0,9}$")
    relation_oid: str = Field(pattern=r"^[1-9][0-9]{0,9}$")
    schema_name: str = Field(min_length=1, max_length=63)
    table_name: str = Field(min_length=1, max_length=63)
    dimension_number: int = Field(strict=True, gt=0)
    column_name: str = Field(min_length=1, max_length=63)
    column_type: Literal["timestamp without time zone", "timestamp with time zone", "date"]
    current_interval: str = Field(min_length=1, max_length=100)


class IntervalStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal["set_chunk_time_interval_public_view_lock_v1"] = "set_chunk_time_interval_public_view_lock_v1"
    extension_version: Literal["2.17.2", "2.18.0"]
    function_oid: str = Field(pattern=r"^[1-9][0-9]{0,9}$")
    function_schema: str = Field(min_length=1, max_length=63)
    dimensions_view_oid: str = Field(pattern=r"^[1-9][0-9]{0,9}$")


class ReviewedPlan(BaseModel):
    """Compared as the SHA-256 of its whole canonical JSON, every field included."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    def fingerprint(self) -> str:
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def require_unchanged(self, reviewed_fingerprint: str) -> None:
        if (
            len(reviewed_fingerprint) != 64
            or any(char not in "0123456789abcdef" for char in reviewed_fingerprint)
            or not hmac.compare_digest(self.fingerprint(), reviewed_fingerprint)
        ):
            raise ActionRefused("conflict", "The operation plan changed; review it again")


class ChunkIntervalPlan(ReviewedPlan):
    operation: Literal["set_chunk_interval"] = "set_chunk_interval"
    target: IntervalTarget
    interval: TimeDuration
    strategy: IntervalStrategy
    impact: Literal["Only future chunks use the new interval; existing chunks are not repartitioned"] = (
        "Only future chunks use the new interval; existing chunks are not repartitioned"
    )
    coordination: Literal[
        "Briefly locks TimescaleDB metadata across this database; new chunk creation may wait"
    ] = "Briefly locks TimescaleDB metadata across this database; new chunk creation may wait"


class TimeHypertable(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    database_oid: str = Field(pattern=_OID)
    relation_oid: str = Field(pattern=_OID)
    schema_name: str = Field(min_length=1, max_length=63)
    table_name: str = Field(min_length=1, max_length=63)
    column_name: str = Field(min_length=1, max_length=63)
    column_type: Literal["timestamp without time zone", "timestamp with time zone", "date"]


AgePolicyKind = Literal["retention", "compression"]


class AgePolicy(BaseModel):
    """A native job acting on chunks past one age threshold."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(pattern=_OID)
    scheduled: bool = Field(strict=True)
    schedule_interval: str = Field(min_length=1, max_length=100)
    older_than: str | None = Field(default=None, min_length=1, max_length=100)
    created_before: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def one_threshold(self) -> Self:
        if (self.older_than is None) == (self.created_before is None):
            raise ValueError("A policy has exactly one readable threshold")
        return self

    def threshold(self) -> str:
        if self.older_than is not None:
            return f"older than {self.older_than}"
        return f"created more than {self.created_before} ago"


class AgePolicyStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal["age_policy_public_jobs_lock_v1"] = "age_policy_public_jobs_lock_v1"
    kind: AgePolicyKind
    extension_version: Literal["2.17.2", "2.18.0"]
    function_schema: str = Field(min_length=1, max_length=63)
    add_function_oid: str = Field(pattern=_OID)
    remove_function_oid: str = Field(pattern=_OID)
    jobs_view_oid: str = Field(pattern=_OID)


_IMPACT: dict[tuple[AgePolicyKind, bool], str] = {
    ("retention", True): (
        "TimescaleDB keeps dropping whole chunks older than this on its own schedule, "
        "after this session ends"
    ),
    ("retention", False): (
        "TimescaleDB stops dropping old chunks automatically; chunks already dropped do not return"
    ),
    ("compression", True): (
        "TimescaleDB keeps compressing chunks older than this on its own schedule; "
        "compressed chunks stay readable"
    ),
    ("compression", False): (
        "TimescaleDB stops compressing chunks automatically; chunks already compressed stay compressed"
    ),
}


class AgePolicyPlan(ReviewedPlan):
    operation: Literal["set_policy", "remove_policy"]
    kind: AgePolicyKind
    target: TimeHypertable
    existing: AgePolicy | None
    older_than: TimeDuration | None
    strategy: AgePolicyStrategy
    coordination: Literal[
        "Briefly locks TimescaleDB job and hypertable metadata across this database; "
        "policy runs and new chunk creation may wait"
    ] = (
        "Briefly locks TimescaleDB job and hypertable metadata across this database; "
        "policy runs and new chunk creation may wait"
    )

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.operation == "set_policy":
            consistent = self.older_than is not None
        else:
            consistent = self.older_than is None and self.existing is not None
        if not consistent or self.strategy.kind != self.kind:
            raise ValueError("The policy operation does not match its parameters")
        return self

    @property
    def impact(self) -> str:
        return _IMPACT[self.kind, self.operation == "set_policy"]


class ContinuousAggregateTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    database_oid: str = Field(pattern=_OID)
    view_oid: str = Field(pattern=_OID)
    view_schema: str = Field(min_length=1, max_length=63)
    view_name: str = Field(min_length=1, max_length=63)
    materialization_oid: str = Field(pattern=_OID)
    materialization_schema: str = Field(min_length=1, max_length=63)
    materialization_name: str = Field(min_length=1, max_length=63)
    source_schema: str = Field(min_length=1, max_length=63)
    source_name: str = Field(min_length=1, max_length=63)
    column_type: Literal["timestamp without time zone", "timestamp with time zone", "date"]


class RefreshPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(pattern=_OID)
    scheduled: bool = Field(strict=True)
    schedule_interval: str = Field(min_length=1, max_length=100)
    # None is an unbounded edge of the window, as the source means it.
    start_offset: str | None = Field(default=None, min_length=1, max_length=100)
    end_offset: str | None = Field(default=None, min_length=1, max_length=100)

    def window(self) -> str:
        start = "the earliest data" if self.start_offset is None else f"{self.start_offset} ago"
        end = "the latest data" if self.end_offset is None else f"{self.end_offset} ago"
        return f"from {start} to {end}"


class RefreshWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start_offset: TimeDuration
    end_offset: TimeDuration
    schedule_interval: TimeDuration


class RefreshStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal["refresh_policy_public_jobs_lock_v1"] = "refresh_policy_public_jobs_lock_v1"
    extension_version: Literal["2.17.2", "2.18.0"]
    function_schema: str = Field(min_length=1, max_length=63)
    add_function_oid: str = Field(pattern=_OID)
    remove_function_oid: str = Field(pattern=_OID)
    jobs_view_oid: str = Field(pattern=_OID)


class RefreshPlan(ReviewedPlan):
    operation: Literal["set_policy", "remove_policy"]
    target: ContinuousAggregateTarget
    existing: RefreshPolicy | None
    window: RefreshWindow | None
    # The source hypertable's retention policy the window was checked against.
    source_retention: AgePolicy | None
    strategy: RefreshStrategy
    coordination: Literal[
        "Briefly locks TimescaleDB job and hypertable metadata across this database; "
        "policy runs and new chunk creation may wait"
    ] = (
        "Briefly locks TimescaleDB job and hypertable metadata across this database; "
        "policy runs and new chunk creation may wait"
    )

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.operation == "set_policy":
            consistent = self.window is not None
        else:
            consistent = self.window is None and self.existing is not None
        if not consistent:
            raise ValueError("The refresh operation does not match its parameters")
        return self

    @property
    def impact(self) -> str:
        if self.operation == "remove_policy":
            return "TimescaleDB stops refreshing this aggregate automatically; its materialized rows stay as they are"
        return "TimescaleDB keeps refreshing this window on its own schedule, after this session ends"


class OrderColumn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    column: str = Field(min_length=1, max_length=63)
    descending: bool = Field(strict=True)
    nulls_first: bool = Field(strict=True)


class CompressionSettingsStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal["compression_settings_alter_table_v1"] = "compression_settings_alter_table_v1"
    extension_version: Literal["2.17.2", "2.18.0"]


class CompressionSettingsPlan(ReviewedPlan):
    operation: Literal["configure_compression"] = "configure_compression"
    target: TimeHypertable
    enabled: bool = Field(strict=True)
    # As the public settings view renders them; None when compression was never configured.
    current_segment_by: str | None = Field(max_length=8192)
    current_order_by: str | None = Field(max_length=8192)
    segment_by: tuple[str, ...] = Field(max_length=32)
    # What the source will hold: the requested order with the time column appended if unnamed.
    order_by: tuple[OrderColumn, ...] = Field(max_length=33)
    any_compressed: bool = Field(strict=True)
    # Unique-key columns in neither list, which the source warns about on first enabling.
    unsegmented_unique: tuple[str, ...] = Field(max_length=1600)
    strategy: CompressionSettingsStrategy
    coordination: Literal[
        "Locks this hypertable exclusively while the settings change; its reads and writes wait until it commits"
    ] = "Locks this hypertable exclusively while the settings change; its reads and writes wait until it commits"

    @property
    def impact(self) -> str:
        if not self.enabled:
            return "Nothing is compressed now; chunks are compressed later by a compression policy or on request"
        return "Only chunks compressed from now on use these settings; already compressed chunks keep theirs"


class ConversionTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    database_oid: str = Field(pattern=_OID)
    relation_oid: str = Field(pattern=_OID)
    schema_name: str = Field(min_length=1, max_length=63)
    table_name: str = Field(min_length=1, max_length=63)


class ConversionColumn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=63)
    type: Literal["timestamp without time zone", "timestamp with time zone", "date"]
    not_null: bool = Field(strict=True)


class ConversionStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal["create_hypertable_by_range_empty_v1"] = "create_hypertable_by_range_empty_v1"
    extension_version: Literal["2.17.2", "2.18.0"]
    function_schema: str = Field(min_length=1, max_length=63)
    create_function_oid: str = Field(pattern=_OID)
    by_range_function_oid: str = Field(pattern=_OID)
    dimension_info_oid: str = Field(pattern=_OID)


class ConversionPlan(ReviewedPlan):
    operation: Literal["convert_empty_table"] = "convert_empty_table"
    target: ConversionTarget
    column: ConversionColumn
    interval: TimeDuration
    # A one-column index on the time column, the only existing index the source counts.
    time_index_exists: bool = Field(strict=True)
    strategy: ConversionStrategy
    impact: Literal[
        "The table keeps its name and identity and becomes a hypertable; "
        "DataPlayer cannot turn it back into an ordinary table"
    ] = (
        "The table keeps its name and identity and becomes a hypertable; "
        "DataPlayer cannot turn it back into an ordinary table"
    )
    coordination: Literal[
        "Locks this table exclusively for the conversion; its reads and writes wait until it commits"
    ] = "Locks this table exclusively for the conversion; its reads and writes wait until it commits"


ChunkStorage = Literal["columnstore", "rowstore"]


class ChunkStorageStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal["chunk_storage_per_chunk_v1"] = "chunk_storage_per_chunk_v1"
    storage: ChunkStorage
    extension_version: Literal["2.17.2", "2.18.0"]
    function_schema: str = Field(min_length=1, max_length=63)
    function_oid: str = Field(pattern=_OID)


class ChunkStorageUnit(ReviewedPlan):
    """What every chunk of an admitted job is checked against before it is converted."""

    operation: Literal["convert_chunks"] = "convert_chunks"
    target: TimeHypertable
    strategy: ChunkStorageStrategy


class ChunkWindow(BaseModel):
    """Whole chunks ending by one instant, optionally starting from another."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ends_by: AwareDatetime
    starts_from: AwareDatetime | None = None


class PlannedChunk(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_name: str = Field(min_length=1, max_length=63)
    name: str = Field(min_length=1, max_length=63)
    # Source text in the session's time zone, shown in the preview and nowhere else.
    range_start: str = Field(min_length=1, max_length=100)
    range_end: str = Field(min_length=1, max_length=100)


_STORAGE_IMPACT: dict[ChunkStorage, str] = {
    "columnstore": (
        "Compressed chunks stay readable; queries and writes touching a chunk may wait while it is rewritten"
    ),
    "rowstore": (
        "Decompressed chunks take more space; a compression policy may compress them again on its own schedule"
    ),
}


class ChunkStoragePlan(ReviewedPlan):
    unit: ChunkStorageUnit
    window: ChunkWindow
    # Whole chunks inside the window not yet stored as requested, in time order.
    chunks: tuple[PlannedChunk, ...] = Field(min_length=1, max_length=MAX_OPERATION_TARGETS)
    # Chunks inside the window already stored as requested, left as they are.
    already: int = Field(strict=True, ge=0)
    coordination: Literal[
        "Each chunk is converted in its own transaction; cancelling keeps the chunks already converted"
    ] = "Each chunk is converted in its own transaction; cancelling keeps the chunks already converted"

    @property
    def impact(self) -> str:
        return _STORAGE_IMPACT[self.unit.strategy.storage]
