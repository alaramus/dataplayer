"""Changing the rows of a MySQL table, checked against what was read (D234).

Every change is one strict transaction. A row is locked with `FOR UPDATE`,
digested the way its page showed it, and changed only if the digest is the
one its handle carries. MySQL has no `RETURNING` for an UPDATE, so the row is
read again by its key afterwards, in the same transaction. A row of a table
with no key is found by its values and changed with LIMIT 1 (D242).

Which values a column cannot hold is asked of the server before anything is
written, by putting each into a temporary table of the same column types: a
paste that half lands is worse than one that does not, and the server's own
rules for its types are the only ones that are right.
"""

from app.adapters.fetch import FetchColumn
from app.adapters.mysql.fetch import cells_of, select_of, shape_of
from app.adapters.mysql.inspection import RelationFacts
from app.adapters.mysql.relation import MysqlRelation
from app.adapters.mysql.rows import (
    RowHandle,
    RowShape,
    decode_handle,
    handle_of,
    key_match,
    version_of,
    written,
)
from app.adapters.mysql.session import MysqlSession, Writing
from app.adapters.mysql.sql import SQL, Composable, Identifier
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

# What the server says about a change it will not make, by error number.
REFUSALS: dict[int, str] = {
    1048: N_("A required value is missing"),
    1062: N_("Another row already has that value where values must be unique"),
    1451: N_("Other rows refer to this one"),
    1452: N_("The value refers to a row that does not exist"),
    3819: N_("The value breaks a check of the table"),
}

# How many values are tried in one statement before a refused batch is split.
_PROBE_BATCH = 500
# Made in the database of the table being changed: a connection may have no
# default database, and a temporary table is visible only to it anyway.
_PROBE = "dp_value_probe"
# Rows read to tell a row named whole from the ones it is alike to.
_ALIKE_CEILING = 1000


async def unreadable(
    work: Writing, schema: str, items: list[tuple[str, FetchColumn]]
) -> list[int]:
    """The positions of the values their column's type cannot hold.

    A temporary table has one column of each type asked about, and every value
    is put into its column; a batch the server refuses is halved until the
    refused values are found. TEMPORARY tables cost no commit in MySQL.

    A shape is read on its own: MariaDB answers WKT it cannot read with NULL
    rather than an error, and a NULL goes into a nullable column quietly.
    """
    refused: list[int] = []
    by_type: dict[str, list[int]] = {}
    for index, (value, column) in enumerate(items):
        if column.type.category == "geometric":
            readable = await work.answers("SELECT ST_GeomFromText(%s) IS NOT NULL", (value,))
            if not readable:
                refused.append(index)
            continue
        by_type.setdefault(column.type.sql, []).append(index)
    if not by_type:
        return sorted(refused)
    slot = {sql: f"c{index}" for index, sql in enumerate(by_type)}
    # A column's type as the server stated it in COLUMNS, so it is the
    # server's own text being handed back to it rather than a client's. A `%`
    # in an enum's label is doubled, as in any statement sent with parameters.
    definition = SQL(", ").join(
        SQL("{} " + sql.replace("%", "%%") + " NULL").format(Identifier(slot[sql]))
        for sql in by_type
    )
    probe = Identifier(schema, _PROBE)
    drop = SQL("DROP TEMPORARY TABLE IF EXISTS {}").format(probe).text()
    await work.execute(drop)
    await work.execute(SQL("CREATE TEMPORARY TABLE {} ({})").format(probe, definition).text())
    try:
        for sql, positions in by_type.items():
            for begin in range(0, len(positions), _PROBE_BATCH):
                refused += await _probe(
                    work, probe, items, slot[sql], positions[begin : begin + _PROBE_BATCH]
                )
        return sorted(refused)
    finally:
        await work.execute(drop)


async def _probe(
    work: Writing,
    probe: Identifier,
    items: list[tuple[str, FetchColumn]],
    slot: str,
    positions: list[int],
) -> list[int]:
    placeholders: list[Composable] = []
    params: list[object] = []
    for position in positions:
        value, column = items[position]
        placeholder, param = written(value, column.type)
        placeholders.append(SQL("({})").format(placeholder))
        params.append(param)
    statement = SQL("INSERT INTO {} ({}) VALUES {}").format(
        probe, Identifier(slot), SQL(", ").join(placeholders)
    )
    accepted = await work.holds(statement.text(), tuple(params))
    if accepted:
        return []
    if len(positions) == 1:
        return positions
    half = len(positions) // 2
    return [
        *await _probe(work, probe, items, slot, positions[:half]),
        *await _probe(work, probe, items, slot, positions[half:]),
    ]


