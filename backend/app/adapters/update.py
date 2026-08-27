"""The source-independent boundary for changing one existing row."""

from pydantic import BaseModel, ConfigDict


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


class RowConflict(Exception):
    """The row no longer has the version the caller read."""


