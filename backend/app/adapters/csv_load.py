"""A delimited file uploaded into a new table: what every SQL source shares.

The form, the file's two ceilings and the choice of columns are the same for
any source that makes a table of a file; what a name may be and how the table
is made are each source's own, so a source subclasses the parameters for its
names and calls `read_upload` and `chosen_rows` from its action.
"""

from collections.abc import Callable
from functools import partial
from pathlib import PurePosixPath

from anyio import to_thread
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.adapters.actions import CHUNK_BYTES, ActionRefused, FilePayload
from app.adapters.delimited import DelimitedTable, read_table
from app.core.translation import N_, say

# How many rows one loaded file may bring. More than this is a durable job
# with progress and cancellation, which is Phase 4. Refused rather than
# truncated: the reader handed over a whole file and would have no way of
# knowing that only its beginning arrived.
CSV_ROW_CEILING = 5000

# How much of the file is read before it is refused. The rows are parsed from
# what arrived rather than from a temporary file, so this is what bounds the
# memory of one request; the row ceiling alone would not, since one row can be
# as long as the whole file.
CSV_MAX_BYTES = 16 * 1024 * 1024


class LoadCsvColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1)
    target: str = Field(min_length=1)


class LoadCsvParams(BaseModel):
    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"x-ui-workflow": "file-to-relation"}
    )

    name: str = Field(
        default="",
        title=N_("Table name"),
        description=N_("Leave empty to name the table after the file"),
        json_schema_extra={"x-ui-purpose": "filename-stem"},
    )
    schema_name: str = Field(default="", title=N_("Schema"))
    create_schema: bool = False
    columns: list[LoadCsvColumn] | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def distinct_columns(self) -> LoadCsvParams:
        columns = self.columns or []
        sources = [column.source for column in columns]
        targets = [column.target for column in columns]
        if len(sources) != len(set(sources)):
            raise ValueError(say("A source column may be selected only once"))
        if len(targets) != len(set(targets)):
            raise ValueError(say("A target column may be named only once"))
        return self


def stem(filename: str) -> str:
    """The file's own name without its extension, and without any directory.

    Only ever the default of a form field, never a path: a browser that sends
    a full name should still suggest the last part of it.
    """
    tail = filename.replace("\\", "/").rsplit("/", 1)[-1]
    return PurePosixPath(tail).stem


def table_name(params: LoadCsvParams, payload: FilePayload, check: Callable[[str], str]) -> str:
    """The name asked for, or the file's, checked by the source's own rule."""
    name = params.name or stem(payload.filename or "")
    if name.strip() == "":
        raise ActionRefused("not_applicable", say("The file has no name to use; type one"))
    check(name)
    return name


async def read_upload(payload: FilePayload) -> DelimitedTable:
    """The upload, as columns and rows, refused past either ceiling.

    Held whole rather than staged on disk: it has to be parsed anyway, and
    the two ceilings say what "whole" may mean. Parsing is blocking work,
    so it goes to a worker thread.
    """
    chunks: list[bytes] = []
    size = 0
    while chunk := await payload.read(CHUNK_BYTES):
        size += len(chunk)
        if size > CSV_MAX_BYTES:
            raise ActionRefused(
                "too_large",
                say(
                    "A file loaded this way must be under {size} MB",
                    size=CSV_MAX_BYTES // (1024 * 1024),
                ),
            )
        chunks.append(chunk)
    # errors="replace" for the reason the file source reads that way: one
    # byte that is not text is not a reason to refuse the whole file.
    text = b"".join(chunks).decode("utf-8", errors="replace")
    table = await to_thread.run_sync(
        partial(read_table, text, payload.filename or "", CSV_ROW_CEILING)
    )
    if not table.columns:
        raise ActionRefused(
            "not_applicable", say("That file has no first line to name columns")
        )
    if table.more:
        raise ActionRefused(
            "too_large",
            say("A file loaded this way may hold at most {count} rows", count=CSV_ROW_CEILING),
        )
    return table


def chosen_rows(
    table: DelimitedTable, params: LoadCsvParams, check: Callable[[str], str]
) -> tuple[list[str], list[list[str | None]]]:
    """The target names and the rows of the columns asked for, in their order.

    Every column of the file when none were chosen; a target name goes through
    the source's own rule, as the table's does.
    """
    selected = (
        [LoadCsvColumn(source=column, target=column) for column in table.columns]
        if params.columns is None
        else params.columns
    )
    positions = {column: index for index, column in enumerate(table.columns)}
    for column in selected:
        if column.source not in positions:
            raise ActionRefused(
                "not_applicable",
                say('The file has no column "{column}"', column=column.source),
            )
        check(column.target)
    if not selected:
        raise ActionRefused("not_applicable", say("Choose at least one column"))
    rows: list[list[str | None]] = [
        [row[positions[column.source]] for column in selected] for row in table.rows
    ]
    return [column.target for column in selected], rows
