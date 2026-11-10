"""Changing the rows of a Cassandra table, checked against what was read (D345).

A row is found by its primary key and changed only when it reads again as it
was shown, by its digest. Cassandra has no transaction, so the check and the
change are two statements, and a change somebody makes between them is not
seen. A lightweight transaction would close that gap at the price of a Paxos
round per cell and of a way of writing that ScyllaDB refuses on a keyspace kept
in tablets; a tool that edits a cell at a time was judged not to need it.

Every value is read from its text as its column's type before anything is
written, so a paste lands whole or not at all. An insert of one row refuses a
key that is already there; rows inserted in a block replace a row with the same
key, which is what Cassandra's `INSERT` does and what loading a file expects.
"""

import asyncio
from typing import Any

from app.adapters.cassandra.cql import SQL, Composable, Identifier
from app.adapters.cassandra.inspection import ColumnFacts, RelationFacts
from app.adapters.cassandra.relation import CassandraRelation
from app.adapters.cassandra.rows import change_reason, key_positions, writable
from app.adapters.cassandra.session import CassandraSession
from app.adapters.cassandra.types import parse_value, read_cell
from app.adapters.row_handles import RowHandle, decode_handle, encode_handle, version_of
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
from app.core.translation import say

# Inserts in flight at once while a block is written.
_PARALLEL = 32


def _key_condition(facts: RelationFacts) -> Composable:
    return SQL(" AND ").join(
        SQL("{} = ?").format(Identifier(column.name)) for column in facts.primary_key
    )


