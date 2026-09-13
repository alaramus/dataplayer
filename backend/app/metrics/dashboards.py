"""A dashboard: a stored layout of typed widgets (D129).

The body is read and written whole and never queried into, so it is one JSON
column. What may be in it is a discriminated union validated on the way in and
again on the way out: a row that no longer validates is listed empty and marked
broken rather than refused, so one damaged row does not hide the rest.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator
from pydantic import Field as PydanticField
from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, SQLModel

from app.core.schemas import get_datetime_utc
from app.metrics.models import ProcessLimit
from app.metrics.store import ProcessSort

GRID_COLUMNS = 12
MAX_WIDGETS = 20
MAX_TITLE = 120
MAX_NAME = 120
MIN_WIDGET_W = 2
MIN_WIDGET_H = 2
MAX_WIDGET_H = 40
MAX_GRID_Y = 400
MAX_SERIES_PER_WIDGET = 50
MAX_HOST = 128

# Closed sets: a free range or interval is a field somebody puts one second into.
RangeSeconds = Literal[300, 900, 3600, 21600, 86400, 604800, 2592000]
RefreshSeconds = Literal[0, 10, 30, 60, 300]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WidgetLayout(_Strict):
    x: int = PydanticField(ge=0, lt=GRID_COLUMNS)
    y: int = PydanticField(ge=0, le=MAX_GRID_Y)
    w: int = PydanticField(ge=MIN_WIDGET_W, le=GRID_COLUMNS)
    h: int = PydanticField(ge=MIN_WIDGET_H, le=MAX_WIDGET_H)

    @model_validator(mode="after")
    def fits_the_grid(self) -> Self:
        if self.x + self.w > GRID_COLUMNS:
            raise ValueError("A widget does not fit the width of the grid")
        return self


class TimeseriesWidget(_Strict):
    type: Literal["timeseries"]
    id: uuid.UUID
    title: str = PydanticField(max_length=MAX_TITLE)
    layout: WidgetLayout
    series_ids: list[int] = PydanticField(min_length=1, max_length=MAX_SERIES_PER_WIDGET)


class StatWidget(_Strict):
    type: Literal["stat"]
    id: uuid.UUID
    title: str = PydanticField(max_length=MAX_TITLE)
    layout: WidgetLayout
    series_id: int


class ProcessesWidget(_Strict):
    """The newest process table of one host of one agent."""

    type: Literal["processes"]
    id: uuid.UUID
    title: str = PydanticField(max_length=MAX_TITLE)
    layout: WidgetLayout
    agent_id: uuid.UUID
    host: str = PydanticField(min_length=1, max_length=MAX_HOST)
    sort: ProcessSort = "pcpu"
    limit: ProcessLimit = 20


AnyWidget = TimeseriesWidget | StatWidget | ProcessesWidget
Widget = Annotated[AnyWidget, PydanticField(discriminator="type")]


def series_of(widget: AnyWidget) -> list[int]:
    if isinstance(widget, StatWidget):
        return [widget.series_id]
    if isinstance(widget, TimeseriesWidget):
        return list(widget.series_ids)
    return []


def agents_of(widget: AnyWidget) -> list[uuid.UUID]:
    """Agents a widget reads beyond its series."""
    return [widget.agent_id] if isinstance(widget, ProcessesWidget) else []


class DashboardOptions(_Strict):
    range_seconds: RangeSeconds = 900
    refresh_seconds: RefreshSeconds = 30


class DashboardContent(_Strict):
    options: DashboardOptions = PydanticField(default_factory=DashboardOptions)
    widgets: list[Widget] = PydanticField(default_factory=list, max_length=MAX_WIDGETS)

    @model_validator(mode="after")
    def widget_ids_are_unique(self) -> Self:
        ids = [widget.id for widget in self.widgets]
        if len(ids) != len(set(ids)):
            raise ValueError("Two widgets have the same id")
        return self


class Dashboard(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True
    )
    name: str = Field(max_length=MAX_NAME)
    content: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    # Raised by every save. A save naming an older version is refused, so two
    # tabs editing one dashboard do not silently undo each other.
    version: int = Field(default=1)
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class DashboardCreate(_Strict):
    name: str = PydanticField(min_length=1, max_length=MAX_NAME)


class DashboardSave(DashboardContent):
    name: str = PydanticField(min_length=1, max_length=MAX_NAME)
    version: int = PydanticField(ge=1)


class DashboardPublic(DashboardContent):
    id: uuid.UUID
    name: str
    version: int
    updated_at: datetime
    # The stored content could not be read and is shown empty.
    broken: bool = False


def public(dashboard: Dashboard) -> DashboardPublic:
    try:
        content = DashboardContent.model_validate(dashboard.content)
        broken = False
    except ValidationError:
        content = DashboardContent()
        broken = True
    return DashboardPublic(
        id=dashboard.id,
        name=dashboard.name,
        version=dashboard.version,
        updated_at=dashboard.updated_at,
        options=content.options,
        widgets=content.widgets,
        broken=broken,
    )
