"""Atomic row changes for delimited files in personal storage."""

import base64
import csv
import json
from dataclasses import dataclass

from anyio import to_thread

from app.adapters.column_changes import (
    AddColumnRequest,
    ColumnChangeResult,
    DropColumnRequest,
    RenameColumnRequest,
)
from app.adapters.delimited import delimiter_of, fit, usable_names
from app.adapters.explorer.formats import format_of
from app.adapters.explorer.members import resolve_node
from app.adapters.explorer.storage import Place, Storage, VersionChanged
from app.adapters.update import (
    CellsUpdated,
    DeleteRowsRequest,
    DeleteRowsResult,
    InsertRowRequest,
    InsertRowResult,
    InsertRowsRequest,
    InsertRowsResult,
    RowConflict,
    RowsInserted,
    UpdateCellRequest,
    UpdateCellResult,
    UpdateCellsRequest,
    UpdateCellsResult,
    UpdatedRow,
)
from app.core.config import settings
from app.core.translation import say


@dataclass
class CsvTable:
    header: list[str]
    names: list[str]
    rows: list[list[str | None]]
    delimiter: str
    version: str


def encode_handle(row: int, version: str) -> str:
    raw = json.dumps([row, version], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_handle(value: str) -> tuple[int, str]:
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded).decode())
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(say("The row handle is not valid for this file")) from exc
    if (
        not isinstance(decoded, list)
        or len(decoded) != 2
        or not isinstance(decoded[0], int)
        or decoded[0] < 0
        or not isinstance(decoded[1], str)
    ):
        raise ValueError(say("The row handle is not valid for this file"))
    return decoded[0], decoded[1]


