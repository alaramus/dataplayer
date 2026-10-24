"""Columns of a SQLite table added, dropped, renamed and changed (D27, D255).

Adding a column that may be empty and renaming one are SQLite's own ALTER
TABLE. Everything else is a rebuild with one clause of the table's text edited
(`restructure`), so what the change does not touch stays as it was written.
"""

import re
import sqlite3

from app.adapters.column_changes import (
    AddColumnRequest,
    ColumnChangeResult,
    ColumnDefaultRequest,
    ColumnNullabilityRequest,
    ColumnNullabilityResult,
    ColumnTypeBlocked,
    ColumnTypeChanged,
    ColumnTypeChangeResult,
    ColumnTypeRequest,
    DropColumnRequest,
    NullabilityBlocked,
    NullabilityChanged,
    RenameColumnRequest,
)
from app.adapters.relation import ColumnType
from app.adapters.sqlite.definition import ColumnText, TableText, read_table
from app.adapters.sqlite.inspection import SCHEMA, ColumnFacts, RelationFacts
from app.adapters.sqlite.relation import SqliteRelation, structure_reason
from app.adapters.sqlite.restructure import (
    Edit,
    Kept,
    after_type,
    column_added,
    edited,
    rebuild,
    retyped,
    uses_column,
    without_clause,
    without_items,
)
from app.adapters.sqlite.session import SqliteSession
from app.adapters.sqlite.sql import SQL, Composable, Identifier, quoted_name
from app.adapters.sqlite.vocabulary import column_type
from app.core.translation import N_, say

# Rows counted before a change is refused for them; past it the count is "at
# least", which is all the next decision needs (D37, D38).
COUNT_CEILING = 1000

REFUSALS: dict[int, str] = {
    sqlite3.SQLITE_CONSTRAINT_NOTNULL: N_(
        "The table has rows, and a new column that requires a value would have none in them"
    ),
}

_NUMBER = re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?")
_HEX = re.compile(r"0x([0-9A-Fa-f]*)")


def literal(value: str, type_: ColumnType) -> str:
    """A default as SQLite reads a literal of this column's kind (D255).

    The inverse of how a page shows a value, as a written cell is (D254): a
    number stays a number where the column holds numbers, `true` and `false`
    are 1 and 0, hexadecimal is a blob. Anything else is a quoted string.
    """
    category = type_.category
    if category in ("number", "other") and _NUMBER.fullmatch(value):
        return value
    if category == "boolean" and value.lower() in ("true", "false"):
        return "1" if value.lower() == "true" else "0"
    if category == "binary" and (found := _HEX.fullmatch(value)) is not None:
        return f"X'{found.group(1)}'"
    return "'" + value.replace("'", "''") + "'"


def _column_text(table: TableText, name: str) -> ColumnText:
    found = table.columns.get(name.lower())
    if found is None:
        raise ValueError(say("The table's definition could not be read"))
    return found


def _stored(facts: RelationFacts, *, leaving: str | None = None) -> list[str]:
    """The columns that carry a row's values across a rebuild."""
    return [
        column.name
        for column in facts.columns
        if column.generated is None and column.name != leaving
    ]


def bounded_count(connection: sqlite3.Connection, statement: Composable) -> tuple[int, bool]:
    """How many rows a statement finds, up to the ceiling, and whether that is all."""
    counted = SQL("SELECT count(*) FROM ({} LIMIT ?)").format(statement)
    found = int(connection.execute(counted.text(), (COUNT_CEILING + 1,)).fetchone()[0])
    return min(found, COUNT_CEILING), found <= COUNT_CEILING


