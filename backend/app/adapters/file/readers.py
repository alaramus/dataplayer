"""Tabular projections of files."""

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TextIO

from app.adapters.delimited import delimiter_of, fit, usable_names
from app.adapters.fetch import FetchColumn
from app.adapters.file import records
from app.adapters.relation import ColumnType


@dataclass(frozen=True)
class Page:
    """One page of rows, before the source adds what it can and cannot do."""

    columns: list[FetchColumn]
    rows: list[list[str | None]]
    has_more: bool


class Reader(Protocol):
    def read(self, path: Path, limit: int, offset: int) -> Page:
        """Read one page. Runs in a worker thread: every call here blocks."""
        ...


class CsvReader:
    """A delimited file: the first line names the columns."""

    def read(self, path: Path, limit: int, offset: int) -> Page:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            reader = csv.reader(handle, delimiter=_delimiter(path, handle))
            header = next(reader, None)
            if header is None:
                return Page(columns=[], rows=[], has_more=False)

            names = usable_names(header)
            for _ in range(offset):
                if next(reader, None) is None:
                    break

            rows: list[list[str | None]] = []
            has_more = False
            for row in reader:
                if len(rows) == limit:
                    has_more = True
                    break
                rows.append(fit(row, len(names)))

        # A CSV states no types, and guessing one from the first page would
        # make the answer depend on where the reader happened to stop.
        columns = [
            FetchColumn(name=name, type=ColumnType(sql="text", category="string"))
            for name in names
        ]
        return Page(columns=columns, rows=rows, has_more=has_more)


class JsonTableReader:
    """The explicit table projection of JSON/JSONL records."""

    def read(self, path: Path, limit: int, offset: int) -> Page:
        table = records.read(path)
        if isinstance(table, records.NotRecords):
            # The caller explicitly asked for a table. Returning numbered
            # text rows would silently change representation under that
            # request, so the projection is refused with its precise reason.
            raise ValueError(table.reason)
        page = table.rows[offset : offset + limit]
        return Page(
            columns=table.columns,
            rows=page,
            has_more=offset + len(page) < len(table.rows),
        )


class TextReader:
    """Anything else readable: one row per line, numbered from one."""

    def read(self, path: Path, limit: int, offset: int) -> Page:
        rows: list[list[str | None]] = []
        has_more = False
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for _ in range(offset):
                if handle.readline() == "":
                    break
            for number, line in enumerate(handle, start=offset + 1):
                if len(rows) == limit:
                    has_more = True
                    break
                rows.append([str(number), line.rstrip("\n").rstrip("\r")])

        columns = [
            FetchColumn(name="line_no", type=ColumnType(sql="text", category="string")),
            FetchColumn(name="line", type=ColumnType(sql="text", category="string")),
        ]
        return Page(columns=columns, rows=rows, has_more=has_more)


def _delimiter(path: Path, handle: TextIO) -> str:
    """The delimiter of this file, without consuming the header.

    The peek is here and the rule is in `delimited`: a file source has a
    handle to rewind, and an upload has only the text it arrived as.
    """
    first_line = handle.readline()
    handle.seek(0)
    return delimiter_of(path.name, first_line)
