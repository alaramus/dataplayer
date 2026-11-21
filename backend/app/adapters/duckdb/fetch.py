"""Reading rows out of a DuckDB relation, or a report, a page at a time (D390, D391, D398).

Names reach a statement only after they are found among the relation's own
columns, and only through `Identifier`; values go through placeholders.
"""

from dataclasses import dataclass
from typing import Any, assert_never

import duckdb

from app.adapters.duckdb.inspection import RelationFacts
from app.adapters.duckdb.relation import DuckdbRelation
from app.adapters.duckdb.reports import SystemReport, in_section, report_for
from app.adapters.duckdb.rows import RowShape, writable
from app.adapters.duckdb.session import DuckdbSession, Reading
from app.adapters.duckdb.sql import SQL, Composable, Composed, Identifier
from app.adapters.duckdb.types import build_column_type, is_nested, shown
from app.adapters.fetch import (
    PAGE_COMMANDS,
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


def refusals_of(facts: RelationFacts) -> tuple[str | None, str | None]:
    """Why rows cannot be changed, and why none can be added, or nothing (D395)."""
    if facts.is_view:
        return say("Only tables can be edited"), say("Only tables accept inserted rows")
    if not facts.primary_key:
        return (
            say("A table without a primary key is read only: DuckDB moves a row when it is updated"),
            None,
        )
    return None, None


def shape_of(facts: RelationFacts) -> RowShape:
    """The columns of a page and what may be done to its rows (D395)."""
    update_reason, insert_reason = refusals_of(facts)
    columns: list[FetchColumn] = []
    for column in facts.columns:
        stored = column.generated is None and writable(column.type)
        insertable = insert_reason is None and stored
        has_default = column.default is not None
        columns.append(
            FetchColumn(
                name=column.name,
                type=column.type,
                # The order DuckDB defines for a list or a struct is nobody's
                # expectation of a sorted grid.
                sortable=not is_nested(column.type),
                filter_operators=column_capabilities(column.type),
                editable=update_reason is None and stored,
                nullable=column.nullable,
                insertable=insertable,
                insert_required=insertable and not column.nullable and not has_default,
                has_default=has_default,
            )
        )
    return RowShape(
        columns=columns,
        key=facts.primary_key,
        update_reason=update_reason,
        insert_reason=insert_reason,
    )


def ordering_of(facts: RelationFacts) -> list[Composable]:
    """What a page is ordered by after the reader's own sort (D391)."""
    if facts.primary_key:
        return [SQL("{} ASC").format(Identifier(name)) for name in facts.primary_key]
    # The fixed word, not a name: quoted, it would be a column called rowid.
    return [SQL("rowid ASC")] if facts.has_rowid else []


@dataclass(frozen=True)
class PreparedRead:
    """One validated read, shared by a page and an export.

    `source` is what the statement selects from: a relation, or a report's
    own statement as a subquery (D55).
    """

    source: Composable
    shape: RowShape
    facts: RelationFacts | None
    report: SystemReport | None
    request: FetchRequest

    @property
    def columns(self) -> list[FetchColumn]:
        return self.shape.columns

    def statement(self, params: list[Any], columns: list[FetchColumn] | None = None) -> Composed:
        """SELECT, WHERE and ORDER BY, without a page."""
        known = {column.name: column for column in self.columns}
        conditions = [_condition(filter_, known, params) for filter_ in self.request.filters]
        chosen = self.columns if columns is None else columns
        statement: Composed = SQL("SELECT {} FROM {}").format(
            SQL(", ").join(shown(Identifier(column.name), column.type) for column in chosen),
            self.source,
        )
        if conditions:
            statement += SQL(" WHERE ") + SQL(" AND ").join(conditions)
        sorted_by = {item.column for item in self.request.sort}
        ordering: list[Composable] = [
            SQL("{} DESC" if item.descending else "{} ASC").format(Identifier(item.column))
            for item in self.request.sort
        ]
        if self.facts is not None:
            ordering += ordering_of(self.facts)
        elif self.report is not None:
            ordering += [
                SQL("{} ASC").format(Identifier(name))
                for name in self.report.stable_order
                if name not in sorted_by
            ]
        if ordering:
            statement += SQL(" ORDER BY ") + SQL(", ").join(ordering)
        return statement


def _report_columns(reading: Reading, statement: str) -> list[FetchColumn]:
    described = reading.tuples("DESCRIBE (" + statement + ")")
    columns: list[FetchColumn] = []
    for row in described:
        type_ = build_column_type(str(row[1]))
        columns.append(
            FetchColumn(
                name=str(row[0]),
                type=type_,
                sortable=not is_nested(type_),
                filter_operators=column_capabilities(type_),
            )
        )
    return columns


class DuckdbFetch:
    def __init__(self, session: DuckdbSession, relation: DuckdbRelation) -> None:
        self._session = session
        self._relation = relation

    async def prepare(self, request: FetchRequest) -> PreparedRead:
        report = report_for(request.node_id)
        if report is not None:
            prepared = await self._report(report, request)
        elif in_section(request.node_id):
            raise ValueError(
                say('"{node_id}" is not a report of this source', node_id=request.node_id)
            )
        else:
            facts = await self._relation.facts(request.node_id, structure=False)
            prepared = PreparedRead(
                source=Identifier(facts.schema, facts.name),
                shape=shape_of(facts),
                facts=facts,
                report=None,
                request=request,
            )
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

    async def _report(self, report: SystemReport, request: FetchRequest) -> PreparedRead:
        """A report's columns as DuckDB describes them; nothing is written through it."""
        columns = await self._session.inspection(
            lambda reading: _report_columns(reading, report.statement)
        )
        refused = say('"{title}" is a report and holds no rows of its own', title=say(report.title))
        return PreparedRead(
            # A statement of this package, never a request's.
            source=SQL("(" + report.statement + ") AS report"),
            shape=RowShape(columns=columns, key=[], update_reason=refused, insert_reason=refused),
            facts=None,
            report=report,
            request=request,
        )

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
        shape = prepared.shape
        page = [[None if cell is None else str(cell) for cell in row] for row in rows[: request.limit]]
        facts = prepared.facts
        report = prepared.report
        return FetchResult(
            columns=shape.columns,
            rows=page,
            has_more=len(rows) > request.limit,
            row_handles=[shape.handle_of(cells) for cells in page],
            references=[]
            if facts is None
            else [
                FetchReference(
                    name=key.name,
                    columns=key.columns,
                    target_title=f"{facts.schema}.{key.target_table}",
                )
                for key in facts.foreign_keys
            ],
            update_supported=shape.update_supported,
            update_reason=shape.update_reason,
            insert_supported=shape.insert_supported,
            insert_reason=shape.insert_reason,
            delete_supported=shape.update_supported,
            delete_reason=shape.update_reason,
            # A row of a report is a line of an answer, not a thing (D111).
            record_supported=report is None,
            record_reason=None if report is None else shape.update_reason,
            # A report is the file describing itself, and a table made of it
            # would be a copy of a moment nobody can refresh (D72).
            page_commands=list(PAGE_COMMANDS)
            if report is None
            else [command for command in PAGE_COMMANDS if command != "create_relation"],
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
