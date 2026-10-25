"""Changing the rows of a ClickHouse table, checked against what was read (D272).

A row is named by its whole row and found again by the columns that compare
exactly; the rows found must all be the row shown, by its digest, or the
change is refused. Rows the same in every value are changed together: to
anybody reading them they are one row, and nothing can tell them apart.

ClickHouse has no transaction, so the check and the change are two requests,
and a change somebody makes between them is not seen (D272). A change is a
lightweight `UPDATE` or `DELETE`; a table made without the block number column
a lightweight update needs is changed by a mutation instead, waited for to
its end.

Which values a column cannot hold is asked of the server before anything is
written, by casting each value as the write would, so a paste lands whole or
not at all.
"""

import json

from app.adapters.clickhouse.fetch import shape_of
from app.adapters.clickhouse.inspection import RelationFacts
from app.adapters.clickhouse.relation import ClickhouseRelation
from app.adapters.clickhouse.rows import (
    RowShape,
    handle_of,
    row_match,
    value_expression,
    writable_type,
)
from app.adapters.clickhouse.session import ClickhouseSession, ServerError
from app.adapters.clickhouse.sql import SQL, Composable, Identifier, Params
from app.adapters.clickhouse.types import decode_line, read_cell, type_name, unwrapped
from app.adapters.fetch import FetchColumn
from app.adapters.row_handles import RowHandle, decode_handle, version_of
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

# What the server says about a change it will not make, by error code.
REFUSALS: dict[int, str] = {
    420: N_("A column of the table's key cannot be changed"),
    469: N_("The value breaks a check of the table"),
}

# A lightweight UPDATE on a table made without `_block_number`.
_NOT_IMPLEMENTED = 48

# How many values one probing statement casts before a refused batch is split.
_PROBE_BATCH = 200
# Rows read to tell a row named whole from the ones it is alike to.
_ALIKE_CEILING = 1000

# How a value is read back in, as every moment is shown in UTC with `Z` (D268).
_WRITING = {"date_time_input_format": "best_effort", "mutations_sync": "1"}


def _probed(value: str | None, column: FetchColumn) -> bool:
    """Whether a value is asked of the server: text holds any text, and a
    value of a type nothing casts to is read as JSON here instead."""
    if value is None:
        return False
    inner = unwrapped(column.type.sql)
    return type_name(inner) != "String" and writable_type(column.type)


def _json_value(value: str | None, column: FetchColumn) -> str:
    """One value as a field of a JSONEachRow line."""
    if value is None:
        return "null"
    if column.type.category in ("array", "composite", "geometric", "json"):
        # Shown as JSON, so written as it: compacted, its numbers as written.
        compact = read_cell(decode_line(value))
        return "null" if compact is None else compact
    if column.type.category == "boolean" and value.lower() in ("true", "false", "1", "0"):
        # JSONEachRow takes a number in quotes and a boolean only bare.
        return value.lower()
    return json.dumps(value, ensure_ascii=False)


async def insert_json(
    session: ClickhouseSession,
    schema: str,
    name: str,
    targets: list[FetchColumn],
    rows: list[list[str | None]],
) -> None:
    """Rows as one JSONEachRow statement; a column left out takes its default."""
    lines = [
        "{"
        + ",".join(
            f"{json.dumps(column.name, ensure_ascii=False)}:{_json_value(value, column)}"
            for column, value in zip(targets, row, strict=True)
        )
        + "}"
        for row in rows
    ]
    table = Identifier(schema, name)
    statement = (
        SQL("INSERT INTO {} ({}) FORMAT JSONEachRow").format(
            table, SQL(", ").join(Identifier(column.name) for column in targets)
        )
        if targets
        else SQL("INSERT INTO {} FORMAT JSONEachRow").format(table)
    )
    await session.command(
        statement.text(), {}, settings=_WRITING, refusals=REFUSALS, data="\n".join(lines).encode()
    )


