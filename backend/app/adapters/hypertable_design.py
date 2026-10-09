"""What a hypertable should be, as one closed model (D207).

The editor sends the whole design and never a list of steps: the source reads
what the hypertable is now into the same model, and the difference between the
two is the plan. A client that sent steps would be computing that difference
itself, from a picture of the source it read some time ago.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_DESIGN_COLUMNS = 32
MAX_HASH_DIMENSIONS = 8
MAX_TABLESPACES = 32
# by_hash takes a smallint-sized count; Timescale refuses more.
MAX_HASH_PARTITIONS = 32767

DurationUnit = Literal["second", "minute", "hour", "day", "week", "month", "year"]
Name = Annotated[str, Field(min_length=1, max_length=63)]


class DesignDuration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    amount: int = Field(strict=True, gt=0, le=2_147_483_647)
    unit: DurationUnit


class ChosenByTimescale(BaseModel):
    """Leave the setting unset, so Timescale chooses it for each chunk."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["default"] = "default"


class NoColumns(BaseModel):
    """Set explicitly to nothing, which is not the same as leaving it unset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["none"] = "none"


class SegmentColumns(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["columns"] = "columns"
    columns: list[Name] = Field(min_length=1, max_length=MAX_DESIGN_COLUMNS)


class OrderKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    column: Name
    descending: bool = Field(strict=True)
    nulls_first: bool = Field(strict=True)


class OrderColumns(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["columns"] = "columns"
    columns: list[OrderKey] = Field(min_length=1, max_length=MAX_DESIGN_COLUMNS)


# Ordering has no "none": every release refuses an empty order.
SegmentBy = Annotated[ChosenByTimescale | NoColumns | SegmentColumns, Field(discriminator="mode")]
OrderBy = Annotated[ChosenByTimescale | OrderColumns, Field(discriminator="mode")]


class ColumnstoreDesign(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = Field(strict=True)
    segment_by: SegmentBy = Field(default_factory=NoColumns)
    order_by: OrderBy = Field(default_factory=ChosenByTimescale)
    # compress_chunk_time_interval: how much time one compressed chunk may
    # cover. Never the same number as a policy's age, which the old
    # application conflated.
    merge_interval: DesignDuration | None = None


class OlderThan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["older_than"] = "older_than"
    older_than: DesignDuration


class KeptAsItIs(BaseModel):
    """An existing policy this editor cannot represent, left untouched.

    A threshold of "1 day 02:00:00", a creation-time threshold or a paused job
    is the source's, and an editor that rounded it to what its fields can hold
    would change it without being asked.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["current"] = "current"


AgePolicyDesign = Annotated[OlderThan | KeptAsItIs, Field(discriminator="kind")]


class HashDimensionDesign(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    column: Name
    partitions: int = Field(strict=True, gt=0, le=MAX_HASH_PARTITIONS)


class HypertableDesign(BaseModel):
    """Every field is optional for a reader, so an older client still validates."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_interval: DesignDuration | None = None
    hash_dimensions: list[HashDimensionDesign] = Field(
        default_factory=list, max_length=MAX_HASH_DIMENSIONS,
    )
    columnstore: ColumnstoreDesign = Field(
        default_factory=lambda: ColumnstoreDesign(enabled=False),
    )
    retention: AgePolicyDesign | None = None
    columnstore_policy: AgePolicyDesign | None = None
    reorder_index: Name | None = None
    tablespaces: list[Name] = Field(default_factory=list, max_length=MAX_TABLESPACES)

    @model_validator(mode="after")
    def distinct(self) -> Self:
        hashed = [item.column for item in self.hash_dimensions]
        if len(set(hashed)) != len(hashed):
            raise ValueError("A column is hashed at most once")
        if len(set(self.tablespaces)) != len(self.tablespaces):
            raise ValueError("A tablespace is attached at most once")
        return self


class HypertableColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    type: str = Field(min_length=1, max_length=200)
    # Whether it can be a hash dimension, an order key or a segment column,
    # as the source decides; a column without a comparison operator is none.
    orderable: bool


class CurrentPolicy(BaseModel):
    """An existing policy, in the source's words, for what the editor shows."""

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(pattern=r"^[1-9][0-9]{0,9}$")
    description: str = Field(min_length=1, max_length=300)


class HypertableDesignState(BaseModel):
    """What the editor opens with: the design as it is now, and what may change.

    `design` is None exactly when `reason` says why the editor cannot work on
    this table. Units and choices are the server's, because which of them this
    hypertable accepts depends on its column types and on the release.
    """

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(min_length=1, max_length=512)
    reason: str | None = Field(default=None, max_length=500)
    design: HypertableDesign | None = None
    extension_version: str | None = None
    time_column: str | None = None
    time_column_type: str | None = None
    columns: list[HypertableColumn] = Field(default_factory=list)
    indexes: list[Name] = Field(default_factory=list)
    tablespaces: list[Name] = Field(default_factory=list)
    interval_units: list[DurationUnit] = Field(default_factory=list)
    policy_units: list[DurationUnit] = Field(default_factory=list)
    merge_units: list[DurationUnit] = Field(default_factory=list)
    # Whether "Timescale chooses" is a state this release has (D207).
    per_chunk_defaults: bool = False
    has_chunks: bool = False
    compressed_chunks: bool = False
    retention: CurrentPolicy | None = None
    columnstore_policy: CurrentPolicy | None = None
    reorder: CurrentPolicy | None = None

    @model_validator(mode="after")
    def answered(self) -> Self:
        if (self.design is None) == (self.reason is None):
            raise ValueError("A state carries a design or the reason there is none")
        return self


class HypertableDesignTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(min_length=1, max_length=512)
