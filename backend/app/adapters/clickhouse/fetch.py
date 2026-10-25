"""Reading rows out of a ClickHouse relation a page at a time.

Names reach a statement only after they are found among the relation's own
columns, and only through `Identifier`; values are the server's parameters,
typed by the column they are compared with (D267).
"""

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import assert_never

from app.adapters.clickhouse.catalog import is_system_database
from app.adapters.clickhouse.inspection import RelationFacts, has_finite_rows
from app.adapters.clickhouse.relation import ClickhouseRelation
from app.adapters.clickhouse.reports import SystemReport, in_section, report_for
from app.adapters.clickhouse.rows import (
    RowShape,
    comparable_type,
    editable_engine,
    handles_of,
    insertable_engine,
    writable_type,
)
from app.adapters.clickhouse.session import BAD_QUERY_PARAMETER, ClickhouseSession
from app.adapters.clickhouse.sql import SQL, Composable, Composed, Identifier, Params
from app.adapters.clickhouse.types import (
    build_column_type,
    read_cell,
    type_name,
    unwrapped,
)
from app.adapters.fetch import (
    PAGE_COMMANDS,
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
    "ne": "!=",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
}

_ORDERED = frozenset({"number", "string", "datetime", "uuid", "enum", "boolean", "network"})
_COMPARED = frozenset({"number", "string", "datetime"})
_EQUAL = _ORDERED

# The number types a parameter may be declared as: the column's own, when it
# is one of these, so that the server parses the value as the column holds it
# and refuses what it cannot hold.
_NUMBER_TYPE = re.compile(
    r"U?Int(8|16|32|64|128|256)|Float(32|64)|BFloat16"
    r"|Decimal(32|64|128|256)?\(\d+(, ?\d+)?\)"
)
_TRUTHS = frozenset({"true", "false", "1", "0"})


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


def parameter_of(value: str, type_: ColumnType) -> tuple[str, str]:
    """The text a filter sends for this column, and the type it is sent as.

    A moment is compared as an instant: a value with no offset is UTC, as
    every moment is shown (D268), and it is sent as one in UTC whatever zone
    the column keeps.
    """
    inner = unwrapped(type_.sql)
    match type_.category:
        case "number":
            try:
                if not Decimal(value).is_finite():
                    raise ValueError
            except InvalidOperation:
                raise ValueError from None
            if _NUMBER_TYPE.fullmatch(inner) is None:
                raise ValueError
            return value, inner
        case "datetime":
            name = type_name(inner)
            if name in ("Date", "Date32"):
                return date.fromisoformat(value).isoformat(), "Date32"
            if name in ("DateTime", "DateTime64"):
                moment = datetime.fromisoformat(value)
                if moment.tzinfo is not None:
                    moment = moment.astimezone(UTC)
                return moment.replace(tzinfo=None).isoformat(sep=" "), "DateTime64(6, 'UTC')"
            raise ValueError
        case "string" | "enum":
            return value, "String"
        case "uuid":
            return str(uuid.UUID(value)), "UUID"
        case "boolean":
            if value.lower() not in _TRUTHS:
                raise ValueError
            return value.lower(), "Bool"
        case "network":
            if type_name(inner) not in ("IPv4", "IPv6"):
                raise ValueError
            return value, type_name(inner)
        case _:
            raise ValueError


def _order(facts: RelationFacts, columns: list[FetchColumn]) -> list[str]:
    """What a page is ordered by once the reader's own sort is done (D269).

    The sorting key's columns first, so the server reads in its own order, and
    then every other column it can compare: no key in ClickHouse is unique,
    and only the whole row tells two rows apart.
    """
    if not has_finite_rows(facts.engine):
        return []
    sortable = [column.name for column in columns if column.sortable]
    leading = [name for name in facts.key_columns(facts.sorting_key) if name in sortable]
    return leading + [name for name in sortable if name not in leading]


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

    @property
    def order(self) -> list[str]:
        if self.facts is not None:
            return _order(self.facts, self.columns)
        return list(self.report.stable_order) if self.report is not None else []

    def statement(self, params: Params, columns: list[FetchColumn] | None = None) -> Composed:
        """SELECT, WHERE and ORDER BY, without a page."""
        known = {column.name: column for column in self.columns}
        conditions = [_condition(filter_, known, params) for filter_ in self.request.filters]
        statement: Composed = SQL("SELECT {} FROM {}").format(
            SQL(", ").join(Identifier(column.name) for column in (columns or self.columns)),
            self.source,
        )
        if conditions:
            statement += SQL(" WHERE ") + SQL(" AND ").join(conditions)
        sorted_by = [item.column for item in self.request.sort]
        ordering: list[Composable] = [
            SQL("{} DESC" if item.descending else "{} ASC").format(Identifier(item.column))
            for item in self.request.sort
        ]
        ordering += [
            SQL("{} ASC").format(Identifier(name)) for name in self.order if name not in sorted_by
        ]
        if ordering:
            statement += SQL(" ORDER BY ") + SQL(", ").join(ordering)
        return statement


