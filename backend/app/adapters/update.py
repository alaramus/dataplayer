"""The source-independent boundary for changing relation rows."""

from typing import Annotated, Literal

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


class CellEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str
    value: str | None


class RowEdit(BaseModel):
    """One row of a pasted block, named by the version it was read with."""

    model_config = ConfigDict(extra="forbid")

    row_handle: str
    cells: Annotated[list[CellEdit], Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def unique_columns(self) -> RowEdit:
        names = [cell.column for cell in self.cells]
        if len(names) != len(set(names)):
            raise ValueError("A column may be set only once in a row")
        return self


class UpdateCellsRequest(BaseModel):
    """A rectangle of cells, as rows rather than as a flat list of cells.

    Rows, because D25 versions a row: the handle carries the key and the xmin
    it was read with, and repeating that on every cell would invite two cells
    of one row to disagree about which version they are editing.
    """

    model_config = ConfigDict(extra="forbid")

    node_id: str
    rows: Annotated[list[RowEdit], Field(min_length=1, max_length=500)]

    @model_validator(mode="after")
    def bounded_and_distinct(self) -> UpdateCellsRequest:
        handles = [row.row_handle for row in self.rows]
        if len(handles) != len(set(handles)):
            raise ValueError("A row may be edited only once")
        if sum(len(row.cells) for row in self.rows) > 2000:
            raise ValueError("A paste may carry at most 2000 cells")
        return self


class InsertRowsRequest(BaseModel):
    """A block of rows for one relation, values in the order of `columns`."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    columns: Annotated[list[str], Field(min_length=1, max_length=100)]
    rows: Annotated[list[list[str | None]], Field(min_length=1, max_length=5000)]

    @model_validator(mode="after")
    def rectangular_and_distinct(self) -> InsertRowsRequest:
        if len(self.columns) != len(set(self.columns)):
            raise ValueError("A column may be filled only once")
        width = len(self.columns)
        if any(len(row) != width for row in self.rows):
            raise ValueError("Every row carries one value per column")
        if width * len(self.rows) > 50_000:
            raise ValueError("A single move may carry at most 50000 values")
        return self


class RejectedValue(BaseModel):
    """A value the target column cannot read, and enough to go and find it.

    The value travels back, cut short, because it is the reader's own content
    and because naming a row and a column without it sends them hunting.
    """

    model_config = ConfigDict(extra="forbid")

    row: int
    column: str
    value: str | None


class RowsInserted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["inserted"] = "inserted"
    inserted: int


class ValuesRejected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["rejected"] = "rejected"
    cells: list[RejectedValue]


InsertRowsResult = Annotated[
    RowsInserted | ValuesRejected,
    Field(discriminator="kind"),
]


class UpdatedRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_handle: str
    values: list[str | None]


class CellsUpdated(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["updated"] = "updated"
    rows: list[UpdatedRow]


class RejectedCell(BaseModel):
    """Where an unreadable value sits, in the request's own coordinates."""

    model_config = ConfigDict(extra="forbid")

    row: int
    column: str


class CellsRejected(BaseModel):
    """Values the column's type cannot read, named rather than counted.

    The mirror of the counts in D37 through D40: those describe data the reader
    has not looked at, so a number is the useful answer; these are the values
    in front of them, and there are at most two thousand.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["rejected"] = "rejected"
    cells: list[RejectedCell]


UpdateCellsResult = Annotated[
    CellsUpdated | CellsRejected,
    Field(discriminator="kind"),
]


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
