"""Changing the columns of a MySQL table (D27, D235).

A type or a nullability change is `MODIFY` with the column's own definition,
as the server prints it, changed in that one place (see `definitions`). Every
statement runs in strict mode, so a value a new type cannot hold refuses the
change rather than being stored as the nearest value it can.
"""

from typing import Any

import pymysql

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
from app.adapters.mysql.definitions import column_definition
from app.adapters.mysql.inspection import RelationFacts
from app.adapters.mysql.relation import MysqlRelation
from app.adapters.mysql.session import VALUE_ERRORS, MysqlSession, Writing
from app.adapters.mysql.sql import SQL, Composable, Identifier
from app.adapters.mysql.vocabulary import COLUMN_TYPES, is_text
from app.core.translation import N_, say

# MySQL allows 64 characters for a column's name and truncates nothing: past
# it the statement is refused, which is said here first.
NAME_LIMIT = 64

# How far a count of what stands in the way goes before it says "a lot".
COUNT_CEILING = 1000

COLUMN_REFUSALS: dict[int, str] = {
    1060: N_("Relation already has a column of that name"),
    1067: N_("Remove the column's default before changing its type"),
    1063: N_("An AUTO_INCREMENT column must stay an integer"),
    1090: N_("A table must keep at least one column"),
    1101: N_("A text, blob or JSON column cannot have a literal default"),
    1170: N_("A text or blob column in a key needs a length; use Text rather than Long text"),
    1553: N_("A foreign key needs an index on this column"),
    1828: N_("A foreign key uses this column"),
    3959: N_("A foreign key uses this column"),
    3108: N_("A generated column uses this column"),
    3753: N_("A JSON column cannot be part of a key"),
}


def _check_name(name: str) -> None:
    if len(name) > NAME_LIMIT:
        raise ValueError(say("A MySQL column name cannot exceed {limit} characters", limit=NAME_LIMIT))


async def bounded_count(session: MysqlSession, body: Composable, params: tuple[object, ...] = ()) -> tuple[int, bool]:
    """How many rows `body` selects, up to the ceiling, and whether that was all."""
    statement = SQL("SELECT COUNT(*) AS found FROM ({} LIMIT {}) AS sample").format(
        body, SQL(str(COUNT_CEILING + 1))
    )
    rows = await session.query(statement.text(), params)
    found = int(rows[0]["found"])
    return min(found, COUNT_CEILING), found <= COUNT_CEILING


# Setting a default meets 1067 for the value, not for a type being changed.
DEFAULT_REFUSALS: dict[int, str] = {
    **COLUMN_REFUSALS,
    1067: N_("The column's type cannot hold that default"),
}


