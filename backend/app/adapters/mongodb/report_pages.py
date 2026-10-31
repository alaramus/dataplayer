"""A report read as a page, or whole: its pipeline, then the reader's stages (D289)."""

from collections.abc import AsyncIterator
from typing import Any

from app.adapters.fetch import (
    PAGE_COMMANDS,
    FetchColumn,
    FetchRequest,
    FetchResult,
    Filter,
    Sort,
)
from app.adapters.mongodb.fetch import PAGE_MILLISECONDS, query_of
from app.adapters.mongodb.reports import ServerReport
from app.adapters.mongodb.session import Client, MongodbSession
from app.adapters.mongodb.values import Tag, capabilities, column_type, read_cell
from app.core.translation import say


def report_columns(report: ServerReport) -> tuple[list[FetchColumn], dict[str, Tag]]:
    columns: list[FetchColumn] = []
    tags: dict[str, Tag] = {}
    for name, tag in report.columns:
        sortable, operators = capabilities(tag, name)
        tags[name] = tag
        columns.append(
            FetchColumn(
                name=name,
                type=column_type(tag),
                sortable=sortable,
                filter_operators=operators,
                nullable=True,
            )
        )
    return columns, tags


def report_pipeline(
    report: ServerReport, filters: list[Filter], sort: list[Sort]
) -> tuple[list[FetchColumn], list[dict[str, Any]]]:
    """The report's own stages, then the reader's filter and order, checked first."""
    columns, tags = report_columns(report)
    query, order = query_of(columns, tags, filters, sort, stable=report.stable_order)
    stages = list(report.pipeline)
    if query:
        stages.append({"$match": query})
    if order:
        stages.append({"$sort": dict(order)})
    return columns, stages


async def _cursor(client: Client, report: ServerReport, stages: list[dict[str, Any]]) -> Any:
    database = client[report.database]
    if report.collection is None:
        return await database.aggregate(stages, maxTimeMS=PAGE_MILLISECONDS)
    return await database[report.collection].aggregate(stages, maxTimeMS=PAGE_MILLISECONDS)


async def report_page(
    session: MongodbSession, report: ServerReport, request: FetchRequest
) -> FetchResult:
    columns, stages = report_pipeline(report, request.filters, request.sort)
    stages += [{"$skip": request.offset}, {"$limit": request.limit + 1}]
    async with session.client() as client:
        with session.failures():
            documents = await (await _cursor(client, report, stages)).to_list()
    refused = say('"{title}" is a report and holds no rows of its own', title=say(report.title))
    return FetchResult(
        columns=columns,
        rows=[
            [read_cell(document.get(column.name)) for column in columns]
            for document in documents[: request.limit]
        ],
        has_more=len(documents) > request.limit,
        update_reason=refused,
        insert_reason=refused,
        delete_reason=refused,
        # A row of a report is a line of an answer, not a thing (D111).
        record_supported=False,
        record_reason=refused,
        refresh_seconds=report.refresh_seconds,
        # The server describing itself: a collection made of it would be a copy
        # of a moment nobody can refresh (D72).
        page_commands=[command for command in PAGE_COMMANDS if command != "create_relation"],
    )


async def report_rows(
    session: MongodbSession, report: ServerReport, names: list[str], filters: list[Filter], sort: list[Sort]
) -> AsyncIterator[list[list[str | None]]]:
    columns, stages = report_pipeline(report, filters, sort)
    known = {column.name for column in columns}
    unknown = [name for name in names if name not in known]
    if unknown:
        raise ValueError(say('Unknown export column: "{column}"', column=unknown[0]))
    async with session.client() as client:
        with session.failures():
            cursor = await _cursor(client, report, stages)
            rows: list[list[str | None]] = []
            async for document in cursor:
                rows.append([read_cell(document.get(name)) for name in names])
                if len(rows) == 500:
                    yield rows
                    rows = []
            if rows:
                yield rows
