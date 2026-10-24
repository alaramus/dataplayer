"""Reading rows out of a SQLite relation a page at a time.

Names reach a statement only after they are found among the relation's own
columns, and only through `Identifier`; values go through placeholders.
"""

import math
import re
from dataclasses import dataclass
from typing import Any, assert_never

from app.adapters.fetch import (
    FetchColumn,
    FetchReference,
    FetchRequest,
    FetchResult,
    Filter,
    FilterOp,
    InFilter,
    NullFilter,
    ScalarFilter,
)
from app.adapters.relation import ColumnType
from app.adapters.sqlite.inspection import SCHEMA, RelationFacts
from app.adapters.sqlite.relation import SqliteRelation
from app.adapters.sqlite.session import Reading, SqliteSession
from app.adapters.sqlite.sql import SQL, Composable, Composed, Identifier
from app.adapters.sqlite.types import read_cell
from app.core.translation import N_, say

_COMPARISONS: dict[str, str] = {
    "eq": "=",
    "ne": "<>",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
}

# Named beside LIKE: SQLite's LIKE has no escape character unless told one.
_LIKE_ESCAPE = "!"
_LIKE = SQL("{} LIKE ? ESCAPE '!'")

_INTEGER = re.compile(r"[+-]?\d+")
# What fits SQLite's 64-bit integer; a longer one is compared as a real.
_INTEGER_RANGE = range(-(2**63), 2**63)

_ORDERED_COMPARED = frozenset({"number", "string", "datetime"})
# Compared as the text they hold: SQLite has no class of their own for them.
_AS_TEXT = frozenset({"json", "other"})


def column_capabilities(type_: ColumnType) -> list[FilterOp]:
    """What a column may be filtered with; every column sorts (D250).

    SQLite orders any mix of classes the same way every time — numbers, then
    text, then blobs — so sorting needs no category.
    """
    operators: list[FilterOp] = []
    category = type_.category
    if category in _ORDERED_COMPARED:
        operators.extend(["eq", "ne", "in", "gt", "gte", "lt", "lte"])
    elif category in ("uuid", "other"):
        operators.extend(["eq", "ne", "in"])
    elif category in ("boolean", "json"):
        operators.extend(["eq", "ne"])
    if category in ("string", "json", "other"):
        operators.extend(["contains", "starts_with"])
    operators.extend(["is_null", "is_not_null"])
    return operators


def coerce_filter_value(value: str, type_: ColumnType) -> object:
    """The text of a filter as the value bound for this column (D250).

    A number is bound as a number. Anything else is bound as text, which a
    column of numeric affinity converts as it would for the comparison.
    """
    match type_.category:
        case "number":
            if _INTEGER.fullmatch(value.strip()) and int(value) in _INTEGER_RANGE:
                return int(value)
            number = float(value)
            if not math.isfinite(number):
                raise ValueError
            return number
        case "boolean":
            spelt = value.strip().lower()
            if spelt in ("true", "1"):
                return 1
            if spelt in ("false", "0"):
                return 0
            raise ValueError
        case "binary":
            raise ValueError
        case _:
            return value


def _like(value: str, *, starts: bool) -> str:
    escaped = (
        value.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
        .replace("%", f"{_LIKE_ESCAPE}%")
        .replace("_", f"{_LIKE_ESCAPE}_")
    )
    return f"{escaped}%" if starts else f"%{escaped}%"


def shape_of(facts: RelationFacts) -> list[FetchColumn]:
    """The columns of a page. Nothing is written through it in this slice."""
    return [
        FetchColumn(
            name=column.name,
            type=column.type,
            sortable=True,
            filter_operators=column_capabilities(column.type),
            nullable=column.nullable,
        )
        for column in facts.columns
    ]


def ordering_of(facts: RelationFacts) -> list[Composable]:
    """What a page is ordered by after the reader's own sort (D251)."""
    if facts.primary_key:
        return [SQL("{} ASC").format(Identifier(name)) for name in facts.primary_key]
    rowid = facts.rowid
    # A fixed word from this package, not a name: quoted, `rowid` would be a
    # column of that name if the table had one.
    return [] if rowid is None else [SQL(f"{rowid} ASC")]


