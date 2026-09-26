"""Editing a table declared over Redis as its rows (D173).

The grid's editing contract (D25, D26), answered by the hashes of a folder: a
cell is one field of one hash, a new row is a new hash, a deleted row is a
deleted key. What stands in for a version is the fingerprint of what the page
showed, as for any Redis edit (`update.py`); nothing is written until every
row and value has been checked, and a batch is written in one transaction.

An empty value is no field, which is how the table shows a field a hash
lacks: emptying a cell removes the field, and a new row keeps only the fields
given something.
"""

from collections.abc import Mapping, Sequence

import redis.asyncio as redis

from app.adapters.declared_tables import DeclaredTable
from app.adapters.redis.keyspace import PlaceRef, is_direct
from app.adapters.redis.row_handle import decode_row_handle
from app.adapters.redis.session import RedisSession, text
from app.adapters.redis.shapes import KEY_COLUMN
from app.adapters.redis.tables import (
    TABLE_ROW,
    RedisTables,
    reads_as,
    table_fingerprint,
    table_row_handle,
)
from app.adapters.redis.update import MAX_VALUE_BYTES
from app.adapters.update import (
    CellsRejected,
    CellsUpdated,
    DeleteRowsRequest,
    DeleteRowsResult,
    InsertRowRequest,
    InsertRowResult,
    InsertRowsRequest,
    InsertRowsResult,
    RejectedCell,
    RejectedValue,
    RowConflict,
    RowsInserted,
    UpdateCellRequest,
    UpdateCellResult,
    UpdateCellsRequest,
    UpdateCellsResult,
    UpdatedRow,
    ValuesRejected,
)

KEY_IS_THE_ROW = "The key is where the row lives; it is not edited"
LAST_FIELD = (
    "Emptying the last field would remove the key; delete the row instead"
)
TYPE_WORDS = {
    "number": "a number",
    "boolean": "true or false",
    "datetime": "a date and time",
}

type Row = list[str | None]


class RedisTableUpdate:
    """Changing, adding and removing the rows of a declared table."""

    def __init__(self, session: RedisSession, tables: RedisTables) -> None:
        self._session = session
        self._tables = tables

    async def update_cell(self, request: UpdateCellRequest) -> UpdateCellResult:
        place, table = self._tables.declared(request.node_id)
        field = _field(table, request.column)
        value = _given(request.value)
        if value is not None and not _fits(table, field, value):
            raise ValueError(_wrong_type(table, field))
        key = decode_row_handle(request.row_handle).identity
        async with self._session.connection(place.database) as client:
            current, length = await _as_read(client, place, table, request.row_handle)
            after = _with(table, current, {field: value})
            _keeps_a_field(current, after, length)
            await _written(client, place, table, [(key, current, after)])
        return UpdateCellResult(
            values=[key, *after], row_handle=table_row_handle(key, after)
        )

    async def update_cells(self, request: UpdateCellsRequest) -> UpdateCellsResult:
        """A block of cells over several rows, checked whole and written at once."""
        place, table = self._tables.declared(request.node_id)
        rejected: list[RejectedCell] = []
        for index, row in enumerate(request.rows):
            for cell in row.cells:
                field = _field(table, cell.column)
                value = _given(cell.value)
                if value is not None and not _fits(table, field, value):
                    rejected.append(RejectedCell(row=index, column=cell.column))
        if rejected:
            return CellsRejected(cells=rejected)
        changes: list[tuple[str, Row, Row]] = []
        async with self._session.connection(place.database) as client:
            for row in request.rows:
                key = decode_row_handle(row.row_handle).identity
                current, length = await _as_read(client, place, table, row.row_handle)
                after = _with(
                    table, current, {cell.column: _given(cell.value) for cell in row.cells}
                )
                _keeps_a_field(current, after, length)
                changes.append((key, current, after))
            await _written(client, place, table, changes)
        return CellsUpdated(
            rows=[
                UpdatedRow(row_handle=table_row_handle(key, after), values=[key, *after])
                for key, _, after in changes
            ]
        )

    async def insert_row(self, request: InsertRowRequest) -> InsertRowResult:
        place, table = self._tables.declared(request.node_id)
        supplied = {item.column: item.value for item in request.values}
        key, values = _new_row(table, supplied)
        for field, value in zip(_fields(table), values, strict=True):
            if value is not None and not _fits(table, field, value):
                raise ValueError(_wrong_type(table, field))
        async with self._session.connection(place.database) as client:
            await _free(client, place, [key])
            await _written(client, place, table, [(key, [None] * len(values), values)])
        return InsertRowResult(values=[key, *values], row_handle=table_row_handle(key, values))

    async def insert_rows(self, request: InsertRowsRequest) -> InsertRowsResult:
        """Every row checked, and every key found free, before one is written."""
        place, table = self._tables.declared(request.node_id)
        known = {KEY_COLUMN, *_fields(table)}
        unknown = [column for column in request.columns if column not in known]
        if unknown:
            raise ValueError(f'This table has no column "{unknown[0]}"')
        if KEY_COLUMN not in request.columns:
            raise ValueError("Rows added to a Redis table need a key")
        rejected: list[RejectedValue] = []
        rows: list[tuple[str, Row]] = []
        seen: set[str] = set()
        for index, raw in enumerate(request.rows):
            supplied = dict(zip(request.columns, raw, strict=True))
            key = _given(supplied.get(KEY_COLUMN))
            if key is None or not is_direct(f"{place.prefix}{key}", place.prefix) or key in seen:
                rejected.append(RejectedValue(row=index, column=KEY_COLUMN, value=key))
                continue
            seen.add(key)
            values: Row = [_given(supplied.get(field)) for field in _fields(table)]
            for field, value in zip(_fields(table), values, strict=True):
                if value is not None and not _fits(table, field, value):
                    rejected.append(RejectedValue(row=index, column=field, value=value))
            if all(value is None for value in values):
                raise ValueError(
                    f"Row {index + 1} gives no field a value; Redis keeps no empty hash"
                )
            rows.append((key, values))
        if rejected:
            return ValuesRejected(cells=rejected)
        async with self._session.connection(place.database) as client:
            await _free(client, place, [key for key, _ in rows])
            await _written(
                client,
                place,
                table,
                [(key, [None] * len(values), values) for key, values in rows],
            )
        return RowsInserted(inserted=len(rows))

    async def delete_rows(self, request: DeleteRowsRequest) -> DeleteRowsResult:
        """Their keys, all of them or none: each is checked before any goes."""
        place, table = self._tables.declared(request.node_id)
        names: list[str] = []
        async with self._session.connection(place.database) as client:
            for raw in request.row_handles:
                await _as_read(client, place, table, raw)
                names.append(f"{place.prefix}{decode_row_handle(raw).identity}")
            await client.delete(*names)
        return DeleteRowsResult(deleted=len(names))


