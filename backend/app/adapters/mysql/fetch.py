"""Reading rows out of a MySQL relation a page at a time.

Names reach a statement only after they are found among the relation's own
columns, and only through `identifier`; values go through placeholders.
"""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, assert_never

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
from app.adapters.mysql.catalog import is_system_database
from app.adapters.mysql.inspection import RelationFacts
from app.adapters.mysql.relation import MysqlRelation
from app.adapters.mysql.reports import SystemReport, in_section, report_for
from app.adapters.mysql.rows import RowShape, handle_of
from app.adapters.mysql.session import MysqlSession
from app.adapters.mysql.sql import SQL, Composable, Composed, Identifier
from app.adapters.mysql.types import read_cell, wire_type
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


# Tables a person's rows live in. A MariaDB sequence is a table of one row
# the server keeps, and a view is not a table.
_WRITABLE_TYPES = ("BASE TABLE", "SYSTEM VERSIONED")


def shape_of(facts: RelationFacts) -> RowShape:
    """The columns of a page and what may be done to its rows (D234)."""
    key = facts.ordering_key
    if is_system_database(facts.schema):
        refused: str | None = say('"{schema}" belongs to the server', schema=facts.schema)
        insert_refused: str | None = refused
    elif facts.table_type not in _WRITABLE_TYPES:
        refused = say("Only tables can be edited")
        insert_refused = say("Only tables accept inserted rows")
    else:
        insert_refused = None
        refused = (
            None
            if key
            else say(
                "This table has no primary key and no unique key over columns that "
                "cannot be empty, so no row of it can be named"
            )
        )
    columns: list[FetchColumn] = []
    for column in facts.columns:
        sortable, operators = column_capabilities(column.type)
        stored = column.generated is None
        insertable = insert_refused is None and stored
        has_default = column.default is not None or column.auto_increment
        columns.append(
            FetchColumn(
                name=column.name,
                type=column.type,
                sortable=sortable,
                filter_operators=operators,
                editable=refused is None and stored,
                nullable=column.nullable,
                insertable=insertable,
                insert_required=insertable and not column.nullable and not has_default,
                has_default=has_default,
            )
        )
    return RowShape(columns=columns, key=key, update_reason=refused, insert_reason=insert_refused)


def select_of(shape: RowShape) -> Composable:
    return SQL(", ").join(select_expression(column) for column in shape.columns)


def cells_of(row: dict[str, Any], shape: RowShape) -> list[str | None]:
    return [read_cell(row[column.name], column.type) for column in shape.columns]


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
    def order(self) -> list[str]:
        if self.facts is not None:
            return self.facts.ordering_key
        return list(self.report.stable_order) if self.report is not None else []

    def statement(self, columns: list[FetchColumn], params: list[Any]) -> Composed:
        """SELECT, WHERE and ORDER BY, without a page."""
        known = {column.name: column for column in self.shape.columns}
        conditions = [_condition(filter_, known, params) for filter_ in self.request.filters]
        statement: Composed = SQL("SELECT {} FROM {}").format(
            SQL(", ").join(select_expression(column) for column in columns), self.source
        )
        if conditions:
            statement += SQL(" WHERE ") + SQL(" AND ").join(conditions)
        ordering: list[Composable] = [
            SQL("{} DESC" if item.descending else "{} ASC").format(Identifier(item.column))
            for item in self.request.sort
        ]
        # Always after what the reader asked for, so page two does not repeat
        # page one (D231). A relation with no such key has nothing honest to add.
        ordering += [SQL("{} ASC").format(Identifier(name)) for name in self.order]
        if ordering:
            statement += SQL(" ORDER BY ") + SQL(", ").join(ordering)
        return statement


class MysqlFetch:
    def __init__(self, session: MysqlSession, relation: MysqlRelation) -> None:
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
        known = {column.name: column for column in prepared.shape.columns}
        for used in [item.column for item in request.filters] + [item.column for item in request.sort]:
            if used not in known:
                raise ValueError(say('Relation has no column "{column}"', column=used))
        for sort in request.sort:
            if not known[sort.column].sortable:
                raise ValueError(say('Cannot sort column "{column}"', column=sort.column))
        # Every filter is checked once here, so a bad one is refused before
        # anything is asked of the server.
        prepared.statement(prepared.shape.columns, [])
        return prepared

    async def _report(self, report: SystemReport, request: FetchRequest) -> PreparedRead:
        """A report's columns as the server describes them; nothing is written through it."""
        statement = report.statement_for(await self._session.profile())
        described = await self._session.describe(
            SQL("SELECT * FROM ({}) AS report LIMIT 0").format(SQL(statement)).text()
        )
        columns: list[FetchColumn] = []
        for name, code in described:
            sql, category = wire_type(code)
            type_ = ColumnType(sql=sql, category=category)
            sortable, operators = column_capabilities(type_)
            columns.append(
                FetchColumn(name=name, type=type_, sortable=sortable, filter_operators=operators)
            )
        refused = say('"{title}" is a report and holds no rows of its own', title=say(report.title))
        return PreparedRead(
            source=SQL("({}) AS report").format(SQL(statement)),
            shape=RowShape(columns=columns, key=[], update_reason=refused, insert_reason=refused),
            facts=None,
            report=report,
            request=request,
        )

    async def fetch(self, request: FetchRequest) -> FetchResult:
        prepared = await self.prepare(request)
        shape = prepared.shape
        params: list[Any] = []
        statement = prepared.statement(shape.columns, params) + SQL(" LIMIT %s OFFSET %s")
        params.extend([request.limit + 1, request.offset])
        rows = await self._session.query(statement.text(), tuple(params))
        cells = [cells_of(row, shape) for row in rows[: request.limit]]
        facts = prepared.facts
        report = prepared.report
        reason = shape.update_reason
        return FetchResult(
            columns=shape.columns,
            rows=cells,
            has_more=len(rows) > request.limit,
            row_handles=[handle_of(shape, row) for row in cells],
            references=[]
            if facts is None
            else [
                FetchReference(
                    name=key.name,
                    columns=key.columns,
                    target_title=f"{key.target_schema or facts.schema}.{key.target_table}",
                )
                for key in facts.foreign_keys
            ],
            update_supported=shape.update_supported,
            update_reason=reason,
            insert_supported=shape.insert_supported,
            insert_reason=shape.insert_reason,
            delete_supported=shape.update_supported,
            delete_reason=reason,
            # A row of a report is a line of an answer, not a thing (D111).
            record_supported=report is None,
            record_reason=None if report is None else reason,
            refresh_seconds=None if report is None else report.refresh_seconds,
            # A report is the server describing itself, and a table made of it
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
