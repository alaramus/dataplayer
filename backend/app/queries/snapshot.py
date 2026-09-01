"""Reading a captured result: what to show, in what order, and as what.

D64: paging, filters and sorting act on the captured set and say so. Nothing
here reaches a source — the rows were read once, inside the transaction that
produced them, and asking the database again would answer from a different
moment and could repeat a side effect.

The order is the platform's, not the database's collation: two sources that
captured the same values sort them the same way, and a person who sorts a
snapshot twice gets the same answer both times.
"""

import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.fetch import FilterOp, ScalarFilterOp
from app.adapters.query import MaterialisedResult, ResultColumn

# csv.QUOTE_NOTNULL keeps SQL null apart from an empty string: one is written
# as nothing at all, the other as "".
NULL_QUOTING: Final = csv.QUOTE_NOTNULL


class SnapshotScalarFilter(BaseModel):
    """One predicate over a captured column, addressed by its position."""

    model_config = ConfigDict(extra="forbid")

    column: str
    op: ScalarFilterOp
    value: str


class SnapshotInFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str
    op: Literal["in"]
    values: list[str] = Field(min_length=1)


class SnapshotNullFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str
    op: Literal["is_null", "is_not_null"]


# The same closed set the grid has, over captured text rather than over a
# source. A raw fragment is not accepted here either (D2c).
SnapshotFilter = Annotated[
    SnapshotScalarFilter | SnapshotInFilter | SnapshotNullFilter,
    Field(discriminator="op"),
]


class SnapshotSort(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str
    descending: bool = False


class SnapshotView(BaseModel):
    """What a caller wants to see of a captured result."""

    model_config = ConfigDict(extra="forbid")

    filters: list[SnapshotFilter] = Field(default_factory=list)
    sort: list[SnapshotSort] = Field(default_factory=list)


def _index_of(columns: list[ResultColumn], column_id: str) -> int:
    for index, column in enumerate(columns):
        if column.id == column_id:
            return index
    raise ValueError(f"This result has no column {column_id}")


def _number(value: str) -> Decimal | None:
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


def _moment(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def sort_key(value: str | None, category: str) -> tuple[int, Any]:
    """One value as something comparable, by what its column holds.

    Numbers compare with arbitrary precision rather than through a float,
    dates and times chronologically, booleans false before true, and anything
    else by Unicode code point. A value that does not read as its own type
    falls back to its text, which is the only honest thing left.
    """
    if value is None:
        return (1, "")
    if category == "number":
        number = _number(value)
        return (0, number) if number is not None else (0, Decimal(0))
    if category == "datetime":
        moment = _moment(value)
        return (0, moment) if moment is not None else (0, datetime.min)
    if category == "boolean":
        return (0, value == "true")
    return (0, value)


def _sortable(value: str | None, category: str, *, descending: bool) -> tuple[int, Any]:
    """The key, with null kept at the far end whichever way the column sorts.

    `reverse=True` would otherwise bring nulls to the front, and "no value" is
    not the largest value — it is the absence of one (D64).
    """
    rank, key = sort_key(value, category)
    is_null = value is None
    # Ascending: 0 for a value, 1 for null. Descending: reversed afterwards, so
    # the ranks are swapped here to leave nulls where they were.
    null_rank = (1 if is_null else 0) if not descending else (0 if is_null else 1)
    return (null_rank, key)


def _compare(cell: str | None, op: ScalarFilterOp, wanted: str, category: str) -> bool:
    if cell is None:
        return False
    if op == "contains":
        return wanted.casefold() in cell.casefold()
    if op == "starts_with":
        return cell.casefold().startswith(wanted.casefold())
    left = sort_key(cell, category)
    right = sort_key(wanted, category)
    try:
        if op == "eq":
            return cell == wanted or left == right
        if op == "ne":
            return cell != wanted and left != right
        if op == "gt":
            return left > right
        if op == "gte":
            return left >= right
        if op == "lt":
            return left < right
        if op == "lte":
            return left <= right
    except TypeError:
        # Two values of one column that do not compare as their type: fall
        # back to text rather than refusing a filter over captured rows.
        return _compare_text(cell, op, wanted)
    return False


def _compare_text(cell: str, op: FilterOp, wanted: str) -> bool:
    if op == "eq":
        return cell == wanted
    if op == "ne":
        return cell != wanted
    if op == "gt":
        return cell > wanted
    if op == "gte":
        return cell >= wanted
    if op == "lt":
        return cell < wanted
    if op == "lte":
        return cell <= wanted
    return False


def apply(result: MaterialisedResult, view: SnapshotView) -> list[list[str | None]]:
    """The captured rows this view asks for, filtered and ordered.

    The original ordinal is the tiebreaker, so a sort is stable and two calls
    with the same view answer in the same order.
    """
    rows = list(result.rows)
    for predicate in view.filters:
        index = _index_of(result.columns, predicate.column)
        category = result.columns[index].type.category
        if isinstance(predicate, SnapshotNullFilter):
            wanted_null = predicate.op == "is_null"
            rows = [row for row in rows if (row[index] is None) is wanted_null]
        elif isinstance(predicate, SnapshotInFilter):
            allowed = set(predicate.values)
            rows = [row for row in rows if row[index] in allowed]
        else:
            rows = [
                row
                for row in rows
                if _compare(row[index], predicate.op, predicate.value, category)
            ]
    # Applied last key first: Python's sort is stable, so the earlier keys win
    # and the original order survives underneath all of them.
    for order in reversed(view.sort):
        index = _index_of(result.columns, order.column)
        category = result.columns[index].type.category
        rows.sort(
            key=lambda row, index=index, category=category, order=order: _sortable(  # type: ignore[misc]
                row[index], category, descending=order.descending
            ),
            reverse=order.descending,
        )
    return rows


def safe_stem(title: str) -> str:
    """A filename made of what somebody typed, and nothing else.

    The same rule the grid's downloads follow: a name is letters, digits and
    three punctuation marks, so a title can never carry a path into a header.
    """
    stem = "".join(
        character if character.isalnum() or character in "._-" else "-"
        for character in title.strip()
    ).strip("._-")
    return stem[:120] or "result"


def to_csv(columns: list[ResultColumn], rows: list[list[str | None]]) -> bytes:
    """The rows as they are shown, with a heading line.

    UTF-8 with a byte order mark, as everywhere else a table is saved: it is
    what a spreadsheet on Windows opens without asking.
    """
    output = io.StringIO(newline="")
    writer = csv.writer(output, quoting=NULL_QUOTING)
    writer.writerow([column.name for column in columns])
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")
