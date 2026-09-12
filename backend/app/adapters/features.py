"""What one connected source says about itself at runtime (D120).

Two things, because they are read from the same connection and answered to the
same reader: what the server is running, and which optional features of it are
there. A person about to work through a connection wants both, and the second
one is meaningless without the first.
"""

from datetime import datetime
from typing import Literal, Protocol, Self, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

FeatureCode = Literal["timescaledb"]
FEATURE_TITLES: dict[FeatureCode, str] = {"timescaledb": "TimescaleDB"}
FeatureState = Literal["absent", "available", "unsupported", "unavailable"]
MAX_SOURCE_FEATURES = 32


class SourceFeature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: FeatureCode
    title: str = Field(min_length=1, max_length=100)
    installed_version: str | None = Field(default=None, max_length=100)
    state: FeatureState
    reason: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_state_details(self) -> Self:
        if self.state == "available" and self.installed_version is None:
            raise ValueError("available features must state their installed version")
        if self.state in {"unsupported", "unavailable"} and self.reason is None:
            raise ValueError(f"{self.state} features must state a reason")
        if self.state == "absent" and self.installed_version is not None:
            raise ValueError("absent features cannot have an installed version")
        return self


class SourceFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_at: datetime
    # What the server says it is running, in its own numbering and without the
    # rest of the sentence a driver would hand over: "17.6", not the build,
    # the distribution and the compiler. Absent where the source does not say.
    server_version: str | None = Field(default=None, max_length=100)
    features: list[SourceFeature] = Field(max_length=MAX_SOURCE_FEATURES)

    @model_validator(mode="after")
    def feature_codes_are_unique(self) -> Self:
        codes = [feature.code for feature in self.features]
        if len(codes) != len(set(codes)):
            raise ValueError("feature codes must be unique")
        return self


@runtime_checkable
class SupportsSourceFeatures(Protocol):
    """A source that will say what it is running, and what it has installed."""

    async def source_features(self) -> SourceFeatures: ...
