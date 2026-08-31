"""Turning delimited text into named columns and text rows.

Shared because two sources need the same reading and neither may import the
other: a file in personal storage is read a page at a time, and an uploaded
CSV becomes a table in a database. What differs is the loop around it — one
pages, the other takes the whole file up to a ceiling — so only the parts that
decide the delimiter, what a column is called and how wide a row is live here.
"""

import csv
import io
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

# What a first line is sniffed for. A `.tsv` promises tabs by its name; a
# `.csv` promises commas only by convention, which is why the line is read.
DELIMITERS = ",;\t|"


def delimiter_of(filename: str, first_line: str) -> str:
    """The delimiter of a delimited file, from its name or its first line."""
    if PurePosixPath(filename).suffix.lower() == ".tsv":
        return "\t"
    try:
        return csv.Sniffer().sniff(first_line, delimiters=DELIMITERS).delimiter
    except csv.Error:
        return ","


def usable_names(header: list[str]) -> list[str]:
    """Column names a caller can address: non-empty and distinct.

    A header is written by hand and regularly has neither property.
    """
    names: list[str] = []
    for position, raw in enumerate(header, start=1):
        name = raw.strip() or f"column_{position}"
        if name in names:
            name = f"{name}_{position}"
        names.append(name)
    return names


def fit(row: Sequence[str | None], width: int) -> list[str | None]:
    """One row shaped to the header, which decides the width of the table.

    A cell may already be absent — a spreadsheet has empty cells in the middle
    of a row, where a delimited file only has short rows — so the width is the
    only thing this decides.
    """
    if len(row) < width:
        return [*row, *[None] * (width - len(row))]
    fitted: list[str | None] = []
    fitted.extend(row[:width])
    return fitted


@dataclass(frozen=True)
class DelimitedTable:
    """A whole delimited text, read up to a ceiling of rows."""

    columns: list[str]
    rows: list[list[str | None]]
    # True when the text held more rows than the ceiling allows. What to do
    # about that belongs to the caller: paging a file and loading one are not
    # the same answer.
    more: bool


def read_table(text: str, filename: str, ceiling: int) -> DelimitedTable:
    """Read the whole text, stopping one row past the ceiling.

    Blocking work — csv parsing of everything held — so it is called from a
    worker thread. No column is given a type: a delimited file states none,
    and one guessed from the rows that happen to be here would change with
    where the reading stopped.
    """
    # newline="" because csv handles the line endings itself, including the
    # ones inside a quoted value.
    handle = io.StringIO(text, newline="")
    first_line = handle.readline()
    handle.seek(0)
    reader = csv.reader(handle, delimiter=delimiter_of(filename, first_line))
    header = next(reader, None)
    if header is None:
        return DelimitedTable(columns=[], rows=[], more=False)

    names = usable_names(header)
    rows: list[list[str | None]] = []
    more = False
    for row in reader:
        if len(rows) == ceiling:
            more = True
            break
        rows.append(fit(row, len(names)))
    return DelimitedTable(columns=names, rows=rows, more=more)
