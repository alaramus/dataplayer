"""Reading a Parquet file: its declared schema, and a bounded page of rows.

A columnar file states its own columns, their types and its exact row count, so
none of it is guessed (D51). The footer is metadata and is read without
decompressing anything; a page is streamed from the row groups it falls in, so
the groups before the offset are never touched and one enormous group is not
held whole.
"""

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from app.adapters.dataset import ParquetDataset
from app.adapters.fetch import FetchColumn, Filter
from app.adapters.file.arrow import column_type, encoder
from app.adapters.file.readers import Page, matcher, select
from app.adapters.relation import Column

# The same ceiling the workbook reader has, for the same reason: a page of a
# thousand rows across an unbounded number of columns is bounded by nothing.
MAX_COLUMNS = 1024

# How many rows come out of the file at a time while it is being searched. Only
# the filtered path uses it: an unfiltered page knows which row groups it wants
# and never looks at the others.
SCAN_BATCH = 1024


class NotParquet(ValueError):
    """The bytes under a `.parquet` name are not a Parquet file."""


def read_page(
    path: Path, limit: int, offset: int, filters: Sequence[Filter] = ()
) -> Page:
    """One bounded page, read from the row groups it falls in. Blocking.

    A filter gives up the row-group arithmetic and reads the file through: the
    metadata says how many rows a group holds, not how many of them match
    (D109). Without one, the page still touches only the groups it falls in.
    """
    with _opened(path) as file:
        schema = file.schema_arrow
        columns = _fetch_columns(schema)
        match = matcher(filters, [column.name for column in columns])
        if not match.tests:
            total = int(file.metadata.num_rows)
            rows = _read_rows(file, schema, limit, offset)
            return Page(
                columns=columns,
                rows=rows,
                has_more=offset + len(rows) < total,
                positions=list(range(offset, offset + len(rows))),
            )
        rows, positions, has_more = select(
            _scanned(file, schema), limit, offset, match
        )

    return Page(
        columns=columns,
        rows=rows,
        has_more=has_more,
        positions=positions,
    )


def _scanned(file: Any, schema: Any) -> Iterator[list[str | None]]:
    """Every row of the file as text, a batch at a time. Blocking."""
    encoders = [encoder(field.type) for field in schema]
    if not encoders:
        return
    for batch in file.iter_batches(batch_size=SCAN_BATCH):
        yield from _rows_of(batch, encoders)


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
            type=column_type(field.type),
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

    encoders = [encoder(field.type) for field in schema]
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
        FetchColumn(name=field.name, type=column_type(field.type), nullable=bool(field.nullable))
        for field in schema
    ]


def _guard_width(schema: Any) -> None:
    if len(schema) > MAX_COLUMNS:
        raise ValueError(
            f"This file has more than {MAX_COLUMNS} columns, "
            "which is more than one page may carry"
        )


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