class CassandraUpdate:
    def __init__(self, session: CassandraSession, relation: CassandraRelation) -> None:
        self._session = session
        self._relation = relation

    async def _changeable(self, node_id: str) -> RelationFacts:
        facts = await self._relation.facts(node_id)
        reason = change_reason(facts)
        if reason is not None:
            raise ValueError(reason)
        return facts

    @staticmethod
    def _column(facts: RelationFacts, name: str) -> ColumnFacts:
        found = next((column for column in facts.columns if column.name == name), None)
        if found is None:
            raise ValueError(say('Relation has no column "{column}"', column=name))
        return found

    @staticmethod
    def _value(column: ColumnFacts, text: str | None) -> Any:
        if text is None:
            return None
        return parse_value(text, column.type_text)

    def _handle(self, facts: RelationFacts, value: str) -> tuple[RowHandle, list[Any]]:
        handle = decode_handle(value, len(facts.primary_key), nulls=False)
        try:
            keys = [
                parse_value(text or "", column.type_text)
                for text, column in zip(handle.keys, facts.primary_key, strict=True)
            ]
        except ValueError:
            raise ValueError(
                say("The row handle is not valid for this relation")
            ) from None
        return handle, keys

    async def _read(
        self, facts: RelationFacts, keys: list[Any]
    ) -> list[str | None] | None:
        statement = SQL("SELECT {} FROM {} WHERE {}").format(
            SQL(", ").join(Identifier(column.name) for column in facts.columns),
            Identifier(facts.keyspace, facts.name),
            _key_condition(facts),
        )
        answer = await self._session.page(statement.text(), keys, fetch_size=2)
        if not answer.rows:
            return None
        return [
            read_cell(value, column.type)
            for value, column in zip(answer.rows[0], facts.columns, strict=True)
        ]

    @staticmethod
    def _handle_of(facts: RelationFacts, cells: list[str | None]) -> str:
        return encode_handle(
            [cells[index] for index in key_positions(facts)], version_of(cells)
        )

    async def _checked(self, facts: RelationFacts, value: str) -> list[Any]:
        """The row's key, once the row reads as it did; RowConflict when it does not."""
        handle, keys = self._handle(facts, value)
        cells = await self._read(facts, keys)
        if cells is None or version_of(cells) != handle.version:
            raise RowConflict(say("The row was changed or deleted since it was read"))
        return keys

    async def _set(
        self,
        facts: RelationFacts,
        keys: list[Any],
        values: list[tuple[ColumnFacts, Any]],
    ) -> None:
        statement = SQL("UPDATE {} SET {} WHERE {}").format(
            Identifier(facts.keyspace, facts.name),
            SQL(", ").join(
                SQL("{} = ?").format(Identifier(column.name)) for column, _ in values
            ),
            _key_condition(facts),
        )
        await self._session.page(
            statement.text(), [value for _, value in values] + keys
        )

    async def update_cell(self, request: UpdateCellRequest) -> UpdateCellResult:
        facts = await self._changeable(request.node_id)
        column = self._column(facts, request.column)
        if not writable(column):
            raise ValueError(
                say('Column "{column}" cannot be changed here', column=column.name)
            )
        try:
            value = self._value(column, request.value)
        except ValueError:
            raise ValueError(
                say('Invalid value for column "{name}"', name=column.name)
            ) from None
        keys = await self._checked(facts, request.row_handle)
        await self._set(facts, keys, [(column, value)])
        cells = await self._read(facts, keys)
        if cells is None:
            raise RowConflict(say("The row was changed or deleted since it was read"))
        return UpdateCellResult(values=cells, row_handle=self._handle_of(facts, cells))

    async def update_cells(self, request: UpdateCellsRequest) -> UpdateCellsResult:
        facts = await self._changeable(request.node_id)
        rejected: list[RejectedCell] = []
        planned: list[tuple[str, list[tuple[ColumnFacts, Any]]]] = []
        for index, row in enumerate(request.rows):
            values: list[tuple[ColumnFacts, Any]] = []
            for cell in row.cells:
                column = self._column(facts, cell.column)
                if not writable(column):
                    raise ValueError(
                        say(
                            'Column "{column}" cannot be changed here',
                            column=column.name,
                        )
                    )
                try:
                    values.append((column, self._value(column, cell.value)))
                except ValueError:
                    rejected.append(RejectedCell(row=index, column=column.name))
            planned.append((row.row_handle, values))
        if rejected:
            return CellsRejected(cells=rejected)
        # Every row is checked before any is written, so a conflict changes nothing.
        checked = [
            (await self._checked(facts, handle), values) for handle, values in planned
        ]
        for keys, values in checked:
            await self._set(facts, keys, values)
        rows: list[UpdatedRow] = []
        for keys, _ in checked:
            cells = await self._read(facts, keys)
            if cells is None:
                raise RowConflict(
                    say("The row was changed or deleted since it was read")
                )
            rows.append(
                UpdatedRow(row_handle=self._handle_of(facts, cells), values=cells)
            )
        return CellsUpdated(rows=rows)

    def _insert_statement(
        self, facts: RelationFacts, columns: list[ColumnFacts]
    ) -> str:
        return (
            SQL("INSERT INTO {} ({}) VALUES ({})")
            .format(
                Identifier(facts.keyspace, facts.name),
                SQL(", ").join(Identifier(column.name) for column in columns),
                SQL(", ".join("?" for _ in columns)),
            )
            .text()
        )

    @staticmethod
    def _require_key(facts: RelationFacts, given: list[str]) -> None:
        missing = [
            column.name for column in facts.primary_key if column.name not in given
        ]
        if missing:
            raise ValueError(
                say(
                    "Every column of the primary key needs a value: {columns}",
                    columns=", ".join(missing),
                )
            )

    async def insert_row(self, request: InsertRowRequest) -> InsertRowResult:
        facts = await self._changeable(request.node_id)
        self._require_key(facts, [item.column for item in request.values])
        columns: list[ColumnFacts] = []
        values: list[Any] = []
        for item in request.values:
            column = self._column(facts, item.column)
            if not column.in_key and not writable(column):
                raise ValueError(
                    say('Column "{column}" cannot be changed here', column=column.name)
                )
            try:
                value = self._value(column, item.value)
            except ValueError:
                raise ValueError(
                    say('Invalid value for column "{name}"', name=column.name)
                ) from None
            if column.in_key and value is None:
                raise ValueError(
                    say(
                        "Every column of the primary key needs a value: {columns}",
                        columns=column.name,
                    )
                )
            columns.append(column)
            values.append(value)
        given = dict(zip((column.name for column in columns), values, strict=True))
        keys = [given[column.name] for column in facts.primary_key]
        if await self._read(facts, keys) is not None:
            raise ValueError(say("A row with this key is already there"))
        await self._session.page(self._insert_statement(facts, columns), values)
        cells = await self._read(facts, keys)
        if cells is None:
            return InsertRowResult(values=[], row_handle=None)
        return InsertRowResult(values=cells, row_handle=self._handle_of(facts, cells))

    async def insert_rows(self, request: InsertRowsRequest) -> InsertRowsResult:
        facts = await self._changeable(request.node_id)
        self._require_key(facts, request.columns)
        columns = [self._column(facts, name) for name in request.columns]
        for column in columns:
            if not column.in_key and not writable(column):
                raise ValueError(
                    say('Column "{column}" cannot be changed here', column=column.name)
                )
        rejected: list[RejectedValue] = []
        parsed: list[list[Any]] = []
        for index, row in enumerate(request.rows):
            values: list[Any] = []
            for column, text in zip(columns, row, strict=True):
                try:
                    value = self._value(column, text)
                    if column.in_key and value is None:
                        raise ValueError
                    values.append(value)
                except ValueError:
                    rejected.append(
                        RejectedValue(
                            row=index, column=column.name, value=(text or "")[:200]
                        )
                    )
            parsed.append(values)
        if rejected:
            return ValuesRejected(cells=rejected)
        statement = self._insert_statement(facts, columns)
        gate = asyncio.Semaphore(_PARALLEL)

        async def write(values: list[Any]) -> None:
            async with gate:
                await self._session.page(statement, values)

        async with self._session.held():
            await asyncio.gather(*(write(values) for values in parsed))
        return RowsInserted(inserted=len(parsed))

    async def delete_rows(self, request: DeleteRowsRequest) -> DeleteRowsResult:
        facts = await self._changeable(request.node_id)
        checked = [await self._checked(facts, handle) for handle in request.row_handles]
        statement = SQL("DELETE FROM {} WHERE {}").format(
            Identifier(facts.keyspace, facts.name), _key_condition(facts)
        )
        for keys in checked:
            await self._session.page(statement.text(), keys)
        return DeleteRowsResult(deleted=len(checked))