@dataclass(frozen=True)
class PreparedRead:
    """One validated read, shared by a page and, later, an export."""

    facts: RelationFacts
    columns: list[FetchColumn]
    request: FetchRequest

    def statement(self, params: list[Any]) -> Composed:
        """SELECT, WHERE and ORDER BY, without a page."""
        known = {column.name: column for column in self.columns}
        conditions = [_condition(filter_, known, params) for filter_ in self.request.filters]
        statement: Composed = SQL("SELECT {} FROM {}").format(
            SQL(", ").join(Identifier(column.name) for column in self.columns),
            Identifier(SCHEMA, self.facts.name),
        )
        if conditions:
            statement += SQL(" WHERE ") + SQL(" AND ").join(conditions)
        ordering: list[Composable] = [
            SQL("{} DESC" if item.descending else "{} ASC").format(Identifier(item.column))
            for item in self.request.sort
        ]
        ordering += ordering_of(self.facts)
        if ordering:
            statement += SQL(" ORDER BY ") + SQL(", ").join(ordering)
        return statement


class SqliteFetch:
    def __init__(self, session: SqliteSession, relation: SqliteRelation) -> None:
        self._session = session
        self._relation = relation

    async def prepare(self, request: FetchRequest) -> PreparedRead:
        facts = await self._relation.facts(request.node_id, structure=False)
        prepared = PreparedRead(facts=facts, columns=shape_of(facts), request=request)
        known = {column.name for column in prepared.columns}
        for used in [item.column for item in request.filters] + [
            item.column for item in request.sort
        ]:
            if used not in known:
                raise ValueError(say('Relation has no column "{column}"', column=used))
        # Every filter is checked once here, so a bad one is refused before
        # the file is read.
        prepared.statement([])
        return prepared

    async def fetch(self, request: FetchRequest) -> FetchResult:
        prepared = await self.prepare(request)
        params: list[Any] = []
        statement = prepared.statement(params) + SQL(" LIMIT ? OFFSET ?")
        params.extend([request.limit + 1, request.offset])
        text = statement.text()

        def read(reading: Reading) -> list[dict[str, Any]]:
            return reading.rows(text, tuple(params))

        rows = await self._session.read(read, fallback_message=N_("Query failed"))
        columns = prepared.columns
        facts = prepared.facts
        refused = say("Rows of a SQLite file are read only for now")
        return FetchResult(
            columns=columns,
            rows=[
                [read_cell(row[column.name], column.type) for column in columns]
                for row in rows[: request.limit]
            ],
            has_more=len(rows) > request.limit,
            references=[
                FetchReference(
                    name=key.name,
                    columns=key.columns,
                    target_title=f"{SCHEMA}.{key.target_table}",
                )
                for key in facts.foreign_keys
            ],
            update_reason=refused,
            insert_reason=refused,
            delete_reason=refused,
        )


def _condition(filter_: Filter, known: dict[str, FetchColumn], params: list[Any]) -> Composable:
    column = known[filter_.column]
    if filter_.op not in column.filter_operators:
        raise ValueError(
            say('Cannot filter column "{name}" with "{op}"', name=column.name, op=filter_.op)
        )
    name: Composable = Identifier(column.name)
    if column.type.category in _AS_TEXT:
        # A column with no declared type keeps each value in its own class,
        # and text bound for it would never equal a number stored there.
        name = SQL("CAST({} AS TEXT)").format(name)

    def coerced(value: str) -> object:
        try:
            return coerce_filter_value(value, column.type)
        except ValueError:
            raise ValueError(say('Invalid value for column "{name}"', name=column.name)) from None

    match filter_:
        case NullFilter(op=op):
            return SQL("{} IS NULL" if op == "is_null" else "{} IS NOT NULL").format(
                Identifier(column.name)
            )
        case InFilter(values=values):
            params.extend(coerced(value) for value in values)
            return SQL("{} IN ({})").format(name, SQL(", ").join(SQL("?") for _ in values))
        case ScalarFilter(op="contains" | "starts_with", value=value):
            params.append(_like(value, starts=filter_.op == "starts_with"))
            return _LIKE.format(name)
        case ScalarFilter(op=op, value=value):
            params.append(coerced(value))
            return SQL("{} " + _COMPARISONS[op] + " ?").format(name)
        case unreachable:
            assert_never(unreachable)
