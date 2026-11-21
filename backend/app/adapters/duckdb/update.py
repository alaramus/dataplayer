"""Changing the rows of a DuckDB table, checked against what was read (D395).

Every change is one transaction: a row is read by its handle, digested the way
its page showed it, and changed only if the digest is the one the handle
carries; `RETURNING` hands back the row as it was written. A second writer of
the same row is refused by DuckDB itself as a conflict.

Any failed statement aborts a DuckDB transaction (D393), so values are not
tried one by one inside the change. A value DuckDB cannot read fails the whole
change; only then is each value tried alone in a temporary table, so the
refused cells are named.
"""

from collections.abc import Callable
from typing import Any

import duckdb

from app.adapters.duckdb.fetch import shape_of
from app.adapters.duckdb.inspection import RelationFacts
from app.adapters.duckdb.relation import DuckdbRelation
from app.adapters.duckdb.rows import (
    RowHandle,
    RowShape,
    decode_handle,
    key_match,
    selected,
    version_of,
    written,
)
from app.adapters.duckdb.session import DuckdbSession, classify
from app.adapters.duckdb.sql import SQL, Composable, Identifier
from app.adapters.fetch import FetchColumn
from app.adapters.protocol import AdapterError
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
from app.core.translation import N_, say

# What DuckDB says about a change it will not make, read for its kind and
# never shown: the sentence quotes the values (checked on 2.0.0).
_REFUSALS: list[tuple[str, str]] = [
    ("NOT NULL constraint", N_("A required value is missing")),
    ("Duplicate key", N_("Another row already has that value where values must be unique")),
    ("CHECK constraint", N_("The value breaks a check of the table")),
]
_MISSING_TARGET = ("does not exist in the referenced table", N_("The value refers to a row that does not exist"))
_STILL_REFERENCED = ("is still referenced", N_("Other rows refer to this one"))
# DuckDB carries out a change to a key or unique column as a delete and an
# insert, so a row others refer to cannot have one changed (checked on 2.0.0).
_REFERENCED_KEY = (
    "is still referenced",
    N_("DuckDB cannot change a key or unique column of a row other rows refer to"),
)
WRITING = [*_REFUSALS, _MISSING_TARGET, _REFERENCED_KEY]
DELETING = [_STILL_REFERENCED, *_REFUSALS]

_PROBE = "dp_value_probe"


class _Unreadable(Exception):
    """DuckDB could not read a value as its column's type."""


def _refusal(exc: duckdb.Error, refusals: list[tuple[str, str]]) -> str | None:
    text = str(exc)
    if isinstance(exc, duckdb.ConstraintException):
        named = next((message for found, message in refusals if found in text), None)
        return say(named) if named is not None else say("The source rejected the change")
    return None


async def _write[T](
    session: DuckdbSession,
    work: Callable[[duckdb.DuckDBPyConnection], T],
    refusals: list[tuple[str, str]],
) -> T:
    """Run `work` as one transaction, committed when it returns."""

    def job(connection: duckdb.DuckDBPyConnection) -> T:
        connection.execute("BEGIN")
        try:
            answer = work(connection)
        except BaseException:
            try:
                connection.execute("ROLLBACK")
            except duckdb.TransactionException:
                pass
            raise
        connection.execute("COMMIT")
        return answer

    handle = await session.handle()
    try:
        return await handle.call(job)
    except (duckdb.ConversionException, duckdb.InvalidInputException, duckdb.OutOfRangeException):
        raise _Unreadable from None
    except duckdb.TransactionException as exc:
        if "onflict" in str(exc):
            raise RowConflict from None
        error_kind, message = classify(exc, fallback_message=N_("Update failed"))
        raise AdapterError(error_kind, message) from None
    except duckdb.Error as exc:
        named = _refusal(exc, refusals)
        if named is not None:
            raise ValueError(named) from None
        error_kind, message = classify(exc, fallback_message=N_("Update failed"))
        raise AdapterError(error_kind, message) from None
    finally:
        await handle.close()


async def _unreadable(
    session: DuckdbSession, facts: RelationFacts, items: list[tuple[str, FetchColumn]]
) -> list[int]:
    """The positions of the values DuckDB cannot read as their column's type.

    Each value goes into a temporary table with the target's own column types,
    in a statement of its own outside any transaction: DuckDB's conversion
    decides, and a refusal aborts only that one statement.
    """
    names = list(dict.fromkeys(column.name for _, column in items))
    probe = Identifier(_PROBE)
    made = SQL("CREATE OR REPLACE TEMP TABLE {} AS SELECT {} FROM {} LIMIT 0").format(
        probe,
        SQL(", ").join(Identifier(name) for name in names),
        Identifier(facts.schema, facts.name),
    )

    def work(connection: duckdb.DuckDBPyConnection) -> list[int]:
        connection.execute(made.text())
        refused: list[int] = []
        try:
            for index, (value, column) in enumerate(items):
                statement = SQL("INSERT INTO {} ({}) VALUES (?)").format(
                    probe, Identifier(column.name)
                )
                try:
                    connection.execute(statement.text(), [written(value, column.type)])
                except duckdb.Error:
                    refused.append(index)
        finally:
            connection.execute(SQL("DROP TABLE IF EXISTS {}").format(probe).text())
        return refused

    handle = await session.handle()
    try:
        return await handle.call(work)
    finally:
        await handle.close()


