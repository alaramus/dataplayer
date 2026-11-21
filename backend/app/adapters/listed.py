"""A list read whole and narrowed here: filters and sorts over rows in memory.

For a source whose API answers a whole list at once — a market's tickers, a
daemon's containers — and pages nothing, so every closed predicate (D2d) is
applied to the rows already read. Cells are text, compared by their column's
category: a number by its value, a moment by its time.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.adapters.fetch import (
    FetchColumn,
    Filter,
    FilterOp,
    InFilter,
    NullFilter,
    ScalarFilter,
    Sort,
)
from app.adapters.relation import ColumnType, TypeCategory
from app.core.translation import say

TEXT_OPS: list[FilterOp] = ["eq", "ne", "contains", "starts_with", "in"]
ORDER_OPS: list[FilterOp] = ["eq", "ne", "gt", "gte", "lt", "lte"]
RANGE_OPS: list[FilterOp] = ["gt", "gte", "lt", "lte"]
NULL_OPS: list[FilterOp] = ["is_null", "is_not_null"]

_SQL: dict[TypeCategory, str] = {
    "string": "text",
    "number": "numeric",
    "datetime": "timestamptz",
    "boolean": "boolean",
}


def column(
    name: str,
    category: TypeCategory,
    ops: list[FilterOp] | None = None,
    *,
    sql: str | None = None,
    sortable: bool = False,
    nullable: bool = False,
) -> FetchColumn:
    return FetchColumn(
        name=name,
        type=ColumnType(sql=sql or _SQL[category], category=category),
        sortable=sortable,
        filter_operators=ops or [],
        nullable=nullable,
    )


def listed_column(
    name: str, category: TypeCategory, *, nullable: bool = False
) -> FetchColumn:
    """A column of a list read whole: sorted and filtered here, by anything."""
    ops = list(TEXT_OPS if category == "string" else ORDER_OPS)
    if nullable:
        ops += NULL_OPS
    return column(name, category, ops, sortable=True, nullable=nullable)


def milliseconds_of(column: str, text: str) -> int:
    try:
        at = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(say("{column} takes a date and time", column=column)) from None
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    return int(at.timestamp() * 1000)


def checked_filters(filters: list[Filter], columns: list[FetchColumn]) -> None:
    offered = {column.name: column.filter_operators for column in columns}
    for one in filters:
        ops = offered.get(one.column)
        if ops is None:
            raise ValueError(say("Unknown column: {column}", column=one.column))
        if one.op not in ops:
            raise ValueError(
                say("{column} cannot be filtered that way", column=one.column)
            )


def checked_sorts(sort: list[Sort], columns: list[FetchColumn]) -> None:
    sortable = {column.name for column in columns if column.sortable}
    for one in sort:
        if one.column not in sortable:
            raise ValueError(say("{column} cannot be sorted", column=one.column))


def _key(category: TypeCategory, text: str | None) -> Any:
    """What a cell is compared by: a number by its value, a moment by its time."""
    if text is None:
        return None
    if category == "number":
        try:
            return Decimal(text)
        except InvalidOperation:
            return None
    if category == "datetime":
        return milliseconds_of("", text)
    return text.casefold()


def _matcher(
    one: Filter, index: int, category: TypeCategory
) -> Callable[[list[str | None]], bool]:
    if isinstance(one, NullFilter):
        wanted_null = one.op == "is_null"
        return lambda row: (row[index] is None) == wanted_null
    if isinstance(one, InFilter):
        wanted = {_key(category, value) for value in one.values}
        return lambda row: _key(category, row[index]) in wanted
    assert isinstance(one, ScalarFilter)
    if category == "number":
        try:
            Decimal(one.value)
        except InvalidOperation:
            raise ValueError(
                say("{column} takes a number", column=one.column)
            ) from None
    if category == "datetime":
        milliseconds_of(one.column, one.value)
    needle = _key(category, one.value)
    op = one.op

    def matches(row: list[str | None]) -> bool:
        value = _key(category, row[index])
        if value is None:
            return op == "ne"
        if op == "contains":
            return bool(needle in value)
        if op == "starts_with":
            return bool(value.startswith(needle))
        return bool(
            {
                "eq": value == needle,
                "ne": value != needle,
                "gt": value > needle,
                "gte": value >= needle,
                "lt": value < needle,
                "lte": value <= needle,
            }[op]
        )

    return matches


def listed_page(
    columns: list[FetchColumn],
    rows: list[list[str | None]],
    filters: list[Filter],
    sort: list[Sort],
) -> list[list[str | None]]:
    """Rows of a list read whole, filtered and sorted as asked."""
    checked_filters(filters, columns)
    checked_sorts(sort, columns)
    names = [column.name for column in columns]
    categories = [column.type.category for column in columns]
    for one in filters:
        index = names.index(one.column)
        keep = _matcher(one, index, categories[index])
        rows = [row for row in rows if keep(row)]
    for order in reversed(sort):
        index = names.index(order.column)
        category = categories[index]
        present = [row for row in rows if _key(category, row[index]) is not None]
        absent = [row for row in rows if _key(category, row[index]) is None]
        present.sort(
            key=lambda row: _key(category, row[index]), reverse=order.descending
        )
        rows = present + absent
    return rows
