"""Changing the rows of a SQLite table, checked against what was read (D254).

Every change is one transaction that takes the file's write lock with its
first statement (`SqliteSession.write`). A row is read by its handle, digested
the way its page showed it, and changed only if the digest is the one the
handle carries; `RETURNING` hands back the row as it was written.

Only a STRICT table refuses a value for its type; any other column takes what
it is given, converted by its affinity. A STRICT table's values are tried in a
temporary table of the same column types before anything is written, so a
paste lands whole or the refused cells are named.
"""

import sqlite3
from typing import Any

from app.adapters.fetch import FetchColumn
from app.adapters.sqlite.fetch import page_row, selected, shape_of
from app.adapters.sqlite.inspection import SCHEMA, RelationFacts
from app.adapters.sqlite.relation import SqliteRelation
from app.adapters.sqlite.rows import (
    RowHandle,
    RowShape,
    decode_handle,
    key_match,
    version_of,
    written,
)
from app.adapters.sqlite.session import SqliteSession
from app.adapters.sqlite.sql import SQL, Composable, Identifier
from app.adapters.sqlite.types import base_name
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

# SQLITE_CONSTRAINT_DATATYPE, a STRICT column's refusal, which the sqlite3
# module does not name.
_CONSTRAINT_DATATYPE = sqlite3.SQLITE_CONSTRAINT | (12 << 8)

# What SQLite says about a change it will not make, by extended result code.
_REFUSALS: dict[int, str] = {
    sqlite3.SQLITE_CONSTRAINT_NOTNULL: N_("A required value is missing"),
    sqlite3.SQLITE_CONSTRAINT_UNIQUE: N_(
        "Another row already has that value where values must be unique"
    ),
    sqlite3.SQLITE_CONSTRAINT_PRIMARYKEY: N_(
        "Another row already has that value where values must be unique"
    ),
    sqlite3.SQLITE_CONSTRAINT_CHECK: N_("The value breaks a check of the table"),
    _CONSTRAINT_DATATYPE: N_("The value is not of the type its column holds"),
}
# A broken foreign key reads differently by what broke it.
WRITING = {
    **_REFUSALS,
    sqlite3.SQLITE_CONSTRAINT_FOREIGNKEY: N_("The value refers to a row that does not exist"),
}
DELETING = {
    **_REFUSALS,
    sqlite3.SQLITE_CONSTRAINT_FOREIGNKEY: N_("Other rows refer to this one"),
}

_PROBE = "dp_value_probe"
# The classes a STRICT column may be declared as (datatype3.html, STRICT).
_STRICT_TYPES = frozenset({"INT", "INTEGER", "REAL", "TEXT", "BLOB", "ANY"})


def unreadable(
    connection: sqlite3.Connection, facts: RelationFacts, items: list[tuple[str, FetchColumn]]
) -> list[int]:
    """The positions of the values a STRICT column cannot hold.

    Each value goes into a temporary STRICT table with a column of the same
    type: SQLite's own conversion decides, and no rule is written here twice.
    """
    if not facts.strict or not items:
        return []
    types = sorted(
        {base_name(column.type.sql) for _, column in items} & _STRICT_TYPES
    )
    if not types:
        return []
    slot = {name: f"c{index}" for index, name in enumerate(types)}
    probe = Identifier("temp", _PROBE)
    definition = ", ".join(f"{slot[name]} {name}" for name in types)
    connection.execute(SQL("DROP TABLE IF EXISTS {}").format(probe).text())
    connection.execute(SQL("CREATE TABLE {} (" + definition + ") STRICT").format(probe).text())
    refused: list[int] = []
    try:
        for index, (value, column) in enumerate(items):
            name = base_name(column.type.sql)
            if name not in slot:
                continue
            statement = SQL("INSERT INTO {} ({}) VALUES (?)").format(probe, Identifier(slot[name]))
            try:
                connection.execute(statement.text(), (written(value, column.type),))
            except sqlite3.IntegrityError:
                refused.append(index)
    finally:
        connection.execute(SQL("DROP TABLE IF EXISTS {}").format(probe).text())
    return refused


def _read(
    connection: sqlite3.Connection, facts: RelationFacts, shape: RowShape, handle: RowHandle
) -> tuple[list[str | None], str | None] | None:
    """The row a handle names, as its page shows it; nothing if not exactly one."""
    params: list[object] = []
    statement = SQL("SELECT {} FROM {} WHERE {} LIMIT 2").format(
        selected(shape), Identifier(SCHEMA, facts.name), key_match(shape, handle.keys, params)
    )
    rows = connection.execute(statement.text(), params).fetchall()
    return page_row(tuple(rows[0]), shape) if len(rows) == 1 else None