def _row(raw: tuple[Any, ...], shape: RowShape) -> UpdatedRow:
    cells = [None if value is None else str(value) for value in raw]
    renewed = shape.handle_of(cells)
    if renewed is None:
        raise RowConflict
    return UpdatedRow(row_handle=renewed, values=cells)


def _checked(
    connection: duckdb.DuckDBPyConnection,
    facts: RelationFacts,
    shape: RowShape,
    handle: RowHandle,
) -> None:
    """Refuse a change to a row somebody changed after it was read."""
    params: list[object] = []
    statement = SQL("SELECT {} FROM {} WHERE {} LIMIT 2").format(
        selected(shape),
        Identifier(facts.schema, facts.name),
        key_match(shape, handle.keys, params),
    )
    rows = connection.execute(statement.text(), params).fetchall()
    if len(rows) != 1:
        raise RowConflict
    cells = [None if value is None else str(value) for value in rows[0]]
    if version_of(cells) != handle.version:
        raise RowConflict


def _changed(
    connection: duckdb.DuckDBPyConnection,
    facts: RelationFacts,
    shape: RowShape,
    handle_value: str,
    cells: list[tuple[FetchColumn, str | None]],
) -> UpdatedRow:
    handle = decode_handle(handle_value, shape)
    _checked(connection, facts, shape, handle)
    params: list[object] = [written(value, column.type) for column, value in cells]
    assignments = SQL(", ").join(
        SQL("{} = ?").format(Identifier(column.name)) for column, _ in cells
    )
    statement = SQL("UPDATE {} SET {} WHERE {} RETURNING {}").format(
        Identifier(facts.schema, facts.name),
        assignments,
        key_match(shape, handle.keys, params),
        selected(shape),
    )
    rows = connection.execute(statement.text(), params).fetchall()
    if len(rows) != 1:
        raise RowConflict
    return _row(tuple(rows[0]), shape)


