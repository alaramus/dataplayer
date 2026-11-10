"""Reading rows out of a Cassandra table a page at a time (D342).

A name reaches a statement only after it is found among the relation's own
columns, and only quoted; a value is bound to a prepared statement, typed by
its column. CQL has no offset: the grid's offset is served from the paging
state of a page served before, kept per read in the connector's cluster.
"""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, assert_never

from app.adapters.cassandra.cql import SQL, Composable, Identifier
from app.adapters.cassandra.inspection import ColumnFacts, RelationFacts
from app.adapters.cassandra.relation import CassandraRelation
from app.adapters.cassandra.reports import ClusterReport, in_section, report_for
from app.adapters.cassandra.rows import change_reason, handles_of, writable
from app.adapters.cassandra.session import CassandraSession, PageStates
from app.adapters.cassandra.types import TEXTS, parse_value, read_cell, type_name
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
from app.adapters.protocol import AdapterError
from app.core.translation import say

_COMPARISONS: dict[str, str] = {
    "eq": "=",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
}

# Rows read and thrown away to reach an offset no kept state is near (D342).
MAX_SKIPPED_ROWS = 100_000
# The most rows asked of the server at once while skipping.
_SKIP_PAGE = 5000

_EQUAL = frozenset({"number", "string", "datetime", "uuid", "boolean", "network"})
_ORDERED = frozenset({"number", "string", "datetime", "uuid", "network"})


def filter_operators(column: ColumnFacts, *, scylla: bool) -> list[FilterOp]:
    """What both servers accept with ALLOW FILTERING on this column's type (D342)."""
    category = column.type.category
    if column.type_text == "counter" or category not in _EQUAL:
        return []
    operators: list[FilterOp] = ["eq", "in"]
    if category in _ORDERED:
        operators.extend(["gt", "gte", "lt", "lte"])
    if scylla and type_name(column.type_text) in TEXTS:
        # Cassandra refuses LIKE on a column without an index.
        operators.extend(["contains", "starts_with"])
    return operators


def bound_value(value: str, column: ColumnFacts) -> Any:
    """The Python value the driver binds for a filter on this column.

    Raises ValueError for text the column cannot hold.
    """
    return parse_value(value, column.type_text)


@dataclass(frozen=True)
class PreparedRead:
    """One validated read, shared by a page and an export."""

    facts: RelationFacts
    columns: list[FetchColumn]
    statement: str
    params: list[Any]
    filtered: bool

    def key(self, limit: int) -> str:
        """What makes two reads' paging states different."""
        text = json.dumps(
            [self.statement, [repr(value) for value in self.params], limit]
        )
        return hashlib.sha256(text.encode()).hexdigest()


def fetch_columns(facts: RelationFacts, *, scylla: bool) -> list[FetchColumn]:
    changeable = change_reason(facts) is None
    return [
        FetchColumn(
            name=column.name,
            type=column.type,
            # CQL orders only inside one partition named in full.
            sortable=False,
            filter_operators=filter_operators(column, scylla=scylla),
            # A key column decides where the row is kept (D345).
            editable=changeable and writable(column),
            nullable=not column.in_key,
            insertable=changeable and (column.in_key or writable(column)),
            insert_required=column.in_key,
        )
        for column in facts.columns
    ]


def _condition(
    filter_: Filter,
    known: dict[str, ColumnFacts],
    allowed: dict[str, list[FilterOp]],
    params: list[Any],
) -> Composable:
    column = known[filter_.column]
    if filter_.op not in allowed[column.name]:
        raise ValueError(
            say(
                'Cannot filter column "{name}" with "{op}"',
                name=column.name,
                op=filter_.op,
            )
        )
    name = Identifier(column.name)

    def bind(value: str) -> Any:
        try:
            return bound_value(value, column)
        except ValueError:
            raise ValueError(
                say('Invalid value for column "{name}"', name=column.name)
            ) from None

    match filter_:
        case NullFilter():
            # Never offered: neither server compares with null.
            raise ValueError(
                say(
                    'Cannot filter column "{name}" with "{op}"',
                    name=column.name,
                    op=filter_.op,
                )
            )
        case InFilter(values=values):
            params.append([bind(value) for value in values])
            return SQL("{} IN ?").format(name)
        case ScalarFilter(op="contains" | "starts_with", value=value):
            if "%" in value or "_" in value:
                raise ValueError(
                    say("ScyllaDB's LIKE cannot look for % or _ in a value")
                )
            params.append(f"%{value}%" if filter_.op == "contains" else f"{value}%")
            return SQL("{} LIKE ?").format(name)
        case ScalarFilter(op=op, value=value):
            if op not in _COMPARISONS:
                raise ValueError(
                    say(
                        'Cannot filter column "{name}" with "{op}"',
                        name=column.name,
                        op=op,
                    )
                )
            params.append(bind(value))
            return SQL("{} " + _COMPARISONS[op] + " ?").format(name)
        case unreachable:
            assert_never(unreachable)


class _Unpaged(Exception):
    """The server answered more rows than a page asked for."""


