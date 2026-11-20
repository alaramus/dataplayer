"""Changing the columns of a DuckDB table, each in place (D396).

Every change is DuckDB's own ALTER TABLE, in one transaction with the counts
before it and the views bound after it (`restructure`). What DuckDB refuses —
dropping a column an index depends on, retyping an indexed one — is said in
its own sentence.
"""

import duckdb

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
from app.adapters.duckdb.inspection import ColumnFacts, RelationFacts
from app.adapters.duckdb.relation import DuckdbRelation
from app.adapters.duckdb.session import DuckdbSession
from app.adapters.duckdb.sql import SQL, Identifier
from app.adapters.duckdb.structure import (
    bounded_count,
    restructure,
    structure_reason,
    table_of,
)
from app.adapters.duckdb.vocabulary import column_type
from app.core.translation import say


def literal(text: str) -> str:
    """A string literal as DuckDB reads one: a quote is doubled."""
    if "\x00" in text:
        raise ValueError(say("A value cannot contain a NUL character"))
    return "'" + text.replace("'", "''") + "'"


class DuckdbColumns:
    def __init__(self, session: DuckdbSession, relation: DuckdbRelation) -> None:
        self._session = session
        self._relation = relation

    async def _table(self, node_id: str) -> RelationFacts:
        facts = await self._relation.facts(node_id)
        refused = structure_reason(facts)
        if refused is not None:
            raise ValueError(refused)
        return facts

    @staticmethod
    def _column(facts: RelationFacts, name: str, *, stored: bool = False) -> ColumnFacts:
        column = next((column for column in facts.columns if column.name == name), None)
        if column is None:
            raise ValueError(say('Relation has no column "{column}"', column=name))
        if stored and column.generated is not None:
            raise ValueError(say("A generated column takes its value from its expression"))
        return column

    @staticmethod
    def _free(facts: RelationFacts, name: str) -> None:
        # DuckDB compares names without case.
        if any(column.name.lower() == name.lower() for column in facts.columns):
            raise ValueError(say('Relation already has a column "{name}"', name=name))

    async def add_column(self, request: AddColumnRequest) -> ColumnChangeResult:
        facts = await self._table(request.node_id)
        self._free(facts, request.name)
        option = column_type(request.type_code)
        if option is None:
            raise ValueError(say('Unknown column type "{code}"', code=request.type_code))
        # A type of the vocabulary, written by this package.
        statement = SQL("ALTER TABLE {} ADD COLUMN {} " + option.sql).format(
            table_of(facts), Identifier(request.name)
        )
        if not request.nullable:
            statement += SQL(" NOT NULL")
        has_rows = SQL("SELECT 1 FROM {} LIMIT 1").format(table_of(facts))

        def work(connection: duckdb.DuckDBPyConnection) -> None:
            if not request.nullable and connection.execute(has_rows.text()).fetchone() is not None:
                raise ValueError(
                    say("A column that must have a value cannot be added to a table that has rows")
                )
            connection.execute(statement.text())

        await restructure(self._session, work)
        return ColumnChangeResult(name=request.name)

    async def drop_column(self, request: DropColumnRequest) -> ColumnChangeResult:
        facts = await self._table(request.node_id)
        self._column(facts, request.name)
        statement = SQL("ALTER TABLE {} DROP COLUMN {}").format(
            table_of(facts), Identifier(request.name)
        )
        await restructure(
            self._session, lambda connection: connection.execute(statement.text()), views=True
        )
        return ColumnChangeResult(name=request.name)

    async def rename_column(self, request: RenameColumnRequest) -> ColumnChangeResult:
        facts = await self._table(request.node_id)
        self._column(facts, request.name)
        if request.new_name.lower() != request.name.lower():
            self._free(facts, request.new_name)
        statement = SQL("ALTER TABLE {} RENAME COLUMN {} TO {}").format(
            table_of(facts), Identifier(request.name), Identifier(request.new_name)
        )
        await restructure(
            self._session, lambda connection: connection.execute(statement.text()), views=True
        )
        return ColumnChangeResult(name=request.new_name)

    async def change_column_default(self, request: ColumnDefaultRequest) -> ColumnChangeResult:
        facts = await self._table(request.node_id)
        column = self._column(facts, request.name, stored=True)
        target = SQL("ALTER TABLE {} ALTER COLUMN {} ").format(
            table_of(facts), Identifier(column.name)
        )
        if request.action == "drop":
            if column.default is None:
                raise ValueError(say("The column has no default to remove"))
            statement = target + SQL("DROP DEFAULT")
            await restructure(self._session, lambda connection: connection.execute(statement.text()))
            return ColumnChangeResult(name=column.name)
        text = request.value or ""
        # The type is DuckDB's own text for the column, from duckdb_columns():
        # DuckDB keeps a default it cannot convert and fails at the next
        # insert, so the text is tried first and the default is of that type.
        cast = "CAST(" + literal(text) + " AS " + column.type.sql + ")"
        statement = target + SQL("SET DEFAULT " + cast)
        tried = "SELECT TRY_CAST(" + literal(text) + " AS " + column.type.sql + ") IS NULL"

        def work(connection: duckdb.DuckDBPyConnection) -> None:
            row = connection.execute(tried).fetchone()
            if row is not None and row[0]:
                raise ValueError(
                    say("That value cannot be read as {sql}", sql=column.type.sql)
                )
            connection.execute(statement.text())

        await restructure(self._session, work)
        return ColumnChangeResult(name=column.name)

    async def change_column_nullability(
        self, request: ColumnNullabilityRequest
    ) -> ColumnNullabilityResult:
        facts = await self._table(request.node_id)
        column = self._column(facts, request.name, stored=True)
        if column.nullable == request.nullable:
            raise ValueError(
                say("The column already accepts rows with no value")
                if request.nullable
                else say("The column already requires a value in every row")
            )
        if request.nullable and column.name in facts.primary_key:
            raise ValueError(say("A column of the primary key must have a value"))
        target = SQL("ALTER TABLE {} ALTER COLUMN {} ").format(
            table_of(facts), Identifier(column.name)
        )
        if request.nullable:
            statement = target + SQL("DROP NOT NULL")
            await restructure(self._session, lambda connection: connection.execute(statement.text()))
            return NullabilityChanged(name=column.name, nullable=True)
        empty = SQL("SELECT 1 FROM {} WHERE {} IS NULL").format(
            table_of(facts), Identifier(column.name)
        )
        statement = target + SQL("SET NOT NULL")

        def work(connection: duckdb.DuckDBPyConnection) -> ColumnNullabilityResult:
            found, exact = bounded_count(connection, empty)
            if found:
                return NullabilityBlocked(name=column.name, rows_without_value=found, exact=exact)
            connection.execute(statement.text())
            return NullabilityChanged(name=column.name, nullable=False)

        return await restructure(self._session, work)

    async def change_column_type(self, request: ColumnTypeRequest) -> ColumnTypeChangeResult:
        facts = await self._table(request.node_id)
        column = self._column(facts, request.name, stored=True)
        option = column_type(request.type_code)
        if option is None:
            raise ValueError(say('Unknown column type "{code}"', code=request.type_code))
        if column.type.sql == option.sql:
            raise ValueError(say('The column already has type "{sql}"', sql=option.sql))
        name = Identifier(column.name)
        # A type of the vocabulary, written by this package.
        converts = "SELECT 1 FROM {} WHERE {} IS NOT NULL AND TRY_CAST({} AS " + option.sql  # noqa: S608
        refusing = SQL(converts + ") IS NULL").format(table_of(facts), name, name)
        statement = SQL("ALTER TABLE {} ALTER COLUMN {} TYPE " + option.sql).format(
            table_of(facts), name
        )

        def work(connection: duckdb.DuckDBPyConnection) -> ColumnTypeChangeResult:
            found, exact = bounded_count(connection, refusing)
            if found:
                return ColumnTypeBlocked(name=column.name, rows_not_convertible=found, exact=exact)
            connection.execute(statement.text())
            return ColumnTypeChanged(name=column.name, type_sql=option.sql)

        return await restructure(self._session, work, views=True)