class DuckdbUpdate:
    def __init__(self, session: DuckdbSession, relation: DuckdbRelation) -> None:
        self._session = session
        self._relation = relation

    async def _shape(self, node_id: str) -> tuple[RelationFacts, RowShape]:
        facts = await self._relation.facts(node_id, structure=False)
        return facts, shape_of(facts)

    @staticmethod
    def _column(shape: RowShape, name: str, *, editing: bool) -> FetchColumn:
        column = next((column for column in shape.columns if column.name == name), None)
        if column is None:
            raise ValueError(say('Relation has no column "{column}"', column=name))
        if editing and not column.editable:
            raise ValueError(say('Column "{column}" cannot be edited', column=name))
        if not editing and not column.insertable:
            raise ValueError(say('Column "{column}" cannot be inserted', column=name))
        return column

    async def update_cell(self, request: UpdateCellRequest) -> UpdateCellResult:
        facts, shape = await self._shape(request.node_id)
        if not shape.update_supported:
            raise ValueError(shape.update_reason or say("This relation cannot be edited"))
        column = self._column(shape, request.column, editing=True)
        decode_handle(request.row_handle, shape)
        try:
            row = await _write(
                self._session,
                lambda connection: _changed(
                    connection, facts, shape, request.row_handle, [(column, request.value)]
                ),
                WRITING,
            )
        except _Unreadable:
            raise ValueError(say("That value cannot be read as {sql}", sql=column.type.sql)) from None
        return UpdateCellResult(values=row.values, row_handle=row.row_handle)

    async def update_cells(self, request: UpdateCellsRequest) -> UpdateCellsResult:
        facts, shape = await self._shape(request.node_id)
        if not shape.update_supported:
            raise ValueError(shape.update_reason or say("This relation cannot be edited"))
        edits: list[list[tuple[FetchColumn, str | None]]] = []
        checked: list[tuple[str, FetchColumn]] = []
        places: list[tuple[int, str]] = []
        for index, row in enumerate(request.rows):
            decode_handle(row.row_handle, shape)
            cells = [
                (self._column(shape, cell.column, editing=True), cell.value) for cell in row.cells
            ]
            edits.append(cells)
            for column, value in cells:
                if value is not None:
                    checked.append((value, column))
                    places.append((index, column.name))

        def work(connection: duckdb.DuckDBPyConnection) -> UpdateCellsResult:
            return CellsUpdated(
                rows=[
                    _changed(connection, facts, shape, row.row_handle, cells)
                    for row, cells in zip(request.rows, edits, strict=True)
                ]
            )

        try:
            return await _write(self._session, work, WRITING)
        except _Unreadable:
            rejected = await _unreadable(self._session, facts, checked)
            if not rejected:
                raise ValueError(say("The source rejected the change")) from None
            return CellsRejected(
                cells=[RejectedCell(row=places[at][0], column=places[at][1]) for at in rejected]
            )

    async def insert_row(self, request: InsertRowRequest) -> InsertRowResult:
        facts, shape = await self._shape(request.node_id)
        if not shape.insert_supported:
            raise ValueError(shape.insert_reason or say("This relation cannot accept rows"))
        given = [
            (self._column(shape, item.column, editing=False), item.value) for item in request.values
        ]
        supplied = {column.name for column, _ in given}
        missing = [
            column.name
            for column in shape.columns
            if column.insert_required and column.name not in supplied
        ]
        if missing:
            raise ValueError(
                say("Required columns were not supplied: {columns}", columns=", ".join(missing))
            )
        target = Identifier(facts.schema, facts.name)
        if given:
            statement = SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING {}").format(
                target,
                SQL(", ").join(Identifier(column.name) for column, _ in given),
                SQL(", ").join(SQL("?") for _ in given),
                selected(shape),
            )
        else:
            statement = SQL("INSERT INTO {} DEFAULT VALUES RETURNING {}").format(
                target, selected(shape)
            )
        params = [written(value, column.type) for column, value in given]

        def work(connection: duckdb.DuckDBPyConnection) -> list[str | None]:
            rows = connection.execute(statement.text(), params).fetchall()
            return [None if value is None else str(value) for value in rows[0]]

        try:
            cells = await _write(self._session, work, WRITING)
        except _Unreadable:
            raise ValueError(say("The source rejected the new value")) from None
        return InsertRowResult(values=cells, row_handle=shape.handle_of(cells))

    async def insert_rows(
        self, request: InsertRowsRequest, *, skipping: bool = False
    ) -> InsertRowsResult:
        """A block of rows; `skipping` leaves out what a unique key holds (D313)."""
        facts, shape = await self._shape(request.node_id)
        if not shape.insert_supported:
            raise ValueError(shape.insert_reason or say("This relation cannot accept rows"))
        targets = [self._column(shape, name, editing=False) for name in request.columns]
        checked: list[tuple[str, FetchColumn]] = []
        places: list[tuple[int, str, str]] = []
        for index, row in enumerate(request.rows):
            for column, value in zip(targets, row, strict=True):
                if value is not None:
                    checked.append((value, column))
                    places.append((index, column.name, value))
        rows = [
            [written(value, column.type) for column, value in zip(targets, row, strict=True)]
            for row in request.rows
        ]
        statement = SQL("INSERT INTO {} ({}) VALUES ({}){}").format(
            Identifier(facts.schema, facts.name),
            SQL(", ").join(Identifier(column.name) for column in targets),
            SQL(", ").join(SQL("?") for _ in targets),
            SQL(" ON CONFLICT DO NOTHING" if skipping else ""),
        )

        def work(connection: duckdb.DuckDBPyConnection) -> int:
            inserted = 0
            for row in rows:
                answer = connection.execute(statement.text(), row).fetchone()
                inserted += int(answer[0]) if answer is not None else 0
            return inserted

        try:
            inserted = await _write(self._session, work, WRITING)
        except _Unreadable:
            rejected = await _unreadable(self._session, facts, [(v, c) for v, c in checked])
            if not rejected:
                raise ValueError(say("The source rejected the change")) from None
            return ValuesRejected(
                cells=[
                    RejectedValue(row=places[at][0], column=places[at][1], value=places[at][2][:100])
                    for at in rejected[:200]
                ]
            )
        return RowsInserted(inserted=inserted if skipping else len(rows))

    async def delete_rows(self, request: DeleteRowsRequest) -> DeleteRowsResult:
        facts, shape = await self._shape(request.node_id)
        if not shape.update_supported:
            raise ValueError(shape.update_reason or say("This relation cannot delete rows"))
        if len(set(request.row_handles)) != len(request.row_handles):
            raise ValueError(say("A row may be deleted only once"))
        handles = [decode_handle(value, shape) for value in request.row_handles]

        def work(connection: duckdb.DuckDBPyConnection) -> int:
            for handle in handles:
                _checked(connection, facts, shape, handle)
            params: list[object] = []
            matches: list[Composable] = [
                SQL("({})").format(key_match(shape, handle.keys, params)) for handle in handles
            ]
            statement = SQL("DELETE FROM {} WHERE {}").format(
                Identifier(facts.schema, facts.name), SQL(" OR ").join(matches)
            )
            answer = connection.execute(statement.text(), params).fetchone()
            deleted = int(answer[0]) if answer is not None else 0
            if deleted != len(handles):
                raise RowConflict
            return deleted

        try:
            deleted = await _write(self._session, work, DELETING)
        except _Unreadable:
            raise RowConflict from None
        return DeleteRowsResult(deleted=deleted)
