"""Turning a JSON document into records, and records into one table.

The shape of the table is settled by reading the whole file, never by looking
at the page that was asked for: two readers scrolling the same file must not
see two different sets of columns. That is what bounds the file — a document
too large to read whole is not read as records at all — and it is why nothing
here takes a limit or an offset.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from app.adapters import jsontext
from app.adapters.delimited import usable_names
from app.adapters.fetch import FetchColumn
from app.adapters.file.formats import JSON_LINES_EXTENSIONS
from app.adapters.relation import ColumnType

# One JSON document is only valid whole, so the reading cannot be cut short at
# a page boundary the way a delimited file can. The ceiling is what keeps a
# request bounded; above it the file is still readable, as lines.
MAX_RECORD_BYTES = 4 * 1024 * 1024

# Files whose records are one per line, as opposed to one document holding all
# of them.
LINE_SUFFIXES = JSON_LINES_EXTENSIONS

# The one column of a file whose records are not all objects. Such a table has
# no columns taken from keys, so this name cannot collide with one.
VALUE_COLUMN = "value"

# The categories a JSON value can land in, which is a closed set smaller than
# the one a source may declare: an unlisted one has to fail to type check here
# rather than to be missing from the table below at runtime.
RecordType = Literal["number", "boolean", "json", "string"]

_TYPES: dict[RecordType, ColumnType] = {
    "number": ColumnType(sql="number", category="number"),
    "boolean": ColumnType(sql="boolean", category="boolean"),
    "json": ColumnType(sql="json", category="json"),
    "string": ColumnType(sql="string", category="string"),
}


@dataclass(frozen=True)
class Table:
    """Every record of the file, as columns and rows."""

    columns: list[FetchColumn]
    rows: list[list[str | None]]


@dataclass(frozen=True)
class NotRecords:
    """Why this file was not read as records, in words for the reader."""

    reason: str


def read(path: Path, *, one_per_line: bool | None = None) -> Table | NotRecords:
    """The whole file as one table, or the reason it is not one.

    Blocking work — the file is read and parsed entirely — so it is called
    from a worker thread.

    Whether the file holds one document or one per line is decided by its name,
    unless a caller already knows better: a log whose lines are JSON objects is
    a `.log`, and reading it as one document fails on its second line.
    """
    size_bytes = path.stat().st_size
    if size_bytes > MAX_RECORD_BYTES:
        return NotRecords(
            f"This file is larger than {MAX_RECORD_BYTES // (1024 * 1024)} MB, "
            "so it cannot be projected as one table."
        )

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return NotRecords(
            "This file is not valid UTF-8 text, so it cannot be projected as a table."
        )

    by_line = (
        one_per_line
        if one_per_line is not None
        else PurePosixPath(path.name).suffix.lower() in LINE_SUFFIXES
    )
    return from_text(text, one_per_line=by_line)


def from_text(
    text: str,
    *,
    one_per_line: bool,
    max_cells: int | None = None,
    checkpoint: Callable[[], None] | None = None,
) -> Table | NotRecords:
    """Project already bounded text using the file reader's lossless rules."""
    if len(text.encode("utf-8")) > MAX_RECORD_BYTES:
        return NotRecords(
            f"This file is larger than {MAX_RECORD_BYTES // (1024 * 1024)} MB, "
            "so it cannot be projected as one table."
        )
    parsed = _lines(text, checkpoint) if one_per_line else _document(text)
    if isinstance(parsed, NotRecords):
        return parsed
    try:
        return _table(parsed, max_cells=max_cells, checkpoint=checkpoint)
    except RecursionError:
        return NotRecords("This JSON is too deeply nested to project as a table.")