class MysqlColumns:
    def __init__(self, session: MysqlSession, relation: MysqlRelation) -> None:
        self._session = session
        self._relation = relation

    async def _table(self, node_id: str) -> RelationFacts:
        facts = await self._relation.facts(node_id, structure=False)
        model_reason = self._relation.structure_reason(facts)
        if model_reason is not None:
            raise ValueError(model_reason)
        return facts

    @staticmethod
    def _names(facts: RelationFacts) -> set[str]:
        # Column names are not case-sensitive in MySQL.
        return {column.name.lower() for column in facts.columns}

    @staticmethod
    def _column(facts: RelationFacts, name: str) -> Any:
        column = next((column for column in facts.columns if column.name == name), None)
        if column is None:
            raise ValueError(say('Relation has no column "{column}"', column=name))
        return column

    async def _alter(
        self,
        facts: RelationFacts,
        action: Composable,
        params: tuple[object, ...] = (),
        refusals: dict[int, str] = COLUMN_REFUSALS,
    ) -> None:
        statement = SQL("ALTER TABLE {} ").format(Identifier(facts.schema, facts.name)) + action
        async with self._session.altering(refusals=refusals) as work:
            await work.execute(statement.text(), params)

    async def add_column(self, request: AddColumnRequest) -> ColumnChangeResult:
        facts = await self._table(request.node_id)
        _check_name(request.name)
        if request.name.lower() in self._names(facts):
            raise ValueError(say('Relation already has a column "{name}"', name=request.name))
        option = COLUMN_TYPES.get(request.type_code)
        if option is None:
            raise ValueError(say('Unknown column type "{code}"', code=request.type_code))
        action = SQL("ADD COLUMN {} " + option.sql + (" NOT NULL" if not request.nullable else "")).format(
            Identifier(request.name)
        )
        await self._alter(facts, action)
        return ColumnChangeResult(name=request.name)

    async def drop_column(self, request: DropColumnRequest) -> ColumnChangeResult:
        facts = await self._table(request.node_id)
        self._column(facts, request.name)
        await self._alter(facts, SQL("DROP COLUMN {}").format(Identifier(request.name)))
        return ColumnChangeResult(name=request.name)

    async def rename_column(self, request: RenameColumnRequest) -> ColumnChangeResult:
        facts = await self._table(request.node_id)
        self._column(facts, request.name)
        _check_name(request.new_name)
        if request.new_name.lower() in self._names(facts) and request.new_name.lower() != request.name.lower():
            raise ValueError(say('Relation already has a column "{name}"', name=request.new_name))
        await self._alter(
            facts,
            SQL("RENAME COLUMN {} TO {}").format(Identifier(request.name), Identifier(request.new_name)),
        )
        return ColumnChangeResult(name=request.new_name)

    async def change_column_default(self, request: ColumnDefaultRequest) -> ColumnChangeResult:
        facts = await self._table(request.node_id)
        column = self._column(facts, request.name)
        if column.generated is not None:
            raise ValueError(say("A generated column cannot have a default"))
        if request.action == "drop":
            action = SQL("ALTER COLUMN {} DROP DEFAULT").format(Identifier(request.name))
            await self._alter(facts, action)
        else:
            # A literal, bound by the driver and read by the server as the
            # column's own type; never an expression (D2c).
            action = SQL("ALTER COLUMN {} SET DEFAULT %s").format(Identifier(request.name))
            await self._alter(facts, action, (request.value,), DEFAULT_REFUSALS)
        return ColumnChangeResult(name=request.name)

    async def change_column_nullability(self, request: ColumnNullabilityRequest) -> ColumnNullabilityResult:
        facts = await self._table(request.node_id)
        column = self._column(facts, request.name)
        if column.generated is not None:
            raise ValueError(say("A generated column takes its value from its expression"))
        if column.nullable == request.nullable:
            raise ValueError(
                say("The column already accepts rows with no value")
                if request.nullable
                else say("The column already requires a value in every row")
            )
        if request.nullable and column.name in facts.primary_key:
            raise ValueError(say('Column "{name}" is part of primary key "{key}"', name=column.name, key="PRIMARY"))
        if not request.nullable:
            # Before the change and outside it: strict mode is what makes the
            # change safe, and this is what makes a refusal a number.
            blocking, exact = await bounded_count(
                self._session,
                SQL("SELECT 1 FROM {} WHERE {} IS NULL").format(
                    Identifier(facts.schema, facts.name), Identifier(column.name)
                ),
            )
            if blocking:
                return NullabilityBlocked(name=column.name, rows_without_value=blocking, exact=exact)
        definition = await column_definition(self._session, facts.schema, facts.name, column.name)
        await self._modify(facts, column.name, definition.with_nullability(request.nullable))
        return NullabilityChanged(name=column.name, nullable=request.nullable)

    async def change_column_type(self, request: ColumnTypeRequest) -> ColumnTypeChangeResult:
        facts = await self._table(request.node_id)
        column = self._column(facts, request.name)
        if column.generated is not None:
            raise ValueError(say("A generated column takes its type from its expression"))
        option = COLUMN_TYPES.get(request.type_code)
        if option is None:
            raise ValueError(say('Unknown column type "{code}"', code=request.type_code))
        if column.type.sql == option.sql:
            raise ValueError(say('The column already has type "{sql}"', sql=option.sql))
        definition = await column_definition(self._session, facts.schema, facts.name, column.name)
        changed = definition.with_type(
            option.sql, keeps_charset=is_text(column.type.sql) and is_text(option.sql)
        )
        try:
            await self._modify(facts, column.name, changed, values_refused=True)
        except _ValuesRefused:
            blocking, exact = await self._unconvertible(facts, column.name, option.sql)
            return ColumnTypeBlocked(
                name=column.name, rows_not_convertible=max(blocking, 1), exact=exact
            )
        return ColumnTypeChanged(name=column.name, type_sql=option.sql)

    async def _modify(
        self, facts: RelationFacts, name: str, definition: str, *, values_refused: bool = False
    ) -> None:
        """`MODIFY COLUMN` with a definition the server itself printed.

        The text is the server's own, changed in one place by this package; a
        `%` in it is doubled for the driver, as in any statement here.
        """
        statement = SQL("ALTER TABLE {} MODIFY COLUMN {} " + definition.replace("%", "%%")).format(
            Identifier(facts.schema, facts.name), Identifier(name)
        )
        async with self._session.altering(refusals=COLUMN_REFUSALS) as work:
            await _run(work, statement.text(), values_refused)

    async def _unconvertible(self, facts: RelationFacts, name: str, type_sql: str) -> tuple[int, bool]:
        """How many values the new type refuses, counted by the server.

        Each value is put into a temporary column of the new type with IGNORE,
        which turns every refusal into a warning; the warnings are the count.
        Only asked once the change itself has been refused, so a change that
        goes through scans the table once.
        """
        probe = Identifier(facts.schema, "dp_type_probe")
        drop = SQL("DROP TEMPORARY TABLE IF EXISTS {}").format(probe).text()
        async with self._session.altering() as work:
            await work.execute(drop)
            await work.execute(
                SQL("CREATE TEMPORARY TABLE {} (`v` " + type_sql + " NULL)").format(probe).text()
            )
            try:
                found = await work.warnings(
                    SQL("INSERT IGNORE INTO {} (`v`) SELECT {} FROM {} WHERE {} IS NOT NULL").format(
                        probe,
                        Identifier(name),
                        Identifier(facts.schema, facts.name),
                        Identifier(name),
                    ).text()
                )
            finally:
                await work.execute(drop)
        return min(found, COUNT_CEILING), found <= COUNT_CEILING


class _ValuesRefused(Exception):
    """The new type cannot hold some value the column already has."""


async def _run(work: Writing, statement: str, values_refused: bool) -> None:
    try:
        await work.execute(statement)
    except pymysql.err.MySQLError as exc:
        if values_refused and exc.args and exc.args[0] in VALUE_ERRORS:
            raise _ValuesRefused from None
        raise
