"""What can be made of a file, and how it is turned into rows."""

import csv
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol, TextIO

from app.adapters.catalog import ContentKind
from app.adapters.fetch import FetchColumn

# Delimited files become columns. The delimiter of a .csv is decided from its
# first line: the extension promises commas only by convention.
TABLE_EXTENSIONS: frozenset[str] = frozenset({".csv", ".tsv"})

# Everything that is not one of these is treated as text, so a file without an
# extension, a Dockerfile or an unknown config still opens. The old
# application worked the other way round, from white lists of readable
# extensions, and anything unlisted simply could not be read.
BINARY_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".7z",
        ".avi",
        ".bin",
        ".bz2",
        ".class",
        ".dll",
        ".doc",
        ".docx",
        ".exe",
        ".gif",
        ".gz",
        ".ico",
        ".iso",
        ".jar",
        ".jpeg",
        ".jpg",
        ".mp3",
        ".mp4",
        ".odt",
        ".ogg",
        ".pdf",
        ".png",
        ".ppt",
        ".pptx",
        ".rar",
        ".so",
        ".tar",
        ".tgz",
        ".ttf",
        ".wav",
        ".webm",
        ".webp",
        ".woff",
        ".woff2",
        ".xls",
        ".xlsx",
        ".zip",
        ".zst",
    }
)


def classify(name: str) -> ContentKind:
    suffix = PurePosixPath(name).suffix.lower()
    if suffix in TABLE_EXTENSIONS:
        return "table"
    if suffix in BINARY_EXTENSIONS:
        return "opaque"
    return "text"


@dataclass(frozen=True)
class Page:
    """One page of rows, before the source adds what it can and cannot do."""

    columns: list[FetchColumn]
    rows: list[list[Any]]
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

            names = _usable_names(header)
            for _ in range(offset):
                if next(reader, None) is None:
                    break

            rows: list[list[Any]] = []
            has_more = False
            for row in reader:
                if len(rows) == limit:
                    has_more = True
                    break
                rows.append(_fit(row, len(names)))

        # A CSV states no types, and guessing one from the first page would
        # make the answer depend on where the reader happened to stop.
        columns = [FetchColumn(name=name, data_type="text") for name in names]
        return Page(columns=columns, rows=rows, has_more=has_more)


class TextReader:
    """Anything else readable: one row per line, numbered from one."""

    def read(self, path: Path, limit: int, offset: int) -> Page:
        rows: list[list[Any]] = []
        has_more = False
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for _ in range(offset):
                if handle.readline() == "":
                    break
            for number, line in enumerate(handle, start=offset + 1):
                if len(rows) == limit:
                    has_more = True
                    break
                rows.append([number, line.rstrip("\n").rstrip("\r")])

        columns = [
            FetchColumn(name="line_no", data_type="integer"),
            FetchColumn(name="line", data_type="text"),
        ]
        return Page(columns=columns, rows=rows, has_more=has_more)


def _delimiter(path: Path, handle: TextIO) -> str:
    """The delimiter of a delimited file, without consuming the header."""
    if path.suffix.lower() == ".tsv":
        return "\t"
    first_line = handle.readline()
    handle.seek(0)
    try:
        return csv.Sniffer().sniff(first_line, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def _usable_names(header: list[str]) -> list[str]:
    """Column names a grid can address: non-empty and distinct.

    A header is written by hand and regularly has neither property.
    """
    names: list[str] = []
    for position, raw in enumerate(header, start=1):
        name = raw.strip() or f"column_{position}"
        if name in names:
            name = f"{name}_{position}"
        names.append(name)
    return names


def _fit(row: list[str], width: int) -> list[Any]:
    """One row shaped to the header, which decides the width of the table."""
    if len(row) < width:
        return [*row, *[None] * (width - len(row))]
    return row[:width]
