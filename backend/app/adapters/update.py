"""The source-independent boundary for changing relation rows."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


class UpdateCellRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    row_handle: str
    column: str
    value: str | None


class UpdateCellResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: list[str | None]
    row_handle: str


class InsertValue(BaseModel):
    """One explicitly supplied value; an absent column keeps its source default."""

    model_config = ConfigDict(extra="forbid")

    column: str
    value: str | None


class InsertRowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    values: Annotated[list[InsertValue], Field(max_length=1000)] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def unique_columns(self) -> InsertRowRequest:
        names = [item.column for item in self.values]
        if len(names) != len(set(names)):
            raise ValueError("An insert column may be supplied only once")
        return self


class InsertRowResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: list[str | None]
    row_handle: str | None


class DeleteRowsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    row_handles: Annotated[list[str], Field(min_length=1, max_length=500)]

    @model_validator(mode="after")
    def unique_handles(self) -> DeleteRowsRequest:
        if len(self.row_handles) != len(set(self.row_handles)):
            raise ValueError("A row may be deleted only once")
        return self


class DeleteRowsResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deleted: int


class RowConflict(Exception):
    """The row no longer has the version the caller read."""
