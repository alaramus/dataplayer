"""Bounded optional Timescale facts for relation Details (D121)."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class HypertableFacts(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: Literal["hypertable"] = "hypertable"
    num_dimensions: int = Field(ge=1, le=32767)
    num_chunks: str = Field(pattern=r"^(0|[1-9][0-9]*)$", max_length=19)
    compression_enabled: bool


class ContinuousAggregateFacts(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: Literal["continuous_aggregate"] = "continuous_aggregate"
    hypertable_schema: str = Field(min_length=1, max_length=63)
    hypertable_name: str = Field(min_length=1, max_length=63)
    materialization_hypertable_schema: str = Field(min_length=1, max_length=63)
    materialization_hypertable_name: str = Field(min_length=1, max_length=63)
    materialized_only: bool
    compression_enabled: bool


class UnavailableTimescaleFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["unavailable"] = "unavailable"
    reason: str = Field(min_length=1, max_length=500)


TimescaleFacts = Annotated[
    HypertableFacts | ContinuousAggregateFacts | UnavailableTimescaleFacts,
    Field(discriminator="kind"),
]


DecimalCount = Annotated[str, Field(pattern=r"^(0|[1-9][0-9]*)$", max_length=19)]


class TimescaleSize(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: Literal["size"] = "size"
    table_bytes: DecimalCount
    index_bytes: DecimalCount
    toast_bytes: DecimalCount
    total_bytes: DecimalCount


class TimescaleCompression(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: Literal["compression"] = "compression"
    total_chunks: DecimalCount
    number_compressed_chunks: DecimalCount
    before_compression_table_bytes: DecimalCount | None
    before_compression_index_bytes: DecimalCount | None
    before_compression_toast_bytes: DecimalCount | None
    before_compression_total_bytes: DecimalCount | None
    after_compression_table_bytes: DecimalCount | None
    after_compression_index_bytes: DecimalCount | None
    after_compression_toast_bytes: DecimalCount | None
    after_compression_total_bytes: DecimalCount | None


class TimescaleStatistics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    size: Annotated[TimescaleSize | UnavailableTimescaleFacts, Field(discriminator="kind")]
    compression: Annotated[
        TimescaleCompression | UnavailableTimescaleFacts, Field(discriminator="kind"),
    ]