class MysqlUpdate:
    def __init__(self, session: MysqlSession, relation: MysqlRelation) -> None:
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

    async def _candidates(
        self, work: Writing, facts: RelationFacts, shape: RowShape, keys: list[str | None]
    ) -> list[list[str | None]]:
        """The rows these values find, locked, as their page shows them."""
        params: list[object] = []
        statement = SQL("SELECT {} FROM {} WHERE {}").format(
            select_of(shape), Identifier(facts.schema, facts.name), key_match(shape, keys, params)
        )
        if shape.whole_row:
            statement += SQL(f" LIMIT {_ALIKE_CEILING + 1}")
        statement += SQL(" FOR UPDATE")
        rows = await work.rows(statement.text(), tuple(params))
        return [cells_of(row, shape) for row in rows]

    async def _locked(
        self,
        work: Writing,
        facts: RelationFacts,
        shape: RowShape,
        keys: list[str | None],
        version: str | None = None,
    ) -> list[str | None] | None:
        """The row these values name, locked, as its page shows it.

        A key finds one row or none. Values find every row alike in the
        columns that compare exactly; the digest then says which is this one,
        and rows alike but not the same are refused rather than guessed at.
        """
        found = await self._candidates(work, facts, shape, keys)
        if not shape.whole_row:
            return found[0] if len(found) == 1 else None
        digests = {version_of(cells) for cells in found}
        if len(found) > _ALIKE_CEILING or len(digests) > 1:
            if version is None or version in digests:
                raise ValueError(
                    say(
                        "Another row differs from this one only in a column that cannot be "
                        "compared exactly, so this one cannot be told apart; give the table a key"
                    )
                )
            return None
        if not found or (version is not None and version not in digests):
            return None
        return found[0]

    async def _changed(
        self,
        work: Writing,
        facts: RelationFacts,
        shape: RowShape,
        handle_value: str,
        cells: list[tuple[FetchColumn, str | None]],
    ) -> UpdatedRow:
        handle = decode_handle(handle_value, shape)
        current = await self._locked(work, facts, shape, handle.keys, handle.version)
        if current is None or version_of(current) != handle.version:
            raise RowConflict
        params: list[object] = []
        assignments: list[Composable] = []
        for column, value in cells:
            placeholder, param = written(value, column.type)
            assignments.append(SQL("{} = {}").format(Identifier(column.name), placeholder))
            params.append(param)
        statement = SQL("UPDATE {} SET {} WHERE {}").format(
            Identifier(facts.schema, facts.name),
            SQL(", ").join(assignments),
            key_match(shape, handle.keys, params),
        )
        if shape.whole_row:
            # Rows alike in every value are one row to anybody looking.
            statement += SQL(" LIMIT 1")
        await work.execute(statement.text(), tuple(params))
        # Read back by the key the row has now, which is the one it was given
        # if a key column was among the cells changed.
        given = {column.name: value for column, value in cells}
        keys = [given.get(name, old) for name, old in zip(shape.naming, handle.keys, strict=True)]
        if shape.whole_row:
            try:
                after = await self._locked(work, facts, shape, keys)
            except ValueError:
                after = None
            # Alike to another row once changed: what was written is what can
            # be said about it, and its next change is checked against that.
            after = after or keys
        else:
            if any(value is None for value in keys):
                raise RowConflict
            after = await self._locked(work, facts, shape, keys)
        if after is None:
            raise RowConflict
        renewed = handle_of(shape, after)
        if renewed is None:
            raise RowConflict
        return UpdatedRow(row_handle=renewed, values=after)

    async def update_cell(self, request: UpdateCellRequest) -> UpdateCellResult:
        facts, shape = await self._shape(request.node_id)
        if not shape.update_supported:
            raise ValueError(shape.update_reason or say("This relation cannot be edited"))
        column = self._column(shape, request.column, editing=True)
        decode_handle(request.row_handle, shape)
        async with self._session.writing(refusals=REFUSALS) as work:
            if request.value is not None and await unreadable(
                work, facts.schema, [(request.value, column)]
            ):
                raise ValueError(say("That value cannot be read as {sql}", sql=column.type.sql))
            row = await self._changed(
                work, facts, shape, request.row_handle, [(column, request.value)]
            )
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
            cells = [(self._column(shape, cell.column, editing=True), cell.value) for cell in row.cells]
            edits.append(cells)
            for column, value in cells:
                if value is not None:
                    checked.append((value, column))
                    places.append((index, column.name))
        updated: list[UpdatedRow] = []
        async with self._session.writing(refusals=REFUSALS) as work:
            rejected = await unreadable(work, facts.schema, checked)
            if rejected:
                return CellsRejected(
                    cells=[RejectedCell(row=places[at][0], column=places[at][1]) for at in rejected]
                )
            for row, cells in zip(request.rows, edits, strict=True):
                updated.append(await self._changed(work, facts, shape, row.row_handle, cells))
        return CellsUpdated(rows=updated)

    async def insert_row(self, request: InsertRowRequest) -> InsertRowResult:
        facts, shape = await self._shape(request.node_id)
        if not shape.insert_supported:
            raise ValueError(shape.insert_reason or say("This relation cannot accept rows"))
        given = [(self._column(shape, item.column, editing=False), item.value) for item in request.values]
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
        params: list[object] = []
        placeholders: list[Composable] = []
        for column, value in given:
            placeholder, param = written(value, column.type)
            placeholders.append(placeholder)
            params.append(param)
        statement = SQL("INSERT INTO {} ({}) VALUES ({})").format(
            Identifier(facts.schema, facts.name),
            SQL(", ").join(Identifier(column.name) for column, _ in given),
            SQL(", ").join(placeholders),
        )
        async with self._session.writing(refusals=REFUSALS) as work:
            checked = [(value, column) for column, value in given if value is not None]
            if await unreadable(work, facts.schema, checked):
                raise ValueError(say("The source rejected the new value"))
            _, made = await work.execute(statement.text(), tuple(params))
            keys = self._new_key(facts, shape, given, made)
            row = None if keys is None else await self._locked(work, facts, shape, keys)
        if row is None:
            # A table with no key to read the row back by: what was given is
            # what can be said about it.
            values = {column.name: value for column, value in given}
            return InsertRowResult(
                values=[values.get(column.name) for column in shape.columns], row_handle=None
            )
        return InsertRowResult(values=row, row_handle=handle_of(shape, row))

    @staticmethod
    def _new_key(
        facts: RelationFacts,
        shape: RowShape,
        given: list[tuple[FetchColumn, str | None]],
        made: int,
    ) -> list[str | None] | None:
        """The key of a row just inserted, from what was given or what was made."""
        if not shape.key:
            return None
        values = {column.name: value for column, value in given}
        generated = {column.name for column in facts.columns if column.auto_increment}
        keys: list[str | None] = []
        for name in shape.key:
            value = values.get(name)
            if value is None and name in generated and made:
                value = str(made)
            if value is None:
                return None
            keys.append(value)
        return keys

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
        rows: list[tuple[object, ...]] = []
        placeholders: list[Composable] = []
        for index, row in enumerate(request.rows):
            converted = [written(value, column.type) for column, value in zip(targets, row, strict=True)]
            if index == 0:
                placeholders = [placeholder for placeholder, _ in converted]
            rows.append(tuple(param for _, param in converted))
        statement = SQL("INSERT INTO {} ({}) VALUES ({})").format(
            Identifier(facts.schema, facts.name),
            SQL(", ").join(Identifier(column.name) for column in targets),
            SQL(", ").join(placeholders),
        )
        async with self._session.writing(refusals=REFUSALS) as work:
            rejected = await unreadable(work, facts.schema, checked)
            if rejected:
                return ValuesRejected(
                    cells=[
                        RejectedValue(
                            row=places[at][0], column=places[at][1], value=places[at][2][:100]
                        )
                        for at in rejected[:200]
                    ]
                )
            await work.execute_many(statement.text(), rows)
        return RowsInserted(inserted=len(request.rows))

    async def delete_rows(self, request: DeleteRowsRequest) -> DeleteRowsResult:
        facts, shape = await self._shape(request.node_id)
        if not shape.update_supported:
            raise ValueError(shape.update_reason or say("This relation cannot delete rows"))
        if len(set(request.row_handles)) != len(request.row_handles):
            raise ValueError(say("A row may be deleted only once"))
        handles = [decode_handle(value, shape) for value in request.row_handles]
        if shape.whole_row:
            return await self._delete_alike(facts, shape, handles)
        async with self._session.writing(refusals=REFUSALS) as work:
            for handle in handles:
                current = await self._locked(work, facts, shape, handle.keys)
                if current is None or version_of(current) != handle.version:
                    raise RowConflict
            params: list[object] = []
            matches = SQL(" OR ").join(
                SQL("({})").format(key_match(shape, handle.keys, params)) for handle in handles
            )
            statement = SQL("DELETE FROM {} WHERE {}").format(
                Identifier(facts.schema, facts.name), matches
            )
            deleted, _ = await work.execute(statement.text(), tuple(params))
            if deleted != len(handles):
                raise RowConflict
        return DeleteRowsResult(deleted=deleted)

    async def _delete_alike(
        self, facts: RelationFacts, shape: RowShape, handles: list[RowHandle]
    ) -> DeleteRowsResult:
        """Rows named whole, as many of each as were picked (D242).

        Two rows the same in every value have handles of their own, and
        picking both deletes two of them, whichever two the server finds.
        """
        picked: dict[tuple[str, tuple[str | None, ...]], int] = {}
        for handle in handles:
            group = (handle.version, tuple(handle.keys))
            picked[group] = picked.get(group, 0) + 1
        deleted = 0
        async with self._session.writing(refusals=REFUSALS) as work:
            for (version, keys), count in picked.items():
                current = await self._locked(work, facts, shape, list(keys), version)
                if current is None:
                    raise RowConflict
                params: list[object] = []
                statement = SQL("DELETE FROM {} WHERE {}").format(
                    Identifier(facts.schema, facts.name), key_match(shape, list(keys), params)
                ) + SQL(f" LIMIT {count}")
                gone, _ = await work.execute(statement.text(), tuple(params))
                if gone != count:
                    raise RowConflict
                deleted += gone
        return DeleteRowsResult(deleted=deleted)