def shape_of(facts: RelationFacts) -> RowShape:
    """The columns of a page and what may be done to its rows (D272)."""
    if is_system_database(facts.schema):
        refused: str | None = say('"{schema}" belongs to the server', schema=facts.schema)
        update_reason: str | None = refused
        insert_reason: str | None = refused
    else:
        update_reason = (
            None
            if editable_engine(facts.engine)
            else say(
                "Only a MergeTree table's rows can be changed; this one is {engine}",
                engine=facts.engine,
            )
        )
        insert_reason = (
            None
            if insertable_engine(facts.engine)
            else say("A {engine} table does not keep rows inserted into it", engine=facts.engine)
        )
    columns: list[FetchColumn] = []
    for column in facts.columns:
        sortable, operators = column_capabilities(column.type)
        stored = column.generated is None
        columns.append(
            FetchColumn(
                name=column.name,
                type=column.type,
                sortable=sortable,
                filter_operators=operators,
                # A key decides where the row is kept, and no UPDATE moves it.
                editable=update_reason is None
                and stored
                and not column.in_key
                and writable_type(column.type),
                nullable=column.nullable,
                insertable=insert_reason is None and stored,
                # Every ClickHouse column has a default, its type's own zero
                # when nothing else is said.
                has_default=True,
            )
        )
    return RowShape(
        columns=columns,
        matched=[
            column.name
            for column in facts.columns
            if column.generated is None and comparable_type(column.type)
        ],
        update_reason=update_reason,
        insert_reason=insert_reason,
    )


class ClickhouseFetch:
    def __init__(self, session: ClickhouseSession, relation: ClickhouseRelation) -> None:
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
        for used in [item.column for item in request.filters] + [item.column for item in request.sort]:
            if used not in known:
                raise ValueError(say('Relation has no column "{column}"', column=used))
        for sort in request.sort:
            if not known[sort.column].sortable:
                raise ValueError(say('Cannot sort column "{column}"', column=sort.column))
        # Every filter is checked once here, so a bad one is refused before
        # anything is asked of the server.
        prepared.statement(Params())
        return prepared

    async def _report(self, report: SystemReport, request: FetchRequest) -> PreparedRead:
        """A report's columns as the server describes them; nothing is written through it."""
        source = SQL("(" + report.statement + ") AS report")
        described = await self._session.answer(
            (SQL("DESCRIBE TABLE ") + SQL("(" + report.statement + ")")).text()
        )
        columns: list[FetchColumn] = []
        for row in described.rows:
            type_ = build_column_type(str(row[1]))
            sortable, operators = column_capabilities(type_)
            columns.append(
                FetchColumn(name=str(row[0]), type=type_, sortable=sortable, filter_operators=operators)
            )
        refused = say('"{title}" is a report and holds no rows of its own', title=say(report.title))
        return PreparedRead(
            source=source,
            shape=RowShape(columns=columns, matched=[], update_reason=refused, insert_reason=refused),
            facts=None,
            report=report,
            request=request,
        )

    async def fetch(self, request: FetchRequest) -> FetchResult:
        prepared = await self.prepare(request)
        params = Params()
        statement = prepared.statement(params)
        statement += SQL(" LIMIT {} OFFSET {}").format(
            params.add(str(request.limit + 1), "UInt64"),
            params.add(str(request.offset), "UInt64"),
        )
        answer = await self._session.answer(
            statement.text(),
            params.values,
            refusals={BAD_QUERY_PARAMETER: N_("A filter value does not fit its column")},
        )
        rows = [[read_cell(value) for value in row] for row in answer.rows[: request.limit]]
        shape = prepared.shape
        report = prepared.report
        return FetchResult(
            columns=shape.columns,
            rows=rows,
            has_more=len(answer.rows) > request.limit,
            row_handles=handles_of(shape, rows),
            update_supported=shape.update_supported,
            update_reason=shape.update_reason,
            insert_supported=shape.insert_supported,
            insert_reason=shape.insert_reason,
            delete_supported=shape.update_supported,
            delete_reason=shape.update_reason,
            # A row of a report is a line of an answer, not a thing (D111).
            record_supported=report is None,
            record_reason=None if report is None else shape.update_reason,
            refresh_seconds=None if report is None else report.refresh_seconds,
            # A report is the server describing itself, and a table made of it
            # would be a copy of a moment nobody can refresh (D72).
            page_commands=list(PAGE_COMMANDS)
            if report is None
            else [command for command in PAGE_COMMANDS if command != "create_relation"],
        )


def _condition(filter_: Filter, known: dict[str, FetchColumn], params: Params) -> Composable:
    column = known[filter_.column]
    if filter_.op not in column.filter_operators:
        raise ValueError(
            say('Cannot filter column "{name}" with "{op}"', name=column.name, op=filter_.op)
        )
    name = Identifier(column.name)

    def parameter(value: str) -> Composable:
        try:
            text, type_ = parameter_of(value, column.type)
        except ValueError:
            raise ValueError(say('Invalid value for column "{name}"', name=column.name)) from None
        return params.add(text, type_)

    match filter_:
        case NullFilter(op=op):
            return SQL("{} IS NULL" if op == "is_null" else "{} IS NOT NULL").format(name)
        case InFilter(values=values):
            return SQL("{} IN ({})").format(
                name, SQL(", ").join(parameter(value) for value in values)
            )
        case ScalarFilter(op="contains", value=value):
            # A function rather than LIKE, so that `%` and `_` are characters.
            return SQL("position({}, {}) > 0").format(name, params.add(value, "String"))
        case ScalarFilter(op="starts_with", value=value):
            return SQL("startsWith({}, {})").format(name, params.add(value, "String"))
        case ScalarFilter(op=op, value=value):
            return SQL("{} " + _COMPARISONS[op] + " {}").format(name, parameter(value))
        case unreachable:
            assert_never(unreachable)
