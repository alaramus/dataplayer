"""Small, read-only reports whose rows come from a protocol rather than SQL."""

from app.adapters.export import ExportRequest
from app.adapters.fetch import (
    FetchColumn,
    FetchRequest,
    FetchResult,
    Filter,
    FilterOp,
    InFilter,
    NullFilter,
    PageCommand,
    ScalarFilter,
    Sort,
)
from app.adapters.relation import ColumnType
from app.core.translation import say

_FILTER_OPERATORS: list[FilterOp] = [
    "eq",
    "ne",
    "contains",
    "starts_with",
    "in",
    "is_null",
    "is_not_null",
]
_REPORT_COMMANDS: list[PageCommand] = ["share"]
_TEXT = ColumnType(sql="text", category="string")


def selected_rows(
    rows: list[tuple[str, str]],
    *,
    name_column: str,
    value_column: str,
    filters: list[Filter],
    sort: list[Sort],
) -> list[tuple[str, str]]:
    """Apply the bounded string operations offered by a report's two columns."""
    positions = {name_column: 0, value_column: 1}
    selected = rows
    for filter_ in filters:
        position = positions.get(filter_.column)
        if position is None:
            raise ValueError(say("This report cannot be filtered that way"))

        def matches(
            row: tuple[str, str],
            *,
            position: int = position,
            filter_: Filter = filter_,
        ) -> bool:
            value = row[position].casefold()
            if isinstance(filter_, NullFilter):
                return filter_.op == "is_not_null"
            if isinstance(filter_, InFilter):
                return value in {item.casefold() for item in filter_.values}
            if not isinstance(filter_, ScalarFilter):
                raise ValueError(say("This report cannot be filtered that way"))
            expected = filter_.value.casefold()
            if filter_.op == "eq":
                return value == expected
            if filter_.op == "ne":
                return value != expected
            if filter_.op == "contains":
                return expected in value
            if filter_.op == "starts_with":
                return value.startswith(expected)
            raise ValueError(say("This report cannot be filtered that way"))

        selected = [row for row in selected if matches(row)]

    # Stable sorts from the last key to the first, as a database applies the
    # same ordered list of sort clauses.
    for order in reversed(sort):
        position = positions.get(order.column)
        if position is None:
            raise ValueError(say("This report cannot be sorted that way"))
        selected = sorted(
            selected,
            key=lambda row: row[position].casefold(),
            reverse=order.descending,
        )
    return selected


def page(
    request: FetchRequest,
    rows: list[tuple[str, str]],
    *,
    name_column: str,
    value_column: str,
    read_only_reason: str,
    refresh_seconds: int | None = None,
    page_commands: list[PageCommand] | None = None,
) -> FetchResult:
    columns = [
        FetchColumn(
            name=name_column,
            type=_TEXT,
            sortable=True,
            filter_operators=_FILTER_OPERATORS,
        ),
        FetchColumn(
            name=value_column,
            type=_TEXT,
            sortable=True,
            filter_operators=_FILTER_OPERATORS,
        ),
    ]
    selected = selected_rows(
        rows,
        name_column=name_column,
        value_column=value_column,
        filters=request.filters,
        sort=request.sort,
    )
    end = request.offset + request.limit
    return FetchResult(
        columns=columns,
        rows=[[name, value] for name, value in selected[request.offset:end]],
        has_more=len(selected) > end,
        update_reason=read_only_reason,
        insert_reason=read_only_reason,
        delete_reason=read_only_reason,
        record_supported=False,
        record_reason=read_only_reason,
        refresh_seconds=refresh_seconds,
        page_commands=list(page_commands or _REPORT_COMMANDS),
    )


def export(
    request: ExportRequest,
    rows: list[tuple[str, str]],
    *,
    name_column: str,
    value_column: str,
) -> list[list[str | None]]:
    selected = selected_rows(
        rows,
        name_column=name_column,
        value_column=value_column,
        filters=request.filters,
        sort=request.sort,
    )
    positions = {name_column: 0, value_column: 1}
    unknown = [name for name in request.columns if name not in positions]
    if unknown:
        raise ValueError(say("Unknown column: {column}", column=unknown[0]))
    order = [positions[name] for name in request.columns]
    exported: list[list[str | None]] = []
    for row in selected:
        cells: list[str | None] = []
        for index in order:
            cells.append(row[index])
        exported.append(cells)
    return exported
