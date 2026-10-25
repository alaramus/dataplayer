"""Changing the columns of a ClickHouse table (D27, D273).

A type or a nullability change is `MODIFY COLUMN` with the new type alone,
which keeps the column's default, comment and codec. ClickHouse changes the
column's type in its metadata at once and converts the rows in a mutation
afterwards; a mutation that meets a value it cannot convert leaves the table
unreadable and every later change waiting behind it. So what would stop it is
counted first, and the change is not made while anything would; if the
mutation fails all the same, it is killed and the old type put back.
"""

from app.adapters.clickhouse.inspection import ColumnFacts, RelationFacts
from app.adapters.clickhouse.relation import ClickhouseRelation, structure_reason
from app.adapters.clickhouse.session import ClickhouseSession, ServerError
from app.adapters.clickhouse.sql import SQL, Composable, Identifier, Params
from app.adapters.clickhouse.types import type_name, unwrapped
from app.adapters.clickhouse.vocabulary import COLUMN_TYPES
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
from app.core.translation import N_, say

# Every structure statement waits for what it starts, so it answers when the
# table is what it was asked to be.
ALTERING = {"mutations_sync": "1", "alter_sync": "1"}

COLUMN_REFUSALS: dict[int, str] = {
    15: N_("Relation already has a column of that name"),
    # A key, a skipping index or another column's expression uses it.
    44: N_("An index, a key or another column uses this column"),
    47: N_("An index, a key or another column uses this column"),
    524: N_("A column of the table's key cannot be changed"),
    457: N_("The column's type cannot hold that default"),
    43: N_("These two types have no conversion between them"),
    70: N_("These two types have no conversion between them"),
}

# A mutation failed on a value; it stays in the way until it is killed.
UNFINISHED_MUTATION = 341

_KILL = """
KILL MUTATION
WHERE database = {database:String} AND table = {table:String} AND NOT is_done
SYNC
"""


def table_of(facts: RelationFacts) -> Identifier:
    return Identifier(facts.schema, facts.name)


async def alter(
    session: ClickhouseSession,
    facts: RelationFacts,
    action: Composable,
    params: Params | None = None,
    *,
    refusals: dict[int, str] = COLUMN_REFUSALS,
    passing: frozenset[int] = frozenset(),
) -> None:
    statement = SQL("ALTER TABLE {} ").format(table_of(facts)) + action
    await session.command(
        statement.text(),
        {} if params is None else params.values,
        settings=ALTERING,
        refusals=refusals,
        passing=passing,
    )


async def changeable_facts(
    relation: ClickhouseRelation, node_id: str, *, structure: bool = False
) -> RelationFacts:
    """The relation, or the reason its structure cannot be changed (D273)."""
    facts = await relation.facts(node_id, structure=structure)
    refused = structure_reason(facts)
    if refused is not None:
        raise ValueError(refused)
    return facts


def nullable_form(type_sql: str) -> str:
    """The type a column that may hold NULL has, `LowCardinality` kept outside."""
    if type_name(type_sql) == "LowCardinality":
        return f"LowCardinality(Nullable({unwrapped(type_sql)}))"
    return f"Nullable({type_sql})"


def required_form(type_sql: str) -> str:
    """The same type without `Nullable`, `LowCardinality` kept."""
    inner = unwrapped(type_sql)
    if type_name(type_sql) == "LowCardinality":
        return f"LowCardinality({inner})"
    return inner


