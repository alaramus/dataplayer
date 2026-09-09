"""Typed read-only plans; a fingerprint detects change, never grants access (D123)."""

import hashlib
import hmac
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.actions import ActionRefused


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

    name: Literal["set_chunk_time_interval_v1"] = "set_chunk_time_interval_v1"
    extension_version: Literal["2.17.2", "2.18.0"]
    function_oid: str = Field(pattern=r"^[1-9][0-9]{0,9}$")
    function_schema: str = Field(min_length=1, max_length=63)


class ChunkIntervalPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: Literal["set_chunk_interval"] = "set_chunk_interval"
    target: IntervalTarget
    interval: TimeDuration
    strategy: IntervalStrategy
    impact: Literal["Only future chunks use the new interval; existing chunks are not repartitioned"] = (
        "Only future chunks use the new interval; existing chunks are not repartitioned"
    )

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
