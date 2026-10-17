"""Counting what stands in the way of a structure change.

Every command that the data can stop asks the same question before it locks
anything: how much of the data contradicts what is being asked for. The answers
differ — rows with no value, values the new type cannot read, values that
repeat, rows pointing at nothing — but the shape does not, so the shape lives
here: one bounded count, and whether the count is the whole truth.

Bounded because an unbounded scan is not run anywhere in this application. Past
the ceiling the answer is "a lot", which is all the reader's next decision
needs.
"""

from collections.abc import Mapping

from psycopg import sql

from app.adapters.postgres.session import PostgresSession
from app.core.translation import N_

COUNT_CEILING = 1000


async def _count(
    session: PostgresSession,
    body: sql.Composed | sql.SQL,
    params: tuple[object, ...] | None = None,
    refusals: Mapping[str, str] | None = None,
) -> tuple[int, bool]:
    """Run one bounded counting query and say whether it reached its ceiling.

    The refusals travel too: a count can be refused for the same reason the
    change it precedes would be — two columns that cannot be compared, for
    instance — and that is a bad request, not an unwell source.
    """
    statement = sql.SQL("SELECT count(*) AS found FROM ({} LIMIT {}) AS sample").format(
        body, sql.Literal(COUNT_CEILING + 1)
    )
    rows = await session.query(statement.as_string(), params, refusals=refusals)
    found = int(rows[0]["found"])
    return min(found, COUNT_CEILING), found <= COUNT_CEILING


async def rows_without_value(
    session: PostgresSession, schema: str, table: str, column: str
) -> tuple[int, bool]:
    """Rows holding nothing in this column — what a NOT NULL would reject."""
    body = sql.SQL("SELECT 1 FROM {} WHERE {} IS NULL").format(
        sql.Identifier(schema, table), sql.Identifier(column)
    )
    return await _count(session, body)


async def rows_the_type_cannot_read(
    session: PostgresSession,
    schema: str,
    table: str,
    column: str,
    type_name: str,
    refusals: Mapping[str, str] | None = None,
) -> tuple[int, bool]:
    """Values this type's input function would refuse.

    Only meaningful where converting is that input function — a string column —
    which is the caller's judgement, not this one's. The type name travels as a
    bound value, so nothing of it is composed into the statement.
    """
    body = sql.SQL(
        "SELECT 1 FROM {} WHERE {} IS NOT NULL AND NOT pg_input_is_valid({}::text, %s)"
    ).format(
        sql.Identifier(schema, table),
        sql.Identifier(column),
        sql.Identifier(column),
    )
    return await _count(session, body, (type_name,), refusals)


async def repeating_groups(
    session: PostgresSession, schema: str, table: str, columns: list[str]
) -> tuple[int, bool]:
    """Values appearing more than once — what a unique index would reject.

    Rows holding a null in any of the columns are left out: PostgreSQL is
    NULLS DISTINCT by default, so two of them do not collide, and counting them
    would refuse something the server would have accepted.
    """
    names = [sql.Identifier(name) for name in columns]
    body = sql.SQL("SELECT 1 FROM {} WHERE {} GROUP BY {} HAVING count(*) > 1").format(
        sql.Identifier(schema, table),
        sql.SQL(" AND ").join(sql.SQL("{} IS NOT NULL").format(name) for name in names),
        sql.SQL(", ").join(names),
    )
    return await _count(session, body)


async def rows_pointing_nowhere(
    session: PostgresSession,
    schema: str,
    table: str,
    columns: list[str],
    target_schema: str,
    target_table: str,
    target_columns: list[str],
    refusals: Mapping[str, str] | None = None,
) -> tuple[int, bool]:
    """Rows whose key names no row of the target — what a foreign key rejects.

    A row with a null anywhere in its key is left out, which is MATCH SIMPLE:
    PostgreSQL treats such a row as satisfying the constraint, so counting it
    would refuse a key the server would have accepted.
    """
    local = [sql.Identifier(name) for name in columns]
    matches = sql.SQL(" AND ").join(
        sql.SQL("target.{} = source.{}").format(
            sql.Identifier(target), sql.Identifier(name)
        )
        for name, target in zip(columns, target_columns, strict=True)
    )
    body = sql.SQL(
        "SELECT 1 FROM {} AS source WHERE {} "
        "AND NOT EXISTS (SELECT 1 FROM {} AS target WHERE {})"
    ).format(
        sql.Identifier(schema, table),
        sql.SQL(" AND ").join(
            sql.SQL("source.{} IS NOT NULL").format(name) for name in local
        ),
        sql.Identifier(target_schema, target_table),
        matches,
    )
    return await _count(session, body, None, refusals)


# A value that cannot be read is the same failure whichever route reaches it,
# and the sentence is all that can honestly be said when the check itself is
# the thing that failed.
VALUE_REFUSALS = {
    "22P02": N_("Some values cannot be read as the column's type"),
    "22003": N_("Some values are out of range for the column's type"),
    "22001": N_("Some values are too long for the column's type"),
}


async def unreadable_values(
    session: PostgresSession, values: list[tuple[str, str]]
) -> list[int]:
    """Which of these (value, type) pairs the type's input function refuses.

    One query for the whole block, and no ceiling: the caller is holding every
    one of these values already, and the point is to say which of them is
    wrong rather than how many. Both arrays travel as bound parameters, so
    neither a value nor a type name is composed into the statement.

    `pg_input_is_valid` reports softly for every core type. One that still
    raises would take the query with it, which is what the refusals are for:
    the answer degrades to a sentence rather than to a failure of the source.
    """
    if not values:
        return []
    statement = (
        "SELECT position - 1 AS at FROM unnest(%s::text[], %s::text[]) "
        "WITH ORDINALITY AS pair(value, type_name, position) "
        "WHERE NOT pg_input_is_valid(value, type_name)"
    )
    rows = await session.query(
        statement,
        ([value for value, _ in values], [name for _, name in values]),
        refusals=VALUE_REFUSALS,
    )
    return [int(row["at"]) for row in rows]
