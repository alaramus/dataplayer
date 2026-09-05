"""Tabular projections of files."""

import csv
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Protocol, TextIO

from app.adapters.delimited import delimiter_of, fit, usable_names
from app.adapters.fetch import FetchColumn, Filter, ScalarFilter
from app.adapters.file import logs, records
from app.adapters.relation import ColumnType

# What a file may be asked about a value, and the whole of it (D109). Sorting
# stays refused, so this is the only vocabulary the file source publishes.
FILE_FILTER_OPERATORS = ["eq"]


@dataclass(frozen=True)
class Page:
    """One page of rows, before the source adds what it can and cannot do.

    `positions` says where each row came from, counted from the first row after
    the header. It is not `offset + index` once a filter is in play: a page of
    matches is not a window into a contiguous run, and a row handle has to name
    the row where it actually is (D109).
    """

    columns: list[FetchColumn]
    rows: list[list[str | None]]
    has_more: bool
    positions: list[int]


@dataclass(frozen=True)
class RowMatch:
    """The rows a filter keeps, as a column position and the text it must hold.

    Resolved against the names this projection actually has, once, before any
    row is read — never against a name that came from the request alone.
    """

    tests: tuple[tuple[int, str], ...]

    def keeps(self, row: Sequence[str | None]) -> bool:
        return all(row[position] == value for position, value in self.tests)



def matcher(filters: Sequence[Filter], names: Sequence[str]) -> RowMatch:
    """What these filters mean over these columns, or why they mean nothing.

    A file has no index and states no types, so equality over its canonical
    text is the only predicate it can answer honestly (D109). Anything else is
    refused here rather than approximated somewhere further down.
    """
    tests: list[tuple[int, str]] = []
    for asked in filters:
        if not isinstance(asked, ScalarFilter) or asked.op != "eq":
            raise ValueError("This source can only filter by an exact value")
        if asked.column not in names:
            raise ValueError(f'This file has no column "{asked.column}"')
        tests.append((names.index(asked.column), asked.value))
    return RowMatch(tuple(tests))


def select(
    rows: Iterable[list[str | None]], limit: int, offset: int, match: RowMatch
) -> tuple[list[list[str | None]], list[int], bool]:
    """The page of matching rows, where each came from, and whether more follow.

    Paging counts matching rows: the offset skips matches rather than rows, and
    `has_more` means another matching row exists. One row past the page is read
    to find that out, which is what the unfiltered readers already did.
    """
    kept: list[list[str | None]] = []
    positions: list[int] = []
    skipped = 0
    has_more = False
    for position, row in enumerate(rows):
        if not match.keeps(row):
            continue
        if skipped < offset:
            skipped += 1
            continue
        if len(kept) == limit:
            has_more = True
            break
        kept.append(row)
        positions.append(position)
    return kept, positions, has_more


class Reader(Protocol):
    def read(
        self, path: Path, limit: int, offset: int, filters: Sequence[Filter] = ()
    ) -> Page:
        """Read one page. Runs in a worker thread: every call here blocks."""
        ...


class CsvReader:
    """A delimited file: the first line names the columns."""

    def read(
        self, path: Path, limit: int, offset: int, filters: Sequence[Filter] = ()
    ) -> Page:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            reader = csv.reader(handle, delimiter=_delimiter(path, handle))
            header = next(reader, None)
            if header is None:
                if filters:
                    raise ValueError("This file has no columns to filter by")
                return Page(columns=[], rows=[], has_more=False, positions=[])

            names = usable_names(header)
            match = matcher(filters, names)
            rows, positions, has_more = select(
                (fit(row, len(names)) for row in reader), limit, offset, match
            )

        # A CSV states no types, and guessing one from the first page would
        # make the answer depend on where the reader happened to stop.
        columns = [
            FetchColumn(name=name, type=ColumnType(sql="text", category="string"))
            for name in names
        ]
        return Page(
            columns=columns, rows=rows, has_more=has_more, positions=positions
        )


class JsonTableReader:
    """The explicit table projection of JSON/JSONL records."""

    def __init__(self, *, one_per_line: bool | None = None) -> None:
        # Said by the caller only where the name cannot say it: a log whose
        # lines are JSON objects is a `.log`, and reading it as one document
        # fails on its second line.
        self._one_per_line = one_per_line

    def read(
        self, path: Path, limit: int, offset: int, filters: Sequence[Filter] = ()
    ) -> Page:
        table = records.read(path, one_per_line=self._one_per_line)
        return _record_page(table, limit, offset, filters)