def _checked(
    connection: sqlite3.Connection, facts: RelationFacts, shape: RowShape, handle: RowHandle
) -> None:
    """Refuse a change to a row somebody changed after it was read."""
    current = _read(connection, facts, shape, handle)
    if current is None or version_of(current[0]) != handle.version:
        raise RowConflict


def _changed(
    connection: sqlite3.Connection,
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
        Identifier(SCHEMA, facts.name),
        assignments,
        key_match(shape, handle.keys, params),
        selected(shape),
    )
    rows = connection.execute(statement.text(), params).fetchall()
    if len(rows) != 1:
        raise RowConflict
    values, renewed = page_row(tuple(rows[0]), shape)
    if renewed is None:
        raise RowConflict
    return UpdatedRow(row_handle=renewed, values=values)


class SqliteUpdate:
    def __init__(self, session: SqliteSession, relation: SqliteRelation) -> None:
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

        def work(connection: sqlite3.Connection) -> UpdatedRow:
            if request.value is not None and unreadable(
                connection, facts, [(request.value, column)]
            ):
                raise ValueError(say("That value cannot be read as {sql}", sql=column.type.sql))
            return _changed(connection, facts, shape, request.row_handle, [(column, request.value)])

        row = await self._session.write(work, refusals=WRITING)
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

        def work(connection: sqlite3.Connection) -> UpdateCellsResult:
            rejected = unreadable(connection, facts, checked)
            if rejected:
                return CellsRejected(
                    cells=[RejectedCell(row=places[at][0], column=places[at][1]) for at in rejected]
                )
            return CellsUpdated(
                rows=[
                    _changed(connection, facts, shape, row.row_handle, cells)
                    for row, cells in zip(request.rows, edits, strict=True)
                ]
            )

        return await self._session.write(work, refusals=WRITING)

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
        target = Identifier(SCHEMA, facts.name)
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

        def work(connection: sqlite3.Connection) -> tuple[list[str | None], str | None]:
            checked = [(value, column) for column, value in given if value is not None]
            if unreadable(connection, facts, checked):
                raise ValueError(say("The source rejected the new value"))
            rows = connection.execute(statement.text(), params).fetchall()
            return page_row(tuple(rows[0]), shape)

        values, handle = await self._session.write(work, refusals=WRITING)
        return InsertRowResult(values=values, row_handle=handle)

    async def insert_rows(self, request: InsertRowsRequest) -> InsertRowsResult:
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
        rows: list[tuple[Any, ...]] = [
            tuple(written(value, column.type) for column, value in zip(targets, row, strict=True))
            for row in request.rows
        ]
        statement = SQL("INSERT INTO {} ({}) VALUES ({})").format(
            Identifier(SCHEMA, facts.name),
            SQL(", ").join(Identifier(column.name) for column in targets),
            SQL(", ").join(SQL("?") for _ in targets),
        )

        def work(connection: sqlite3.Connection) -> InsertRowsResult:
            rejected = unreadable(connection, facts, checked)
            if rejected:
                return ValuesRejected(
                    cells=[
                        RejectedValue(
                            row=places[at][0], column=places[at][1], value=places[at][2][:100]
                        )
                        for at in rejected[:200]
                    ]
                )
            connection.executemany(statement.text(), rows)
            return RowsInserted(inserted=len(rows))

        return await self._session.write(work, refusals=WRITING)

    async def delete_rows(self, request: DeleteRowsRequest) -> DeleteRowsResult:
        facts, shape = await self._shape(request.node_id)
        if not shape.update_supported:
            raise ValueError(shape.update_reason or say("This relation cannot delete rows"))
        if len(set(request.row_handles)) != len(request.row_handles):
            raise ValueError(say("A row may be deleted only once"))
        handles = [decode_handle(value, shape) for value in request.row_handles]

        def work(connection: sqlite3.Connection) -> int:
            for handle in handles:
                _checked(connection, facts, shape, handle)
            params: list[object] = []
            matches: list[Composable] = [
                SQL("({})").format(key_match(shape, handle.keys, params)) for handle in handles
            ]
            statement = SQL("DELETE FROM {} WHERE {}").format(
                Identifier(SCHEMA, facts.name), SQL(" OR ").join(matches)
            )
            deleted = connection.execute(statement.text(), params).rowcount
            if deleted != len(handles):
                raise RowConflict
            return deleted

        return DeleteRowsResult(deleted=await self._session.write(work, refusals=DELETING))
