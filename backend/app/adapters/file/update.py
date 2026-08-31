"""Atomic row changes for delimited files in personal storage."""

import base64
import csv
import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from anyio import to_thread

from app.adapters.column_changes import (
    AddColumnRequest,
    ColumnChangeResult,
    DropColumnRequest,
    RenameColumnRequest,
)
from app.adapters.delimited import delimiter_of, fit, usable_names
from app.adapters.file.formats import format_of
from app.adapters.file.members import resolve_node
from app.adapters.file.session import FileSession
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


@dataclass
class CsvTable:
    header: list[str]
    names: list[str]
    rows: list[list[str | None]]
    delimiter: str
    version: str


def file_version(path: Path) -> str:
    facts = path.stat()
    return f"{facts.st_mtime_ns}:{facts.st_size}"


def encode_handle(row: int, version: str) -> str:
    raw = json.dumps([row, version], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_handle(value: str) -> tuple[int, str]:
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded).decode())
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("The row handle is not valid for this file") from exc
    if (
        not isinstance(decoded, list)
        or len(decoded) != 2
        or not isinstance(decoded[0], int)
        or decoded[0] < 0
        or not isinstance(decoded[1], str)
    ):
        raise ValueError("The row handle is not valid for this file")
    return decoded[0], decoded[1]


class FileTableChanges:
    def __init__(self, session: FileSession) -> None:
        self._session = session

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

    def _path(self, node_id: str) -> Path:
        resolved = resolve_node(self._session, node_id)
        if resolved.member is not None or format_of(resolved.path.name) != "delimited":
            raise ValueError("Only a CSV or TSV file on disk can be edited as rows")
        if not resolved.path.is_file():
            raise ValueError(f"No such file: {node_id}")
        if resolved.path.stat().st_size > settings.MAX_UPLOAD_BYTES:
            raise ValueError("This file is too large to rewrite safely")
        return resolved.path

    def _read(self, node_id: str) -> tuple[Path, CsvTable]:
        path = self._path(node_id)
        version = file_version(path)
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            first_line = handle.readline()
            handle.seek(0)
            delimiter = delimiter_of(path.name, first_line)
            reader = csv.reader(handle, delimiter=delimiter)
            header = next(reader, None)
            if header is None:
                return path, CsvTable([], [], [], delimiter, version)
            names = usable_names(header)
            rows = [fit(row, len(names)) for row in reader]
        if file_version(path) != version:
            raise RowConflict
        return path, CsvTable(header, names, rows, delimiter, version)

    @staticmethod
    def _column(table: CsvTable, name: str) -> int:
        try:
            return table.names.index(name)
        except ValueError:
            raise ValueError(f'File has no column "{name}"') from None

    @staticmethod
    def _row(table: CsvTable, handle: str) -> int:
        row, version = decode_handle(handle)
        if version != table.version or row >= len(table.rows):
            raise RowConflict
        return row

    def _update_cell(self, request: UpdateCellRequest) -> UpdateCellResult:
        path, table = self._read(request.node_id)
        row = self._row(table, request.row_handle)
        table.rows[row][self._column(table, request.column)] = request.value
        version = self._write(path, table)
        return UpdateCellResult(values=table.rows[row], row_handle=encode_handle(row, version))

    def _update_cells(self, request: UpdateCellsRequest) -> UpdateCellsResult:
        path, table = self._read(request.node_id)
        changed: list[int] = []
        for edit in request.rows:
            row = self._row(table, edit.row_handle)
            changed.append(row)
            for cell in edit.cells:
                table.rows[row][self._column(table, cell.column)] = cell.value
        version = self._write(path, table)
        return CellsUpdated(
            rows=[
                UpdatedRow(
                    values=table.rows[row], row_handle=encode_handle(row, version)
                )
                for row in changed
            ]
        )

    def _insert_row(self, request: InsertRowRequest) -> InsertRowResult:
        path, table = self._read(request.node_id)
        values: list[str | None] = [None] * len(table.names)
        for item in request.values:
            values[self._column(table, item.column)] = item.value
        table.rows.append(values)
        version = self._write(path, table)
        return InsertRowResult(
            values=values, row_handle=encode_handle(len(table.rows) - 1, version)
        )

    def _insert_rows(self, request: InsertRowsRequest) -> InsertRowsResult:
        path, table = self._read(request.node_id)
        positions = [self._column(table, name) for name in request.columns]
        for incoming in request.rows:
            values: list[str | None] = [None] * len(table.names)
            for position, value in zip(positions, incoming, strict=True):
                values[position] = value
            table.rows.append(values)
        self._write(path, table)
        return RowsInserted(inserted=len(request.rows))

    def _delete_rows(self, request: DeleteRowsRequest) -> DeleteRowsResult:
        path, table = self._read(request.node_id)
        rows = [self._row(table, handle) for handle in request.row_handles]
        if len(rows) != len(set(rows)):
            raise ValueError("A row may be deleted only once")
        for row in sorted(rows, reverse=True):
            table.rows.pop(row)
        self._write(path, table)
        return DeleteRowsResult(deleted=len(rows))

    def _add_column(self, request: AddColumnRequest) -> ColumnChangeResult:
        path, table = self._read(request.node_id)
        if request.type_code != "text":
            raise ValueError("A delimited file can add only a text column")
        if request.name in table.names:
            raise ValueError(f'File already has a column named "{request.name}"')
        table.header.append(request.name)
        table.names.append(request.name)
        for row in table.rows:
            row.append(None)
        self._write(path, table)
        return ColumnChangeResult(name=request.name)

    def _drop_column(self, request: DropColumnRequest) -> ColumnChangeResult:
        path, table = self._read(request.node_id)
        if len(table.names) == 1:
            raise ValueError("A delimited file must keep at least one column")
        position = self._column(table, request.name)
        table.header.pop(position)
        table.names.pop(position)
        for row in table.rows:
            row.pop(position)
        self._write(path, table)
        return ColumnChangeResult(name=request.name)

    def _rename_column(self, request: RenameColumnRequest) -> ColumnChangeResult:
        path, table = self._read(request.node_id)
        if request.new_name in table.names:
            raise ValueError(f'File already has a column named "{request.new_name}"')
        position = self._column(table, request.name)
        table.header[position] = request.new_name
        table.names[position] = request.new_name
        self._write(path, table)
        return ColumnChangeResult(name=request.new_name)

    @staticmethod
    def _write(path: Path, table: CsvTable) -> str:
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".csv-edit-")
        replacement = Path(temporary)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, delimiter=table.delimiter, lineterminator="\n")
                writer.writerow(table.header)
                writer.writerows(table.rows)
            if file_version(path) != table.version:
                raise RowConflict
            os.replace(replacement, path)
            previous_mtime = int(table.version.partition(":")[0])
            now = max(time.time_ns(), previous_mtime + 1)
            os.utime(path, ns=(now, now))
            return file_version(path)
        finally:
            replacement.unlink(missing_ok=True)