def _fields(table: DeclaredTable) -> list[str]:
    return [column.name for column in table.columns]


def _field(table: DeclaredTable, column: str) -> str:
    if column == KEY_COLUMN:
        raise ValueError(KEY_IS_THE_ROW)
    if column not in _fields(table):
        raise ValueError(f'This table has no column "{column}"')
    return column


def _given(value: str | None) -> str | None:
    """An empty value is no field (D173)."""
    if value is None or value == "":
        return None
    if len(value.encode("utf-8")) > MAX_VALUE_BYTES:
        raise ValueError(f"A value written here is at most {MAX_VALUE_BYTES // 1024} KB")
    return value


def _fits(table: DeclaredTable, field: str, value: str) -> bool:
    declared = next(column for column in table.columns if column.name == field)
    return reads_as(declared.type, value)


def _wrong_type(table: DeclaredTable, field: str) -> str:
    declared = next(column for column in table.columns if column.name == field)
    return f'"{field}" takes {TYPE_WORDS.get(declared.type, "text")}'


def _with(table: DeclaredTable, current: Row, edits: Mapping[str, str | None]) -> Row:
    return [
        edits[field] if field in edits else held
        for field, held in zip(_fields(table), current, strict=True)
    ]


def _keeps_a_field(current: Row, after: Row, length: int) -> None:
    """Refuse an edit that would leave the hash empty, which Redis deletes."""
    undeclared = length - sum(value is not None for value in current)
    if undeclared + sum(value is not None for value in after) == 0:
        raise ValueError(LAST_FIELD)


def _new_row(table: DeclaredTable, supplied: Mapping[str, str | None]) -> tuple[str, Row]:
    known = {KEY_COLUMN, *_fields(table)}
    unknown = [column for column in supplied if column not in known]
    if unknown:
        raise ValueError(f'This table has no column "{unknown[0]}"')
    key = _given(supplied.get(KEY_COLUMN))
    if key is None:
        raise ValueError("A new row needs a key")
    values: Row = [_given(supplied.get(field)) for field in _fields(table)]
    if all(value is None for value in values):
        raise ValueError("A new row needs a value for at least one field")
    return key, values


async def _as_read(
    client: redis.Redis, place: PlaceRef, table: DeclaredTable, raw_handle: str
) -> tuple[Row, int]:
    """The row as it stands, refused if it is not what was read; and the hash's size."""
    handle = decode_row_handle(raw_handle)
    name = f"{place.prefix}{handle.identity}"
    if handle.data_type != TABLE_ROW or not is_direct(name, place.prefix):
        raise RowConflict
    pipe = client.pipeline(transaction=False)
    pipe.type(name)
    pipe.hmget(name, _fields(table))
    pipe.hlen(name)
    kind, found, length = await pipe.execute(raise_on_error=False)
    if text(kind) != "hash" or not isinstance(found, list):
        raise RowConflict
    current: Row = [None if one is None else text(one) for one in found]
    if table_fingerprint(current) != handle.fingerprint:
        raise RowConflict
    return current, int(length)


async def _free(client: redis.Redis, place: PlaceRef, keys: Sequence[str]) -> None:
    """Every new key a name within the folder that nothing holds yet."""
    for key in keys:
        if not is_direct(f"{place.prefix}{key}", place.prefix):
            raise ValueError(f'"{key}" would lie in a folder below this table')
    pipe = client.pipeline(transaction=False)
    for key in keys:
        pipe.exists(f"{place.prefix}{key}")
    taken = [key for key, held in zip(keys, await pipe.execute(), strict=True) if held]
    if len(taken) == 1:
        raise ValueError(f'"{taken[0]}" is already in this folder')
    if taken:
        raise ValueError(
            f'"{taken[0]}" and {len(taken) - 1} more are already in this folder'
        )


async def _written(
    client: redis.Redis,
    place: PlaceRef,
    table: DeclaredTable,
    changes: Sequence[tuple[str, Row, Row]],
) -> None:
    """Each hash as it will be, in one transaction: fields set, fields removed.

    Only what changed is written, so a field somebody else changed meanwhile
    is not put back to what this page showed.
    """
    async with client.pipeline(transaction=True) as pipe:
        for key, current, after in changes:
            name = f"{place.prefix}{key}"
            setting = {
                field: value
                for field, before, value in zip(_fields(table), current, after, strict=True)
                if value is not None and value != before
            }
            removing = [
                field
                for field, before, value in zip(_fields(table), current, after, strict=True)
                if value is None and before is not None
            ]
            if setting:
                pipe.hset(name, mapping=setting)
            if removing:
                pipe.hdel(name, *removing)
        await pipe.execute()
