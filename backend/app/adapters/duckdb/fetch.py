"""Reading rows out of a DuckDB relation a page at a time (D390, D391).

Names reach a statement only after they are found among the relation's own
columns, and only through `Identifier`; values go through placeholders.
"""

from dataclasses import dataclass
from typing import Any, assert_never

import duckdb

from app.adapters.duckdb.inspection import RelationFacts
from app.adapters.duckdb.relation import DuckdbRelation
from app.adapters.duckdb.session import DuckdbSession, Reading
from app.adapters.duckdb.sql import SQL, Composable, Composed, Identifier
from app.adapters.duckdb.types import is_nested, shown
from app.adapters.fetch import (
    FetchColumn,
    FetchRequest,
    FetchResult,
    Filter,
    FilterOp,
    InFilter,
    NullFilter,
    ScalarFilter,
)
from app.adapters.relation import ColumnType
from app.core.translation import N_, say

_COMPARISONS: dict[str, str] = {
    "eq": "=",
    "ne": "<>",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
}

_LIKE_ESCAPE = "!"
_LIKE = SQL("{} ILIKE ? ESCAPE '!'")

_ORDERED = frozenset({"number", "string", "datetime"})
_EQUAL = frozenset({"uuid", "enum", "other"})
_AS_TEXT = frozenset({"string", "json", "array", "composite"})


def column_capabilities(type_: ColumnType) -> list[FilterOp]:
    """What a column may be filtered with (D390)."""
    operators: list[FilterOp] = []
    category = type_.category
    if category in _ORDERED:
        operators.extend(["eq", "ne", "in", "gt", "gte", "lt", "lte"])
    elif category in _EQUAL:
        operators.extend(["eq", "ne", "in"])
    elif category == "boolean":
        operators.extend(["eq", "ne"])
    if category in _AS_TEXT:
        operators.extend(["contains", "starts_with"])
    operators.extend(["is_null", "is_not_null"])
    return operators


def _bound(value: str, type_: ColumnType) -> object:
    """The text of a filter as the value bound for this column.

    Text, which DuckDB casts to the type it infers for the placeholder from the
    column it is compared with, by its own rules; a boolean is spelt out here
    because DuckDB's cast reads `t` and `yes` as well.
    """
    if type_.category == "boolean":
        spelt = value.strip().lower()
        if spelt in ("true", "1"):
            return True
        if spelt in ("false", "0"):
            return False
        raise ValueError
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
            # The order DuckDB defines for a list or a struct is nobody's
            # expectation of a sorted grid.
            sortable=not is_nested(column.type),
            filter_operators=column_capabilities(column.type),
            nullable=column.nullable,
        )
        for column in facts.columns
    ]


def ordering_of(facts: RelationFacts) -> list[Composable]:
    """What a page is ordered by after the reader's own sort (D391)."""
    if facts.primary_key:
        return [SQL("{} ASC").format(Identifier(name)) for name in facts.primary_key]
    # The fixed word, not a name: quoted, it would be a column called rowid.
    return [SQL("rowid ASC")] if facts.has_rowid else []


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
            SQL(", ").join(shown(Identifier(column.name), column.type) for column in self.columns),
            Identifier(self.facts.schema, self.facts.name),
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


class DuckdbFetch:
    def __init__(self, session: DuckdbSession, relation: DuckdbRelation) -> None:
        self._session = session
        self._relation = relation

    async def prepare(self, request: FetchRequest) -> PreparedRead:
        facts = await self._relation.facts(request.node_id, structure=False)
        prepared = PreparedRead(facts=facts, columns=shape_of(facts), request=request)
        known = {column.name: column for column in prepared.columns}
        for used in [item.column for item in request.filters] + [
            item.column for item in request.sort
        ]:
            if used not in known:
                raise ValueError(say('Relation has no column "{column}"', column=used))
        for item in request.sort:
            if not known[item.column].sortable:
                raise ValueError(say("{column} cannot be sorted", column=item.column))
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

        def read(reading: Reading) -> list[tuple[Any, ...]]:
            try:
                return reading.tuples(text, params)
            except duckdb.ConversionException:
                # A date, a decimal or a UUID DuckDB cannot read: the
                # reader's mistake, and the text is not shown (D390).
                raise ValueError(say("A filter value does not fit its column's type")) from None

        rows = await self._session.read(read, fallback_message=N_("Query failed"))
        refused = say("Rows of a DuckDB file are read only for now")
        return FetchResult(
            columns=prepared.columns,
            rows=[
                [None if cell is None else str(cell) for cell in row]
                for row in rows[: request.limit]
            ],
            has_more=len(rows) > request.limit,
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
    name = Identifier(column.name)

    def bound(value: str) -> object:
        try:
            return _bound(value, column.type)
        except ValueError:
            raise ValueError(say('Invalid value for column "{name}"', name=column.name)) from None

    match filter_:
        case NullFilter(op=op):
            return SQL("{} IS NULL" if op == "is_null" else "{} IS NOT NULL").format(name)
        case InFilter(values=values):
            params.extend(bound(value) for value in values)
            return SQL("{} IN ({})").format(name, SQL(", ").join(SQL("?") for _ in values))
        case ScalarFilter(op="contains" | "starts_with", value=value):
            # The text a value is shown as, so what matches is what is seen.
            params.append(_like(value, starts=filter_.op == "starts_with"))
            return _LIKE.format(shown(name, column.type))
        case ScalarFilter(op=op, value=value):
            params.append(bound(value))
            return SQL("{} " + _COMPARISONS[op] + " ?").format(name)
        case unreachable:
            assert_never(unreachable)
