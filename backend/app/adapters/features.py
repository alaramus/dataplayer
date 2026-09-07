"""Runtime features exposed by one connected source (D120)."""

from datetime import datetime
from typing import Literal, Protocol, Self, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

FeatureCode = Literal["timescaledb"]
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
    features: list[SourceFeature] = Field(max_length=MAX_SOURCE_FEATURES)

    @model_validator(mode="after")
    def feature_codes_are_unique(self) -> Self:
        codes = [feature.code for feature in self.features]
        if len(codes) != len(set(codes)):
            raise ValueError("feature codes must be unique")
        return self


@runtime_checkable
class SupportsSourceFeatures(Protocol):
    async def source_features(self) -> SourceFeatures: ...