class LogReader:
    """A log file: the columns its own lines are written in.

    Three answers, and which one a file gets is decided by the file. Lines that
    are JSON objects are records, and the record reader already turns those
    into columns. Lines that fit one of the known shapes become that shape's
    columns. A file that fits neither is read as text is read — numbered lines
    — because a log nobody has taught this module yet is still a log somebody
    wants to look at.
    """

    def read(
        self, path: Path, limit: int, offset: int, filters: Sequence[Filter] = ()
    ) -> Page:
        shape_name = logs.shape_of(path)
        if shape_name == logs.JSON_LINES:
            return JsonTableReader(one_per_line=True).read(path, limit, offset, filters)
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return self._read_lines(handle, shape_name, limit, offset, filters)

    def read_snapshot(
        self,
        data: bytes,
        limit: int,
        *,
        max_cells: int,
        checkpoint: Callable[[], None],
    ) -> Page:
        """The same projection over a bounded byte snapshot for SQL (D96)."""
        with StringIO(data.decode("utf-8", errors="replace"), newline=None) as handle:
            shape_name = logs.shape_of_lines(_checked_lines(handle, checkpoint))
            handle.seek(0)
            if shape_name == logs.JSON_LINES:
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError:
                    raise ValueError("This log is not valid UTF-8 text") from None
                checkpoint()
                table = records.from_text(
                    text, one_per_line=True, max_cells=max_cells, checkpoint=checkpoint
                )
                checkpoint()
                return _record_page(table, limit, 0, ())
            return self._read_lines(handle, shape_name, limit, 0, (), checkpoint)

    def _read_lines(
        self,
        handle: Iterable[str],
        shape_name: str | None,
        limit: int,
        offset: int,
        filters: Sequence[Filter] = (),
        checkpoint: Callable[[], None] | None = None,
    ) -> Page:
        shape = logs.shape_named(shape_name) if shape_name is not None else None
        if shape is None:
            return TextReader().read_stream(handle, limit, offset, filters, checkpoint)

        match = matcher(filters, shape.columns)
        rows, positions, has_more = select(
            (
                logs.parse(shape, line.rstrip("\n").rstrip("\r"))
                for line in _checked_lines(handle, checkpoint)
            ),
            limit,
            offset,
            match,
        )
        columns = [
            FetchColumn(name=name, type=ColumnType(sql="text", category="string"))
            for name in shape.columns
        ]
        return Page(
            columns=columns, rows=rows, has_more=has_more, positions=positions
        )


TEXT_COLUMN_NAMES = ("line_no", "line")


class TextReader:
    """Anything else readable: one row per line, numbered from one."""

    def read(
        self, path: Path, limit: int, offset: int, filters: Sequence[Filter] = ()
    ) -> Page:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return self.read_stream(handle, limit, offset, filters)

    def read_stream(
        self,
        handle: Iterable[str],
        limit: int,
        offset: int,
        filters: Sequence[Filter] = (),
        checkpoint: Callable[[], None] | None = None,
    ) -> Page:
        match = matcher(filters, TEXT_COLUMN_NAMES)
        rows, positions, has_more = select(
            (
                [str(number), line.rstrip("\n").rstrip("\r")]
                for number, line in enumerate(
                    _checked_lines(handle, checkpoint), start=1
                )
            ),
            limit,
            offset,
            match,
        )
        columns = [
            FetchColumn(name=name, type=ColumnType(sql="text", category="string"))
            for name in TEXT_COLUMN_NAMES
        ]
        return Page(
            columns=columns, rows=rows, has_more=has_more, positions=positions
        )


def _record_page(
    table: records.Table | records.NotRecords,
    limit: int,
    offset: int,
    filters: Sequence[Filter],
) -> Page:
    if isinstance(table, records.NotRecords):
        # Asking for records must never silently fall back to numbered text.
        raise ValueError(table.reason)
    match = matcher(filters, [column.name for column in table.columns])
    rows, positions, has_more = select(table.rows, limit, offset, match)
    return Page(
        columns=table.columns,
        rows=rows,
        has_more=has_more,
        positions=positions,
    )


def _checked_lines(handle: Iterable[str], checkpoint: Callable[[], None] | None) -> Iterator[str]:
    for line in handle:
        if checkpoint is not None:
            checkpoint()
        yield line


def _delimiter(path: Path, handle: TextIO) -> str:
    """The delimiter of this file, without consuming the header.

    The peek is here and the rule is in `delimited`: a file source has a
    handle to rewind, and an upload has only the text it arrived as.
    """
    first_line = handle.readline()
    handle.seek(0)
    return delimiter_of(path.name, first_line)
