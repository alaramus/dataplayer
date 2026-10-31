"""Reading the documents of a MongoDB collection a page at a time (D285).

A filter is a query document built here from the closed set of predicates,
naming only fields the collection was found to have (D284), with every value
typed as the field holds it. Nothing a client sends becomes an operator.
"""

import re
from dataclasses import dataclass
from typing import Any, assert_never

from app.adapters.fetch import (
    FetchColumn,
    FetchRequest,
    FetchResult,
    Filter,
    InFilter,
    NullFilter,
    ScalarFilter,
    Sort,
)
from app.adapters.mongodb.inspection import CollectionFacts
from app.adapters.mongodb.relation import MongodbRelation
from app.adapters.mongodb.rows import (
    editable,
    editing_reason,
    handle_of,
    insertable,
    inserting_reason,
)
from app.adapters.mongodb.session import MongodbSession
from app.adapters.mongodb.values import (
    Tag,
    capabilities,
    column_type,
    parsed_value,
    read_cell,
    tag_of,
)
from app.core.translation import say

_COMPARISONS = {"eq": "$eq", "ne": "$ne", "gt": "$gt", "gte": "$gte", "lt": "$lt", "lte": "$lte"}

# How long one page may take on the server before it is stopped.
PAGE_MILLISECONDS = 60_000


@dataclass(frozen=True)
class PreparedRead:
    """One validated read, shared by a page and an export."""

    facts: CollectionFacts
    columns: list[FetchColumn]
    tags: dict[str, Tag]
    query: dict[str, Any]
    sort: list[tuple[str, int]]


def columns_of(facts: CollectionFacts) -> tuple[list[FetchColumn], dict[str, Tag]]:
    columns: list[FetchColumn] = []
    tags: dict[str, Tag] = {}
    for sampled in facts.fields:
        type_ = column_type(sampled.tag)
        tag: Tag = sampled.tag or "mixed"
        sortable, operators = capabilities(tag, sampled.name)
        tags[sampled.name] = tag
        columns.append(
            FetchColumn(
                name=sampled.name,
                type=type_,
                sortable=sortable,
                filter_operators=operators,
                nullable=not sampled.everywhere or sampled.tag is None,
            )
        )
    return columns, tags


def _condition(filter_: Filter, column: FetchColumn, tag: Tag) -> dict[str, Any]:
    if filter_.op not in column.filter_operators:
        raise ValueError(
            say('Cannot filter column "{name}" with "{op}"', name=column.name, op=filter_.op)
        )

    def value(text: str) -> Any:
        try:
            return parsed_value(text, tag)
        except ValueError:
            raise ValueError(say('Invalid value for column "{name}"', name=column.name)) from None

    match filter_:
        case NullFilter(op=op):
            # Null and absent alike: to a reader both are an empty cell.
            return {"$eq": None} if op == "is_null" else {"$ne": None}
        case InFilter(values=values):
            return {"$in": [value(item) for item in values]}
        case ScalarFilter(op="contains", value=text):
            return {"$regex": re.escape(text)}
        case ScalarFilter(op="starts_with", value=text):
            return {"$regex": "^" + re.escape(text)}
        case ScalarFilter(op=op, value=text):
            return {_COMPARISONS[op]: value(text)}
        case unreachable:
            assert_never(unreachable)


def query_of(
    columns: list[FetchColumn],
    tags: dict[str, Tag],
    filters: list[Filter],
    sort: list[Sort],
    *,
    stable: tuple[str, ...],
) -> tuple[dict[str, Any], list[tuple[str, int]]]:
    """A query document and an order, from a reader's filters and sort.

    Every name is checked against the columns first. `stable` follows the
    reader's own order, so a page is the same page every time it is read.
    """
    known = {column.name: column for column in columns}
    for used in [item.column for item in filters] + [item.column for item in sort]:
        if used not in known:
            raise ValueError(say('Relation has no column "{column}"', column=used))
    for item in sort:
        if not known[item.column].sortable:
            raise ValueError(say('Cannot sort column "{column}"', column=item.column))
    clauses = [
        {item.column: _condition(item, known[item.column], tags[item.column])}
        for item in filters
    ]
    query: dict[str, Any] = {}
    if len(clauses) == 1:
        query = clauses[0]
    elif clauses:
        query = {"$and": clauses}
    order = [(item.column, -1 if item.descending else 1) for item in sort]
    order += [(name, 1) for name in stable if name in known and all(name != used for used, _ in order)]
    return query, order


def prepare(facts: CollectionFacts, request: FetchRequest) -> PreparedRead:
    columns, tags = columns_of(facts)
    query, sort = query_of(columns, tags, request.filters, request.sort, stable=("_id",))
    return PreparedRead(facts=facts, columns=columns, tags=tags, query=query, sort=sort)


def with_page_fields(
    columns: list[FetchColumn], documents: list[dict[str, Any]]
) -> list[FetchColumn]:
    """The sampled columns, then any field met only on this page.

    Shown so nothing on the page is hidden, and offered for nothing: it was
    not in the sample, so a filter on it would be refused next time (D284).
    """
    known = {column.name for column in columns}
    extra: dict[str, Tag | None] = {}
    for document in documents:
        for name, value in document.items():
            if name not in known:
                tag = tag_of(value)
                extra[name] = extra.get(name) or tag
    return columns + [
        FetchColumn(name=name, type=column_type(tag), nullable=True)
        for name, tag in extra.items()
    ]


class MongodbFetch:
    def __init__(self, session: MongodbSession, relation: MongodbRelation) -> None:
        self._session = session
        self._relation = relation

    async def prepare(self, request: FetchRequest) -> PreparedRead:
        facts = await self._relation.facts(request.node_id, structure=False)
        return prepare(facts, request)

    async def fetch(self, request: FetchRequest) -> FetchResult:
        prepared = await self.prepare(request)
        facts = prepared.facts
        async with self._session.client() as client:
            with self._session.failures():
                cursor = client[facts.database][facts.name].find(prepared.query)
                if prepared.sort:
                    cursor = cursor.sort(prepared.sort)
                documents = await (
                    cursor.skip(request.offset)
                    .limit(request.limit + 1)
                    .max_time_ms(PAGE_MILLISECONDS)
                    .to_list()
                )
        page = documents[: request.limit]
        update_reason = editing_reason(facts)
        insert_reason = inserting_reason(facts)
        columns = [
            column.model_copy(
                update={
                    "editable": update_reason is None and editable(column),
                    "insertable": insert_reason is None and insertable(column),
                    # `_id` is made by the driver when it is not given.
                    "has_default": True,
                }
            )
            for column in prepared.columns
        ]
        columns = with_page_fields(columns, page)
        rows = [[read_cell(document.get(column.name)) for column in columns] for document in page]
        return FetchResult(
            columns=columns,
            rows=rows,
            has_more=len(documents) > request.limit,
            row_handles=[handle_of(document) for document in page],
            update_supported=update_reason is None,
            update_reason=update_reason,
            insert_supported=insert_reason is None,
            insert_reason=insert_reason,
            delete_supported=update_reason is None,
            delete_reason=update_reason,
        )
