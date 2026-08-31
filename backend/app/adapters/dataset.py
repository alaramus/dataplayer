"""What only a file format knows about the dataset inside it.

A discriminated union rather than a bag of labelled strings: the reader of a
Parquet file wants different facts from the reader of a spreadsheet, and a
screen that rendered "name: value" pairs the source had written would be
showing text nobody could check. Adding a format means adding a member here and
a branch to the one place that renders them, which is a type error until it is
written (D51).
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class ParquetDataset(BaseModel):
    """A columnar file, described from its own footer."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["parquet"] = "parquet"
    # Exact, not an estimate: the footer counts the rows of every group.
    rows: int = Field(ge=0)
    row_groups: int = Field(ge=0)
    columns: int = Field(ge=0)
    # Distinct codecs, in the order they were first met. One file may compress
    # one column with one codec and another with a second.
    compression: list[str] = Field(default_factory=list)
    # The writer's own claim about itself, and empty in a file that made none.
    created_by: str | None = None
    format_version: str
    size_bytes: int = Field(ge=0)


class WorksheetDataset(BaseModel):
    """One sheet of a workbook, and where it sits among the others."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["worksheet"] = "worksheet"
    workbook: str
    sheet_name: str
    # One-based, among the worksheets of the workbook and in their order.
    sheet_position: int = Field(ge=1)
    sheet_count: int = Field(ge=1)
    hidden: bool = False
    # The used range the sheet declares, header row excluded from the count of
    # rows. A workbook written without a dimension states neither.
    rows: int | None = Field(default=None, ge=0)
    columns: int | None = Field(default=None, ge=0)


DatasetInfo = Annotated[
    ParquetDataset | WorksheetDataset,
    Field(discriminator="kind"),
]
