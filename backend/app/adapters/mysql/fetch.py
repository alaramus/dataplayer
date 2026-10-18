"""Reading rows out of a MySQL relation a page at a time.

Names reach a statement only after they are found among the relation's own
columns, and only through `identifier`; values go through placeholders.
"""

import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, assert_never

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
from app.adapters.mysql.inspection import RelationFacts
from app.adapters.mysql.relation import MysqlRelation
from app.adapters.mysql.session import MysqlSession
from app.adapters.mysql.sql import SQL, Composable, Composed, Identifier
from app.adapters.mysql.types import read_cell
from app.adapters.relation import ColumnType
from app.core.translation import say

_COMPARISONS: dict[str, str] = {
    "eq": "=",
    "ne": "<>",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
}

# Written beside `LIKE` rather than relying on the backslash, whose meaning in a
# string literal changes with NO_BACKSLASH_ESCAPES.
_LIKE_ESCAPE = "!"
_LIKE = SQL("{} LIKE %s ESCAPE '!'")

# A TIME as MySQL accepts one: it may be negative and past a day, which a
# Python time cannot hold, so the text is checked and sent as it is.
_TIME = re.compile(r"-?\d{1,3}:\d{2}(:\d{2}(\.\d{1,6})?)?")

# The categories PostgreSQL's grid offers each operator to, kept apart rather
# than shared: which text a datetime filter is parsed as is a fact of each
# server's types, and MySQL's are spelt differently.
_ORDERED = frozenset({"number", "string", "datetime", "uuid", "enum"})
_COMPARED = frozenset({"number", "string", "datetime"})
_EQUAL = frozenset({"number", "string", "datetime", "uuid", "enum"})


def _base_type(type_: ColumnType) -> str:
    return type_.sql.split("(", 1)[0].split(" ", 1)[0].lower()


def column_capabilities(type_: ColumnType) -> tuple[bool, list[FilterOp]]:
    operators: list[FilterOp] = []
    if type_.category in _EQUAL:
        operators.extend(["eq", "ne", "in"])
    if type_.category in _COMPARED:
        operators.extend(["gt", "gte", "lt", "lte"])
    if type_.category == "string":
        operators.extend(["contains", "starts_with"])
    operators.extend(["is_null", "is_not_null"])
    return type_.category in _ORDERED, operators


def coerce_filter_value(value: str, type_: ColumnType) -> object:
    """The text of a filter as the value the driver sends for this column."""
    try:
        match type_.category:
            case "number":
                return Decimal(value)
            case "datetime":
                match _base_type(type_):
                    case "date":
                        return date.fromisoformat(value)
                    case "time":
                        if _TIME.fullmatch(value) is None:
                            raise ValueError
                        return value
                    case kind:
                        moment = datetime.fromisoformat(value)
                        # A TIMESTAMP is read and compared in UTC (D230); a
                        # DATETIME has no zone, and an offset typed for one
                        # is not the server's to apply.
                        if moment.tzinfo is not None and kind == "timestamp":
                            moment = moment.astimezone(UTC)
                        return moment.replace(tzinfo=None)
            case "string" | "enum" | "uuid":
                return value
            case _:
                raise ValueError
    except (InvalidOperation, ValueError):
        raise ValueError from None


def _like(value: str, *, starts: bool) -> str:
    escaped = (
        value.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
        .replace("%", f"{_LIKE_ESCAPE}%")
        .replace("_", f"{_LIKE_ESCAPE}_")
    )
    return f"{escaped}%" if starts else f"%{escaped}%"


def select_expression(column: FetchColumn) -> Composable:
    name = Identifier(column.name)
    # Geometry crosses as text the server writes, as PostgreSQL's does: its
    # bytes are a format with the SRID in front.
    if column.type.category == "geometric":
        return SQL("ST_AsText({}) AS {}").format(name, name)
    return name


class MysqlFetch:
    def __init__(self, session: MysqlSession, relation: MysqlRelation) -> None:
        self._session = session
        self._relation = relation

    async def fetch(self, request: FetchRequest) -> FetchResult:
        facts = await self._relation.facts(request.node_id, structure=False)
        columns = _columns(facts)
        known = {column.name: column for column in columns}
        for used in [item.column for item in request.filters] + [item.column for item in request.sort]:
            if used not in known:
                raise ValueError(say('Relation has no column "{column}"', column=used))
        for sort in request.sort:
            if not known[sort.column].sortable:
                raise ValueError(say('Cannot sort column "{column}"', column=sort.column))

        params: list[Any] = []
        conditions = [_condition(filter_, known, params) for filter_ in request.filters]
        statement: Composed = SQL("SELECT {} FROM {}").format(
            SQL(", ").join(select_expression(column) for column in columns),
            Identifier(facts.schema, facts.name),
        )
        if conditions:
            statement += SQL(" WHERE ") + SQL(" AND ").join(conditions)
        ordering: list[Composable] = [
            SQL("{} DESC" if item.descending else "{} ASC").format(Identifier(item.column))
            for item in request.sort
        ]
        # Always after what the reader asked for, so page two does not repeat
        # page one (D231). A relation with no such key has nothing honest to add.
        ordering += [SQL("{} ASC").format(Identifier(name)) for name in facts.ordering_key]
        if ordering:
            statement += SQL(" ORDER BY ") + SQL(", ").join(ordering)
        statement += SQL(" LIMIT %s OFFSET %s")
        params.extend([request.limit + 1, request.offset])

        rows = await self._session.query(statement.text(), tuple(params))
        page = rows[: request.limit]
        refused = say("Changing rows of a MySQL relation is not supported yet")
        return FetchResult(
            columns=columns,
            rows=[[read_cell(row[column.name], column.type) for column in columns] for row in page],
            has_more=len(rows) > request.limit,
            row_handles=[None] * len(page),
            update_reason=refused,
            insert_reason=refused,
            delete_reason=refused,
        )


def _columns(facts: RelationFacts) -> list[FetchColumn]:
    columns: list[FetchColumn] = []
    for column in facts.columns:
        sortable, operators = column_capabilities(column.type)
        columns.append(
            FetchColumn(
                name=column.name,
                type=column.type,
                sortable=sortable,
                filter_operators=operators,
                nullable=column.nullable,
                has_default=column.default is not None or column.auto_increment,
            )
        )
    return columns


def _condition(filter_: Filter, known: dict[str, FetchColumn], params: list[Any]) -> Composable:
    column = known[filter_.column]
    if filter_.op not in column.filter_operators:
        raise ValueError(
            say('Cannot filter column "{name}" with "{op}"', name=column.name, op=filter_.op)
        )
    name = Identifier(column.name)

    def coerced(value: str) -> object:
        try:
            return coerce_filter_value(value, column.type)
        except ValueError:
            raise ValueError(say('Invalid value for column "{name}"', name=column.name)) from None

    match filter_:
        case NullFilter(op=op):
            return SQL("{} IS NULL" if op == "is_null" else "{} IS NOT NULL").format(name)
        case InFilter(values=values):
            params.extend(coerced(value) for value in values)
            return SQL("{} IN ({})").format(name, SQL(", ").join(SQL("%s") for _ in values))
        case ScalarFilter(op="contains" | "starts_with", value=value):
            params.append(_like(value, starts=filter_.op == "starts_with"))
            return _LIKE.format(name)
        case ScalarFilter(op=op, value=value):
            params.append(coerced(value))
            return SQL("{} " + _COMPARISONS[op] + " %s").format(name)
        case unreachable:
            assert_never(unreachable)