class CassandraFetch:
    def __init__(self, session: CassandraSession, relation: CassandraRelation) -> None:
        self._session = session
        self._relation = relation

    async def prepare(self, request: FetchRequest) -> PreparedRead:
        facts = await self._relation.facts(request.node_id)
        scylla = (await self._session.profile()).scylla
        columns = fetch_columns(facts, scylla=scylla)
        known = {column.name: column for column in facts.columns}
        for used in [item.column for item in request.filters] + [
            item.column for item in request.sort
        ]:
            if used not in known:
                raise ValueError(say('Relation has no column "{column}"', column=used))
        for sort in request.sort:
            raise ValueError(say('Cannot sort column "{column}"', column=sort.column))
        allowed = {column.name: column.filter_operators for column in columns}
        params: list[Any] = []
        conditions = [
            _condition(item, known, allowed, params) for item in request.filters
        ]
        statement = SQL("SELECT {} FROM {}").format(
            SQL(", ").join(Identifier(column.name) for column in facts.columns),
            Identifier(facts.keyspace, facts.name),
        )
        if conditions:
            statement += (
                SQL(" WHERE ") + SQL(" AND ").join(conditions) + SQL(" ALLOW FILTERING")
            )
        return PreparedRead(
            facts=facts,
            columns=columns,
            statement=statement.text(),
            params=params,
            filtered=bool(conditions),
        )

    async def _report(
        self, report: ClusterReport, request: FetchRequest
    ) -> FetchResult:
        """A report read whole and cut into the page asked; nothing is written through it."""
        if request.filters or request.sort:
            raise ValueError(say("A report is neither filtered nor sorted"))
        answer = await report.read(self._session, await self._session.profile())
        refused = say(
            '"{title}" is a report and holds no rows of its own',
            title=say(report.title),
        )
        end = request.offset + request.limit
        return FetchResult(
            columns=[
                FetchColumn(name=column.name, type=column.type)
                for column in answer.columns
            ],
            rows=answer.rows[request.offset : end],
            has_more=len(answer.rows) > end,
            update_reason=refused,
            insert_reason=refused,
            delete_reason=refused,
            # A row of a report is a line of an answer, not a thing (D111).
            record_supported=False,
            record_reason=refused,
            refresh_seconds=report.refresh_seconds,
            page_commands=[
                command for command in PAGE_COMMANDS if command != "create_relation"
            ],
        )

    async def fetch(self, request: FetchRequest) -> FetchResult:
        report = report_for(request.node_id)
        if report is not None:
            return await self._report(report, request)
        if in_section(request.node_id):
            raise ValueError(
                say(
                    '"{node_id}" is not a report of this source',
                    node_id=request.node_id,
                )
            )
        prepared = await self.prepare(request)
        states = await self._session.page_states()
        rows, more = await self._page(prepared, states, request.offset, request.limit)
        types = [column.type for column in prepared.columns]
        cells = [
            [read_cell(value, type_) for value, type_ in zip(row, types, strict=True)]
            for row in rows
        ]
        reason = change_reason(prepared.facts)
        return FetchResult(
            columns=prepared.columns,
            rows=cells,
            has_more=more,
            row_handles=handles_of(prepared.facts, cells),
            update_supported=reason is None,
            update_reason=reason,
            insert_supported=reason is None,
            insert_reason=reason,
            delete_supported=reason is None,
            delete_reason=reason,
        )

    async def _read(
        self, prepared: PreparedRead, size: int, state: bytes | None
    ) -> tuple[list[tuple[Any, ...]], bytes | None]:
        answer = await self._session.page(
            prepared.statement,
            prepared.params,
            fetch_size=size,
            paging_state=state,
        )
        if len(answer.rows) > size:
            raise _Unpaged
        return answer.rows, answer.paging_state

    async def _page(
        self, prepared: PreparedRead, states: PageStates, offset: int, limit: int
    ) -> tuple[Sequence[tuple[Any, ...]], bool]:
        try:
            return await self._paged(prepared, states, offset, limit)
        except _Unpaged:
            # A virtual table answers whole, whatever page size is asked: the
            # page is cut out of the whole read, under the same ceiling.
            answer = await self._session.rows(
                prepared.statement,
                prepared.params,
                limit=min(offset, MAX_SKIPPED_ROWS) + limit + 1,
            )
            rows = answer.rows[offset : offset + limit]
            return rows, len(answer.rows) > offset + limit

    async def _paged(
        self, prepared: PreparedRead, states: PageStates, offset: int, limit: int
    ) -> tuple[Sequence[tuple[Any, ...]], bool]:
        """`limit` rows from `offset`, and whether the server has more after them.

        A page of a filtered read may come back short, or empty with more
        after it: the server stops reading at its own budget, not at a row
        count. So both the skip and the read go on until the count is met or
        no paging state is left.
        """
        read = prepared.key(limit)
        position, state = states.nearest(read, offset)
        if offset - position > MAX_SKIPPED_ROWS:
            raise AdapterError(
                "config",
                say(
                    "This page is {rows} rows past the last one read; page forward from there",
                    rows=offset - position,
                ),
            )
        # A kept state means the read has begun, and a state of None after
        # that means it has ended; before it, None means from the start.
        begun = state is not None
        while position < offset:
            if begun and state is None:
                return [], False
            rows, state = await self._read(
                prepared, min(offset - position, _SKIP_PAGE), state
            )
            begun = True
            position += len(rows)
            if state is not None:
                states.keep(read, position, state)
        rows_read: list[tuple[Any, ...]] = []
        while len(rows_read) < limit and not (begun and state is None):
            rows, state = await self._read(prepared, limit - len(rows_read), state)
            begun = True
            rows_read.extend(rows)
        if state is not None:
            states.keep(read, offset + len(rows_read), state)
        return rows_read, state is not None
