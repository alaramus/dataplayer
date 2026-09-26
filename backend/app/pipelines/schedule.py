"""When a pipeline runs by itself (D179), kept beside its body.

A schedule is not what a pipeline runs, so it is a row of its own: a change
of it is not checked against the version the canvas saves with, and the loop
that starts runs reads it without reading the body.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic import Field as PydanticField
from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, SQLModel

from app.core.schemas import get_datetime_utc

MIN_EVERY_MINUTES = 5
MAX_EVERY_MINUTES = 7 * 24 * 60
MAX_TIMES = 12

TimeOfDay = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
# Monday is 0, as Python counts days.
Weekday = Annotated[int, PydanticField(ge=0, le=6)]


class ScheduleSettings(BaseModel):
    """What the owner chose: every so long, or at times on chosen days."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    kind: Literal["interval", "times"] = "times"
    every_minutes: int = PydanticField(default=60, ge=MIN_EVERY_MINUTES, le=MAX_EVERY_MINUTES)
    times: list[TimeOfDay] = PydanticField(default_factory=lambda: ["03:00"], max_length=MAX_TIMES)
    days: list[Weekday] = PydanticField(default_factory=lambda: list(range(7)), max_length=7)
    # The owner's wall clock, as the browser names it.
    time_zone: str = PydanticField(min_length=1, max_length=64)

    @field_validator("time_zone")
    @classmethod
    def a_known_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Unknown time zone") from None
        return value

    @model_validator(mode="after")
    def times_on_days(self) -> Self:
        self.times = sorted(set(self.times))
        self.days = sorted(set(self.days))
        if self.kind == "times" and not self.times:
            raise ValueError("Choose a time of day")
        if self.kind == "times" and not self.days:
            raise ValueError("Choose a day of the week")
        return self


class PipelineSchedule(SQLModel, table=True):
    pipeline_id: uuid.UUID = Field(
        foreign_key="pipeline.id", primary_key=True, ondelete="CASCADE"
    )
    settings: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    # What an interval counts from: when the schedule was last switched on.
    counted_from: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    # None while it is off.
    next_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True, index=True)
    )
    # The last time it came and nothing started, and why (D179).
    note: str | None = Field(default=None, max_length=512)
    note_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class SchedulePublic(BaseModel):
    """A pipeline's schedule as its owner reads it; no settings before the first."""

    settings: ScheduleSettings | None = None
    next_at: datetime | None = None
    note: str | None = None
    note_at: datetime | None = None