def _document(text: str) -> list[Any] | NotRecords:
    """The records of a whole-document file.

    A top-level array holds them; anything else is itself the one record the
    document describes. Reaching into an object for the array inside it would
    be a guess about which key mattered, and a guess is exactly what a source
    does not make.
    """
    try:
        value = jsontext.load(text)
    except JSONDecodeError as exc:
        return NotRecords(_decode_reason(exc))
    except jsontext.NonStandardJson as exc:
        return NotRecords(f"This file is not valid JSON ({exc}).")
    except RecursionError:
        return NotRecords(
            "This JSON document is too deeply nested to project as a table."
        )
    return value if isinstance(value, list) else [value]


def _lines(text: str, checkpoint: Callable[[], None] | None = None) -> list[Any] | NotRecords:
    """The records of a file that holds one per line.

    A blank line separates records rather than being one, which is what every
    writer of this format assumes.
    """
    parsed: list[Any] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if checkpoint is not None:
            checkpoint()
        if not line.strip():
            continue
        try:
            parsed.append(jsontext.load(line))
        except JSONDecodeError as exc:
            return NotRecords(
                f"Line {number} is not valid JSON ({exc.msg}), so the records "
                "of this file cannot be projected as a table."
            )
        except jsontext.NonStandardJson as exc:
            return NotRecords(
                f"Line {number} is not valid JSON ({exc}), so the records "
                "of this file cannot be projected as a table."
            )
        except RecursionError:
            return NotRecords(
                f"Line {number} is too deeply nested to project as a table."
            )
    return parsed


def _decode_reason(exc: JSONDecodeError) -> str:
    """Why a document did not parse, in the parser's own words.

    The message describes the text the reader wrote and nothing about the
    server, so it is the one driver message this source passes on.
    """
    return (
        f"This file is not valid JSON ({exc.msg}, line {exc.lineno} "
        f"column {exc.colno}), so it cannot be projected as a table."
    )


def _table(
    records: list[Any],
    *,
    max_cells: int | None = None,
    checkpoint: Callable[[], None] | None = None,
) -> Table | NotRecords:
    """Columns from every record, then every record shaped to them."""
    if not records:
        return Table(columns=[], rows=[])
    if not all(isinstance(record, dict) for record in records):
        if max_cells is not None and len(records) > max_cells:
            return NotRecords("The log projection exceeds the SQL cell limit")
        return _flat_table(records)

    keys: list[str] = []
    seen: set[str] = set()
    for record in records:
        if checkpoint is not None:
            checkpoint()
        for key in record:
            if key not in seen:
                seen.add(key)
                keys.append(key)

    if max_cells is not None and len(keys) * len(records) > max_cells:
        return NotRecords("The log projection exceeds the SQL cell limit")
    rows: list[list[str | None]] = []
    for record in records:
        if checkpoint is not None:
            checkpoint()
        rows.append([_cell(record.get(key)) for key in keys])
    columns = [
        FetchColumn(name=name, type=_type_of(record.get(key) for record in records))
        for key, name in zip(keys, usable_names(keys), strict=True)
    ]
    return Table(columns=columns, rows=rows)


def _flat_table(records: list[Any]) -> Table:
    """A file whose records are not all objects: one column of values."""
    return Table(
        columns=[FetchColumn(name=VALUE_COLUMN, type=_type_of(records))],
        rows=[[_cell(record)] for record in records],
    )


def _cell(value: Any) -> str | None:
    """One value as the lossless text every source hands over (D23)."""
    if value is None:
        return None
    if isinstance(value, jsontext.JsonNumber):
        return value.text
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    return jsontext.encode(value)


def _type_of(values: Iterable[Any]) -> ColumnType:
    """The type of a column, which is a type only where the file agrees.

    JSON states what each value is, unlike a delimited file, so the answer is
    read rather than guessed. Where two records disagree there is no type to
    state and the column is text, which every value already renders as.
    """
    categories: set[RecordType] = set()
    for value in values:
        if value is None:
            continue
        categories.add(_category(value))
        if len(categories) > 1:
            break
    if len(categories) == 1:
        return _TYPES[categories.pop()]
    return _TYPES["string"]


def _category(value: Any) -> RecordType:
    if isinstance(value, jsontext.JsonNumber):
        return "number"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    return "json"
