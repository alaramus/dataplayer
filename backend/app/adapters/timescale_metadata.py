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