class ClickhouseUpdate:
    def __init__(self, session: ClickhouseSession, relation: ClickhouseRelation) -> None:
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

    async def unreadable(self, items: list[tuple[str | None, FetchColumn]]) -> list[int]:
        """The positions of the values their column's type cannot hold."""
        refused: list[int] = []
        asked: list[int] = []
        for index, (value, column) in enumerate(items):
            if value is None:
                continue
            if column.type.category in ("array", "composite", "geometric", "json"):
                try:
                    decode_line(value)
                except ValueError:
                    refused.append(index)
                    continue
            if _probed(value, column):
                asked.append(index)
        for begin in range(0, len(asked), _PROBE_BATCH):
            refused += await self._probe(items, asked[begin : begin + _PROBE_BATCH])
        return sorted(refused)

    async def _probe(
        self, items: list[tuple[str | None, FetchColumn]], positions: list[int]
    ) -> list[int]:
        params = Params()
        expressions: list[Composable] = []
        refused: list[int] = []
        kept: list[int] = []
        for position in positions:
            value, column = items[position]
            try:
                expressions.append(value_expression(value, column.type, params))
                kept.append(position)
            except ValueError:
                refused.append(position)
        if not kept:
            return refused
        statement = SQL("SELECT {}").format(SQL(", ").join(expressions))
        try:
            await self._session.answer(
                statement.text(), params.values, settings=_WRITING, server_errors=True
            )
        except ServerError:
            if len(kept) == 1:
                return refused + kept
            half = len(kept) // 2
            return [
                *refused,
                *await self._probe(items, kept[:half]),
                *await self._probe(items, kept[half:]),
            ]
        return refused

    async def _alike(
        self, facts: RelationFacts, shape: RowShape, cells: list[str | None]
    ) -> list[list[str | None]]:
        """The rows these values find, as their page shows them."""
        params = Params()
        statement = SQL("SELECT {} FROM {} WHERE {} LIMIT {}").format(
            SQL(", ").join(Identifier(column.name) for column in shape.columns),
            Identifier(facts.schema, facts.name),
            row_match(shape, cells, params),
            params.add(str(_ALIKE_CEILING + 1), "UInt32"),
        )
        answer = await self._session.answer(statement.text(), params.values, settings=_WRITING)
        return [[read_cell(value) for value in row] for row in answer.rows]

    async def _found(self, facts: RelationFacts, shape: RowShape, handle: RowHandle) -> int:
        """How many rows the handle names now; refused if they are not the row shown.

        Values find every row alike in the columns that compare exactly; the
        digest then says whether they are this one, and rows alike but not the
        same are refused rather than changed together by mistake.
        """
        found = await self._alike(facts, shape, handle.keys)
        digests = {version_of(cells) for cells in found}
        if len(found) > _ALIKE_CEILING or len(digests) > 1:
            if handle.version in digests:
                raise ValueError(
                    say(
                        "Another row differs from this one only in a column that cannot be "
                        "compared exactly, so this one cannot be told apart"
                    )
                )
            raise RowConflict
        if not found or handle.version not in digests:
            raise RowConflict
        return len(found)

    async def _change(
        self,
        facts: RelationFacts,
        lightweight: Composable,
        mutation: Composable,
        params: Params,
    ) -> None:
        """A lightweight change, or the mutation that does the same where the
        table cannot take one."""
        try:
            await self._session.command(
                lightweight.text(),
                params.values,
                settings=_WRITING,
                refusals=REFUSALS,
                passing=frozenset({_NOT_IMPLEMENTED}),
            )
        except ServerError:
            await self._session.command(
                mutation.text(), params.values, settings=_WRITING, refusals=REFUSALS
            )

    async def _changed(
        self,
        facts: RelationFacts,
        shape: RowShape,
        handle_value: str,
        cells: list[tuple[FetchColumn, str | None]],
    ) -> UpdatedRow:
        handle = decode_handle(handle_value, len(shape.columns), nulls=True)
        await self._found(facts, shape, handle)
        params = Params()
        assignments = SQL(", ").join(
            SQL("{} = {}").format(Identifier(column.name), value_expression(value, column.type, params))
            for column, value in cells
        )
        where = row_match(shape, handle.keys, params)
        table = Identifier(facts.schema, facts.name)
        await self._change(
            facts,
            SQL("UPDATE {} SET {} WHERE {}").format(table, assignments, where),
            SQL("ALTER TABLE {} UPDATE {} WHERE {}").format(table, assignments, where),
            params,
        )
        given = {column.name: value for column, value in cells}
        after = [
            given.get(column.name, old)
            for column, old in zip(shape.columns, handle.keys, strict=True)
        ]
        # Read back as the server shows it now: `1.5` into a Decimal(38, 10)
        # is shown with its whole scale. Alike to another row once changed,
        # what was written is what can be said about it.
        found = await self._alike(facts, shape, after)
        if found and len({version_of(row) for row in found}) == 1:
            after = found[0]
        renewed = handle_of(shape, after)
        if renewed is None:
            raise RowConflict
        return UpdatedRow(row_handle=renewed, values=after)

    async def update_cell(self, request: UpdateCellRequest) -> UpdateCellResult:
        facts, shape = await self._shape(request.node_id)
        if not shape.update_supported:
            raise ValueError(shape.update_reason or say("This relation cannot be edited"))
        column = self._column(shape, request.column, editing=True)
        decode_handle(request.row_handle, len(shape.columns), nulls=True)
        if await self.unreadable([(request.value, column)]):
            raise ValueError(say("That value cannot be read as {sql}", sql=column.type.sql))
        row = await self._changed(facts, shape, request.row_handle, [(column, request.value)])
        return UpdateCellResult(values=row.values, row_handle=row.row_handle)

    async def update_cells(self, request: UpdateCellsRequest) -> UpdateCellsResult:
        facts, shape = await self._shape(request.node_id)
        if not shape.update_supported:
            raise ValueError(shape.update_reason or say("This relation cannot be edited"))
        edits: list[list[tuple[FetchColumn, str | None]]] = []
        checked: list[tuple[str | None, FetchColumn]] = []
        places: list[tuple[int, str]] = []
        for index, row in enumerate(request.rows):
            decode_handle(row.row_handle, len(shape.columns), nulls=True)
            cells = [(self._column(shape, cell.column, editing=True), cell.value) for cell in row.cells]
            edits.append(cells)
            for column, value in cells:
                checked.append((value, column))
                places.append((index, column.name))
        rejected = await self.unreadable(checked)
        if rejected:
            return CellsRejected(
                cells=[RejectedCell(row=places[at][0], column=places[at][1]) for at in rejected]
            )
        updated = [
            await self._changed(facts, shape, row.row_handle, cells)
            for row, cells in zip(request.rows, edits, strict=True)
        ]
        return CellsUpdated(rows=updated)

    def _given(self, shape: RowShape, columns: list[str]) -> list[FetchColumn]:
        if not shape.insert_supported:
            raise ValueError(shape.insert_reason or say("This relation cannot accept rows"))
        return [self._column(shape, name, editing=False) for name in columns]

    async def _insert(
        self, facts: RelationFacts, targets: list[FetchColumn], rows: list[list[str | None]]
    ) -> None:
        await insert_json(self._session, facts.schema, facts.name, targets, rows)

    async def insert_row(self, request: InsertRowRequest) -> InsertRowResult:
        facts, shape = await self._shape(request.node_id)
        targets = self._given(shape, [item.column for item in request.values])
        values = [item.value for item in request.values]
        if await self.unreadable(list(zip(values, targets, strict=True))):
            raise ValueError(say("The source rejected the new value"))
        await self._insert(facts, targets, [values])
        # No key reads the row back: what was given is what can be said of it.
        given = {item.column: item.value for item in request.values}
        return InsertRowResult(
            values=[given.get(column.name) for column in shape.columns], row_handle=None
        )

    async def insert_rows(self, request: InsertRowsRequest) -> InsertRowsResult:
        facts, shape = await self._shape(request.node_id)
        targets = self._given(shape, request.columns)
        checked: list[tuple[str | None, FetchColumn]] = []
        places: list[tuple[int, str, str | None]] = []
        for index, row in enumerate(request.rows):
            for column, value in zip(targets, row, strict=True):
                checked.append((value, column))
                places.append((index, column.name, value))
        rejected = await self.unreadable(checked)
        if rejected:
            return ValuesRejected(
                cells=[
                    RejectedValue(row=row, column=column, value=None if value is None else value[:100])
                    for row, column, value in (places[at] for at in rejected[:200])
                ]
            )
        await self._insert(facts, targets, request.rows)
        return RowsInserted(inserted=len(request.rows))

    async def delete_rows(self, request: DeleteRowsRequest) -> DeleteRowsResult:
        """Every row alike to the ones picked, each group once (D272)."""
        facts, shape = await self._shape(request.node_id)
        if not shape.update_supported:
            raise ValueError(shape.update_reason or say("This relation cannot delete rows"))
        groups: dict[str, RowHandle] = {}
        for value in request.row_handles:
            handle = decode_handle(value, len(shape.columns), nulls=True)
            groups.setdefault(handle.version, handle)
        deleted = 0
        table = Identifier(facts.schema, facts.name)
        for handle in groups.values():
            count = await self._found(facts, shape, handle)
            params = Params()
            where = row_match(shape, handle.keys, params)
            await self._change(
                facts,
                SQL("DELETE FROM {} WHERE {}").format(table, where),
                SQL("ALTER TABLE {} DELETE WHERE {}").format(table, where),
                params,
            )
            deleted += count
        return DeleteRowsResult(deleted=deleted)