class SqliteColumns:
    def __init__(self, session: SqliteSession, relation: SqliteRelation) -> None:
        self._session = session
        self._relation = relation

    async def _changeable(self, node_id: str) -> tuple[RelationFacts, TableText]:
        facts = await self._relation.facts(node_id)
        refused = structure_reason(facts)
        if refused is not None:
            raise ValueError(refused)
        return facts, read_table(facts.text)

    @staticmethod
    def _column(facts: RelationFacts, name: str) -> ColumnFacts:
        column = next((column for column in facts.columns if column.name == name), None)
        if column is None:
            raise ValueError(say('Relation has no column "{column}"', column=name))
        return column

    @staticmethod
    def _unused(facts: RelationFacts, name: str) -> None:
        if any(column.name.lower() == name.lower() for column in facts.columns):
            raise ValueError(say('Relation already has a column "{name}"', name=name))

    async def add_column(self, request: AddColumnRequest) -> ColumnChangeResult:
        facts, table = await self._changeable(request.node_id)
        self._unused(facts, request.name)
        option = column_type(request.type_code, facts.strict)
        if option is None:
            raise ValueError(say('Unknown column type "{code}"', code=request.type_code))
        definition = f"{quoted_name(request.name)} {option.sql}"
        target = quoted_name(SCHEMA, facts.name)
        if request.nullable:
            await self._session.write(
                lambda connection: connection.execute(
                    f"ALTER TABLE {target} ADD COLUMN {definition}"
                ),
                refusals=REFUSALS,
            )
        else:
            # SQLite adds no column that requires a value without a default to
            # give the rows already there; a rebuild says whether there are any.
            text = _edited(table, [column_added(table, f"{definition} NOT NULL")])
            await self._session.restructure(
                lambda connection: rebuild(connection, facts.name, text, _stored(facts)),
                refusals=REFUSALS,
            )
        return ColumnChangeResult(name=request.name)

    async def drop_column(self, request: DropColumnRequest) -> ColumnChangeResult:
        facts, table = await self._changeable(request.node_id)
        column = self._column(facts, request.name)
        if len(facts.columns) == 1:
            raise ValueError(say("A table must keep at least one column"))
        said = _column_text(table, column.name)
        # The keys and indexes over the column go with it, as PostgreSQL's
        # do; a check, a view or a trigger that reads it refuses the drop in
        # SQLite's own words.
        positions = [said.item] + [
            clause.item
            for clause in table.constraints
            if not clause.inline and clause.kind != "check" and uses_column(clause, column.name)
        ]
        text = _edited(table, [without_items(table, positions)])

        def keep(kept: Kept) -> bool:
            return not any(name.lower() == column.name.lower() for name in kept.columns)

        await self._session.restructure(
            lambda connection: rebuild(
                connection, facts.name, text, _stored(facts, leaving=column.name), keep_index=keep
            )
        )
        return ColumnChangeResult(name=request.name)

    async def rename_column(self, request: RenameColumnRequest) -> ColumnChangeResult:
        facts, _ = await self._changeable(request.node_id)
        column = self._column(facts, request.name)
        if request.new_name.lower() != column.name.lower():
            self._unused(facts, request.new_name)
        statement = (
            f"ALTER TABLE {quoted_name(SCHEMA, facts.name)} "
            f"RENAME COLUMN {quoted_name(column.name)} TO {quoted_name(request.new_name)}"
        )
        # SQLite renames it in the table's indexes, triggers, views and keys.
        await self._session.restructure(lambda connection: connection.execute(statement))
        return ColumnChangeResult(name=request.new_name)

    async def change_column_default(self, request: ColumnDefaultRequest) -> ColumnChangeResult:
        facts, table = await self._changeable(request.node_id)
        column = self._column(facts, request.name)
        if column.generated is not None:
            raise ValueError(say("A generated column cannot have a default"))
        said = _column_text(table, column.name)
        edits: list[Edit] = [
            without_clause(table, clause) for clause in said.clauses if clause.kind == "default"
        ]
        if request.action == "set" and request.value is not None:
            edits.append(after_type(said, f"DEFAULT {literal(request.value, column.type)}"))
        text = _edited(table, edits)
        await self._session.restructure(
            lambda connection: rebuild(connection, facts.name, text, _stored(facts))
        )
        return ColumnChangeResult(name=request.name)

    async def change_column_nullability(
        self, request: ColumnNullabilityRequest
    ) -> ColumnNullabilityResult:
        facts, table = await self._changeable(request.node_id)
        column = self._column(facts, request.name)
        if column.generated is not None:
            raise ValueError(say("A generated column takes its value from its expression"))
        if column.nullable == request.nullable:
            raise ValueError(
                say("The column already accepts rows with no value")
                if request.nullable
                else say("The column already requires a value in every row")
            )
        if request.nullable and column.key_position and (facts.without_rowid or column.rowid_alias):
            raise ValueError(
                say(
                    'Column "{name}" is part of primary key "{key}"',
                    name=column.name,
                    key="PRIMARY KEY",
                )
            )
        said = _column_text(table, column.name)
        if request.nullable:
            edits = [
                without_clause(table, clause)
                for clause in said.clauses
                if clause.kind == "not_null"
            ]
        else:
            edits = [after_type(said, "NOT NULL")]
        text = _edited(table, edits)
        empty = SQL("SELECT 1 FROM {} WHERE {} IS NULL").format(
            Identifier(SCHEMA, facts.name), Identifier(column.name)
        )

        def work(connection: sqlite3.Connection) -> ColumnNullabilityResult:
            if not request.nullable:
                found, exact = bounded_count(connection, empty)
                if found:
                    return NullabilityBlocked(
                        name=column.name, rows_without_value=found, exact=exact
                    )
            rebuild(connection, facts.name, text, _stored(facts))
            return NullabilityChanged(name=column.name, nullable=request.nullable)

        return await self._session.restructure(work)

    async def change_column_type(self, request: ColumnTypeRequest) -> ColumnTypeChangeResult:
        facts, table = await self._changeable(request.node_id)
        column = self._column(facts, request.name)
        if column.generated is not None:
            raise ValueError(say("A generated column takes its type from its expression"))
        option = column_type(request.type_code, facts.strict)
        if option is None:
            raise ValueError(say('Unknown column type "{code}"', code=request.type_code))
        if option.sql.lower() == column.type.sql.lower():
            raise ValueError(say('The column already has type "{sql}"', sql=option.sql))
        said = _column_text(table, column.name)
        text = _edited(table, retyped(said, option.sql))
        values = SQL("SELECT {} FROM {} WHERE {} IS NOT NULL").format(
            Identifier(column.name), Identifier(SCHEMA, facts.name), Identifier(column.name)
        )

        def work(connection: sqlite3.Connection) -> ColumnTypeChangeResult:
            if facts.strict:
                # Only a STRICT table refuses a value for its type; the values
                # are tried in a column of the new type first.
                refused = _unconvertible(connection, values, option.sql)
                if refused[0]:
                    return ColumnTypeBlocked(
                        name=column.name, rows_not_convertible=refused[0], exact=refused[1]
                    )
            rebuild(connection, facts.name, text, _stored(facts))
            return ColumnTypeChanged(name=column.name, type_sql=option.sql)

        return await self._session.restructure(work)


def _edited(table: TableText, edits: list[Edit]) -> str:
    return edited(table.text, edits)


def _unconvertible(
    connection: sqlite3.Connection, values: Composable, sql: str
) -> tuple[int, bool]:
    """How many values a STRICT column of type `sql` refuses, up to the ceiling.

    `sql` is one of the published type options, never a client's text.
    """
    probe = Identifier("temp", "dp_type_probe")
    drop = SQL("DROP TABLE IF EXISTS {}").format(probe).text()
    connection.execute(drop)
    connection.execute(SQL("CREATE TABLE {} (value " + sql + ") STRICT").format(probe).text())
    insert = SQL("INSERT INTO {} (value) VALUES (?)").format(probe).text()
    refused = 0
    try:
        for (value,) in connection.execute(values.text()):
            try:
                connection.execute(insert, (value,))
            except sqlite3.IntegrityError:
                refused += 1
                if refused > COUNT_CEILING:
                    return COUNT_CEILING, False
    finally:
        connection.execute(drop)
    return refused, True
