"""Typed specialisations that retain a node's ordinary structural kind (D121)."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class TimescaleHypertable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["timescale_hypertable"] = "timescale_hypertable"


class TimescaleContinuousAggregate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["timescale_continuous_aggregate"] = (
        "timescale_continuous_aggregate"
    )


RelationSpecialization = Annotated[
    TimescaleHypertable | TimescaleContinuousAggregate,
    Field(discriminator="kind"),
]