class ExplorerTableChanges:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    async def update_cell(self, request: UpdateCellRequest) -> UpdateCellResult:
        return await to_thread.run_sync(self._update_cell, request)

    async def update_cells(self, request: UpdateCellsRequest) -> UpdateCellsResult:
        return await to_thread.run_sync(self._update_cells, request)

    async def insert_row(self, request: InsertRowRequest) -> InsertRowResult:
        return await to_thread.run_sync(self._insert_row, request)

    async def insert_rows(self, request: InsertRowsRequest) -> InsertRowsResult:
        return await to_thread.run_sync(self._insert_rows, request)

    async def delete_rows(self, request: DeleteRowsRequest) -> DeleteRowsResult:
        return await to_thread.run_sync(self._delete_rows, request)

    async def add_column(self, request: AddColumnRequest) -> ColumnChangeResult:
        return await to_thread.run_sync(self._add_column, request)

    async def drop_column(self, request: DropColumnRequest) -> ColumnChangeResult:
        return await to_thread.run_sync(self._drop_column, request)

    async def rename_column(
        self, request: RenameColumnRequest
    ) -> ColumnChangeResult:
        return await to_thread.run_sync(self._rename_column, request)

    def _place(self, node_id: str) -> Place:
        resolved = resolve_node(self._storage, node_id)
        if resolved.member is not None or format_of(resolved.name) != "delimited":
            raise ValueError(say("Only a CSV or TSV file on disk can be edited as rows"))
        if resolved.entry is None or resolved.entry.is_directory:
            raise ValueError(say("No such file: {node_id}", node_id=node_id))
        if resolved.entry.size_bytes > settings.MAX_UPLOAD_BYTES:
            raise ValueError(say("This file is too large to rewrite safely"))
        return resolved.place

    def _read(self, node_id: str) -> tuple[Place, CsvTable]:
        place = self._place(node_id)
        version = self._storage.version(place)
        with (
            self._storage.local_file(place) as path,
            path.open("r", encoding="utf-8", errors="replace", newline="") as handle,
        ):
            first_line = handle.readline()
            handle.seek(0)
            delimiter = delimiter_of(place.name, first_line)
            reader = csv.reader(handle, delimiter=delimiter)
            header = next(reader, None)
            if header is None:
                return place, CsvTable([], [], [], delimiter, version)
            names = usable_names(header)
            rows = [fit(row, len(names)) for row in reader]
        if self._storage.version(place) != version:
            raise RowConflict
        return place, CsvTable(header, names, rows, delimiter, version)

    @staticmethod
    def _column(table: CsvTable, name: str) -> int:
        try:
            return table.names.index(name)
        except ValueError:
            raise ValueError(say('File has no column "{name}"', name=name)) from None

    @staticmethod
    def _row(table: CsvTable, handle: str) -> int:
        row, version = decode_handle(handle)
        if version != table.version or row >= len(table.rows):
            raise RowConflict
        return row

    def _update_cell(self, request: UpdateCellRequest) -> UpdateCellResult:
        place, table = self._read(request.node_id)
        row = self._row(table, request.row_handle)
        table.rows[row][self._column(table, request.column)] = request.value
        version = self._write(place, table)
        return UpdateCellResult(values=table.rows[row], row_handle=encode_handle(row, version))

    def _update_cells(self, request: UpdateCellsRequest) -> UpdateCellsResult:
        place, table = self._read(request.node_id)
        changed: list[int] = []
        for edit in request.rows:
            row = self._row(table, edit.row_handle)
            changed.append(row)
            for cell in edit.cells:
                table.rows[row][self._column(table, cell.column)] = cell.value
        version = self._write(place, table)
        return CellsUpdated(
            rows=[
                UpdatedRow(
                    values=table.rows[row], row_handle=encode_handle(row, version)
                )
                for row in changed
            ]
        )

    def _insert_row(self, request: InsertRowRequest) -> InsertRowResult:
        place, table = self._read(request.node_id)
        values: list[str | None] = [None] * len(table.names)
        for item in request.values:
            values[self._column(table, item.column)] = item.value
        table.rows.append(values)
        version = self._write(place, table)
        return InsertRowResult(
            values=values, row_handle=encode_handle(len(table.rows) - 1, version)
        )

    def _insert_rows(self, request: InsertRowsRequest) -> InsertRowsResult:
        place, table = self._read(request.node_id)
        positions = [self._column(table, name) for name in request.columns]
        for incoming in request.rows:
            values: list[str | None] = [None] * len(table.names)
            for position, value in zip(positions, incoming, strict=True):
                values[position] = value
            table.rows.append(values)
        self._write(place, table)
        return RowsInserted(inserted=len(request.rows))

    def _delete_rows(self, request: DeleteRowsRequest) -> DeleteRowsResult:
        place, table = self._read(request.node_id)
        rows = [self._row(table, handle) for handle in request.row_handles]
        if len(rows) != len(set(rows)):
            raise ValueError(say("A row may be deleted only once"))
        for row in sorted(rows, reverse=True):
            table.rows.pop(row)
        self._write(place, table)
        return DeleteRowsResult(deleted=len(rows))

    def _add_column(self, request: AddColumnRequest) -> ColumnChangeResult:
        place, table = self._read(request.node_id)
        if request.type_code != "text":
            raise ValueError(say("A delimited file can add only a text column"))
        if request.name in table.names:
            raise ValueError(
                say('File already has a column named "{name}"', name=request.name)
            )
        table.header.append(request.name)
        table.names.append(request.name)
        for row in table.rows:
            row.append(None)
        self._write(place, table)
        return ColumnChangeResult(name=request.name)

    def _drop_column(self, request: DropColumnRequest) -> ColumnChangeResult:
        place, table = self._read(request.node_id)
        if len(table.names) == 1:
            raise ValueError(say("A delimited file must keep at least one column"))
        position = self._column(table, request.name)
        table.header.pop(position)
        table.names.pop(position)
        for row in table.rows:
            row.pop(position)
        self._write(place, table)
        return ColumnChangeResult(name=request.name)

    def _rename_column(self, request: RenameColumnRequest) -> ColumnChangeResult:
        place, table = self._read(request.node_id)
        if request.new_name in table.names:
            raise ValueError(
                say('File already has a column named "{name}"', name=request.new_name)
            )
        position = self._column(table, request.name)
        table.header[position] = request.new_name
        table.names[position] = request.new_name
        self._write(place, table)
        return ColumnChangeResult(name=request.new_name)

    def _write(self, place: Place, table: CsvTable) -> str:
        """Write the whole file beside itself, then replace it in one step.

        Only while it is still the version that was read: a row handle carries
        that version, and a write over somebody else's is a conflict to say,
        not a thing to do (D48).
        """
        with self._storage.staged(place, prefix=".csv-edit-") as staged:
            with staged.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, delimiter=table.delimiter, lineterminator="\n")
                writer.writerow(table.header)
                writer.writerows(table.rows)
            try:
                self._storage.publish(
                    staged, place, replace=True, expected_version=table.version
                )
            except VersionChanged:
                raise RowConflict from None
        return self._storage.version(place)
