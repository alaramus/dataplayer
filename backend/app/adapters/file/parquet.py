"""Reading a Parquet file: its declared schema, and a bounded page of rows.

A columnar file states its own columns, their types and its exact row count, so
none of it is guessed (D51). The footer is metadata and is read without
decompressing anything; a page is streamed from the row groups it falls in, so
the groups before the offset are never touched and one enormous group is not
held whole.
"""

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pyarrow.types as types

from app.adapters.cells import encode_cell
from app.adapters.dataset import ParquetDataset
from app.adapters.fetch import FetchColumn
from app.adapters.file.readers import Page
from app.adapters.relation import Column, ColumnType, TypeCategory

# The same ceiling the workbook reader has, for the same reason: a page of a
# thousand rows across an unbounded number of columns is bounded by nothing.
MAX_COLUMNS = 1024


class NotParquet(ValueError):
    """The bytes under a `.parquet` name are not a Parquet file."""


def read_page(path: Path, limit: int, offset: int) -> Page:
    """One bounded page, read from the row groups it falls in. Blocking."""
    with _opened(path) as file:
        schema = file.schema_arrow
        columns = _fetch_columns(schema)
        total = int(file.metadata.num_rows)
        rows = _read_rows(file, schema, limit, offset)

    return Page(
        columns=columns,
        rows=rows,
        has_more=offset + len(rows) < total,
    )


def describe(path: Path) -> tuple[list[Column], ParquetDataset]:
    """The declared columns and the facts the footer states. Blocking."""
    with _opened(path) as file:
        schema = file.schema_arrow
        metadata = file.metadata
        _guard_width(schema)
        return _described(path, schema, metadata)


def _described(
    path: Path, schema: Any, metadata: Any
) -> tuple[list[Column], ParquetDataset]:
    columns = [
        Column(
            position=position,
            name=field.name,
            type=_column_type(field.type),
            nullable=bool(field.nullable),
        )
        for position, field in enumerate(schema, start=1)
    ]
    return columns, ParquetDataset(
        rows=int(metadata.num_rows),
        row_groups=int(metadata.num_row_groups),
        columns=len(columns),
        compression=_compression(metadata),
        created_by=None if metadata.created_by is None else str(metadata.created_by),
        format_version=str(metadata.format_version),
        size_bytes=path.stat().st_size,
    )


@contextmanager
def _opened(path: Path) -> Iterator[Any]:
    """The file's footer, or our own refusal, over a handle we close.

    The handle is opened here rather than by pyarrow so that it is closed even
    when the footer turns out not to be one: a reader that leaves a descriptor
    behind on every malformed file is a leak nobody sees until the server has
    run out of them. pyarrow's own message names the file and what the parser
    expected, and a driver's text never reaches a caller (ENGINEERING), so the
    reason is ours.
    """
    with path.open("rb") as handle:
        try:
            file = pq.ParquetFile(handle)
        except Exception:
            raise NotParquet("This file is not a Parquet file") from None
        yield file


def _read_rows(
    file: Any, schema: Any, limit: int, offset: int
) -> list[list[str | None]]:
    metadata = file.metadata
    group_count = int(metadata.num_row_groups)
    start, skip = _starting_group(metadata, group_count, offset)
    if start >= group_count or limit == 0:
        return []

    encoders = [_encoder(field.type) for field in schema]
    if not encoders:
        return []

    rows: list[list[str | None]] = []
    for batch in file.iter_batches(
        batch_size=limit, row_groups=list(range(start, group_count))
    ):
        height = int(batch.num_rows)
        if skip >= height:
            skip -= height
            continue
        rows.extend(_rows_of(batch.slice(skip, limit - len(rows)), encoders))
        skip = 0
        if len(rows) >= limit:
            break
    return rows


def _starting_group(metadata: Any, group_count: int, offset: int) -> tuple[int, int]:
    """The first row group the page touches, and the rows to skip inside it."""
    remaining = offset
    for index in range(group_count):
        rows = int(metadata.row_group(index).num_rows)
        if remaining < rows:
            return index, remaining
        remaining -= rows
    return group_count, 0


def _rows_of(batch: Any, encoders: list[Callable[[Any], str | None]]) -> list[list[str | None]]:
    """One batch as rows of text, converted column by column.

    Column-wise because that is how the value arrives: `to_pylist` on a column
    is one call into the library instead of one per cell.
    """
    columns = [
        [encode(value) for value in batch.column(index).to_pylist()]
        for index, encode in enumerate(encoders)
    ]
    return [list(row) for row in zip(*columns, strict=True)]


def _fetch_columns(schema: Any) -> list[FetchColumn]:
    _guard_width(schema)
    return [
        FetchColumn(name=field.name, type=_column_type(field.type), nullable=bool(field.nullable))
        for field in schema
    ]


def _guard_width(schema: Any) -> None:
    if len(schema) > MAX_COLUMNS:
        raise ValueError(
            f"This file has more than {MAX_COLUMNS} columns, "
            "which is more than one page may carry"
        )


def _column_type(arrow_type: Any) -> ColumnType:
    """The file's own spelling of a type, and what its values mean."""
    return ColumnType(sql=str(arrow_type), category=_category(arrow_type))


def _category(arrow_type: Any) -> TypeCategory:
    if types.is_boolean(arrow_type):
        return "boolean"
    if (
        types.is_integer(arrow_type)
        or types.is_floating(arrow_type)
        or types.is_decimal(arrow_type)
    ):
        return "number"
    if types.is_temporal(arrow_type):
        return "datetime"
    if types.is_string(arrow_type) or types.is_large_string(arrow_type):
        return "string"
    if (
        types.is_binary(arrow_type)
        or types.is_large_binary(arrow_type)
        or types.is_fixed_size_binary(arrow_type)
    ):
        return "binary"
    if _is_nested(arrow_type):
        return "json"
    if types.is_dictionary(arrow_type):
        # A dictionary encodes how the column is stored, not what it holds.
        return _category(arrow_type.value_type)
    return "other"


def _is_nested(arrow_type: Any) -> bool:
    return bool(
        types.is_list(arrow_type)
        or types.is_large_list(arrow_type)
        or types.is_fixed_size_list(arrow_type)
        or types.is_struct(arrow_type)
        or types.is_map(arrow_type)
    )


def _encoder(arrow_type: Any) -> Callable[[Any], str | None]:
    """How one column's values become text, decided once for the column."""
    column_type = _column_type(arrow_type)
    if column_type.category == "json":
        # A nested value arrives as Python containers. It is serialised here
        # and compacted by the shared renderer, so JSON has one spelling
        # wherever it crosses the boundary (D23).
        def encode_nested(value: Any) -> str | None:
            if value is None:
                return None
            return encode_cell(json.dumps(value, separators=(",", ":"), default=_plain), column_type)

        return encode_nested

    def encode(value: Any) -> str | None:
        return encode_cell(value, column_type)

    return encode


def _plain(value: Any) -> str:
    """A value inside a nested one that JSON has no spelling for."""
    if isinstance(value, bytes | bytearray):
        return f"0x{bytes(value).hex().upper()}"
    return str(value)


def _compression(metadata: Any) -> list[str]:
    """The codecs of the first row group, distinct and in column order.

    The first group rather than every one: a file may hold thousands, and a
    per-column codec that changes between groups is a curiosity nobody reads a
    catalog to discover.
    """
    if int(metadata.num_row_groups) == 0:
        return []
    group = metadata.row_group(0)
    codecs: list[str] = []
    for index in range(int(group.num_columns)):
        codec = str(group.column(index).compression)
        if codec not in codecs:
            codecs.append(codec)
    return codecs