class ClickhouseColumns:
    def __init__(self, session: ClickhouseSession, relation: ClickhouseRelation) -> None:
        self._session = session
        self._relation = relation

    async def _table(self, node_id: str) -> RelationFacts:
        return await changeable_facts(self._relation, node_id)

    @staticmethod
    def _column(facts: RelationFacts, name: str, *, stored: bool = False) -> ColumnFacts:
        column = next((column for column in facts.columns if column.name == name), None)
        if column is None:
            raise ValueError(say('Relation has no column "{column}"', column=name))
        if stored and column.generated is not None:
            raise ValueError(say("A generated column takes its value from its expression"))
        return column

    @staticmethod
    def _not_key(column: ColumnFacts) -> None:
        if column.in_key:
            raise ValueError(
                say(
                    'Column "{name}" is in the table\'s key, which decides where rows are kept',
                    name=column.name,
                )
            )

    async def _modify(self, facts: RelationFacts, column: ColumnFacts, type_sql: str) -> None:
        """`MODIFY COLUMN` to a type, and the table put back if its mutation fails."""
        action = SQL("MODIFY COLUMN {} ").format(Identifier(column.name)) + SQL(type_sql)
        try:
            await alter(self._session, facts, action, passing=frozenset({UNFINISHED_MUTATION}))
        except ServerError:
            await self._session.command(
                _KILL, {"database": facts.schema, "table": facts.name}
            )
            await alter(
                self._session,
                facts,
                SQL("MODIFY COLUMN {} ").format(Identifier(column.name)) + SQL(column.type.sql),
            )
            raise ValueError(
                say("The server could not convert every value, and the column was left as it was")
            ) from None

    async def add_column(self, request: AddColumnRequest) -> ColumnChangeResult:
        facts = await self._table(request.node_id)
        if any(column.name == request.name for column in facts.columns):
            raise ValueError(say('Relation already has a column "{name}"', name=request.name))
        option = COLUMN_TYPES.get(request.type_code)
        if option is None:
            raise ValueError(say('Unknown column type "{code}"', code=request.type_code))
        type_sql = nullable_form(option.sql) if request.nullable else option.sql
        # A type of the vocabulary above, written by this package.
        await alter(
            self._session,
            facts,
            SQL("ADD COLUMN {} ").format(Identifier(request.name)) + SQL(type_sql),
        )
        return ColumnChangeResult(name=request.name)

    async def drop_column(self, request: DropColumnRequest) -> ColumnChangeResult:
        facts = await self._table(request.node_id)
        self._not_key(self._column(facts, request.name))
        await alter(self._session, facts, SQL("DROP COLUMN {}").format(Identifier(request.name)))
        return ColumnChangeResult(name=request.name)

    async def rename_column(self, request: RenameColumnRequest) -> ColumnChangeResult:
        facts = await self._table(request.node_id)
        self._not_key(self._column(facts, request.name))
        if any(column.name == request.new_name for column in facts.columns):
            raise ValueError(say('Relation already has a column "{name}"', name=request.new_name))
        await alter(
            self._session,
            facts,
            SQL("RENAME COLUMN {} TO {}").format(Identifier(request.name), Identifier(request.new_name)),
        )
        return ColumnChangeResult(name=request.new_name)

    async def change_column_default(self, request: ColumnDefaultRequest) -> ColumnChangeResult:
        facts = await self._table(request.node_id)
        column = self._column(facts, request.name, stored=True)
        if request.action == "drop":
            if column.default is None:
                raise ValueError(say("The column has no default to remove"))
            await alter(
                self._session, facts, SQL("MODIFY COLUMN {} REMOVE DEFAULT").format(Identifier(column.name))
            )
            return ColumnChangeResult(name=column.name)
        # A literal, a parameter the server reads as the column's own type and
        # keeps as a constant; never an expression (D2c). The type is the
        # server's own text from system.columns.
        params = Params()
        value = params.add(request.value or "", unwrapped(column.type.sql))
        await alter(
            self._session,
            facts,
            SQL("MODIFY COLUMN {} DEFAULT {}").format(Identifier(column.name), value),
            params,
        )
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
        self._not_key(column)
        if request.nullable:
            await self._modify(facts, column, nullable_form(column.type.sql))
            return NullabilityChanged(name=column.name, nullable=True)
        rows = await self._session.query(
            SQL("SELECT count() AS found FROM {} WHERE {} IS NULL")
            .format(table_of(facts), Identifier(column.name))
            .text()
        )
        blocking = int(rows[0]["found"])
        if blocking:
            return NullabilityBlocked(name=column.name, rows_without_value=blocking)
        await self._modify(facts, column, required_form(column.type.sql))
        return NullabilityChanged(name=column.name, nullable=False)

    async def change_column_type(self, request: ColumnTypeRequest) -> ColumnTypeChangeResult:
        facts = await self._table(request.node_id)
        column = self._column(facts, request.name, stored=True)
        option = COLUMN_TYPES.get(request.type_code)
        if option is None:
            raise ValueError(say('Unknown column type "{code}"', code=request.type_code))
        self._not_key(column)
        target = nullable_form(option.sql) if column.nullable else option.sql
        if column.type.sql == target:
            raise ValueError(say('The column already has type "{sql}"', sql=target))
        # Counted before anything changes: a failed conversion is a broken
        # table here, not a refused statement.
        params = Params()
        statement = SQL(
            "SELECT count() AS found FROM {} WHERE {} IS NOT NULL AND accurateCastOrNull({}, {}) IS NULL"
        ).format(
            table_of(facts),
            Identifier(column.name),
            Identifier(column.name),
            params.add(unwrapped(option.sql), "String"),
        )
        try:
            rows = await self._session.answer(statement.text(), params.values, server_errors=True)
        except ServerError:
            raise ValueError(say("These two types have no conversion between them")) from None
        blocking = int(rows.rows[0][0])
        if blocking:
            return ColumnTypeBlocked(name=column.name, rows_not_convertible=blocking)
        await self._modify(facts, column, target)
        return ColumnTypeChanged(name=column.name, type_sql=target)
