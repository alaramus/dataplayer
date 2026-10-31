"""Every document matching a page's query, streamed in bounded batches (D45, D289)."""

from collections.abc import AsyncIterator

from app.adapters.export import EXPORT_BATCH_SIZE, ExportBatch, ExportRequest
from app.adapters.fetch import FetchRequest
from app.adapters.mongodb.fetch import MongodbFetch
from app.adapters.mongodb.report_pages import report_rows
from app.adapters.mongodb.reports import report_for
from app.adapters.mongodb.session import MongodbSession
from app.adapters.mongodb.values import read_cell
from app.core.translation import say


class MongodbExport:
    def __init__(self, session: MongodbSession, fetch: MongodbFetch) -> None:
        self._session = session
        self._fetch = fetch

    def export_rows(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        return self._stream(request)

    async def _stream(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        report = report_for(request.node_id)
        if report is not None:
            async for block in report_rows(
                self._session, report, request.columns, request.filters, request.sort
            ):
                yield ExportBatch(rows=block)
            return
        # A limit of one only to reuse the page's validation; an export has no
        # limit or offset at all.
        prepared = await self._fetch.prepare(
            FetchRequest(node_id=request.node_id, limit=1, filters=request.filters, sort=request.sort)
        )
        known = {column.name for column in prepared.columns}
        unknown = [name for name in request.columns if name not in known]
        if unknown:
            raise ValueError(say('Unknown export column: "{column}"', column=unknown[0]))
        facts = prepared.facts
        async with self._session.client() as client:
            with self._session.failures():
                cursor = client[facts.database][facts.name].find(
                    prepared.query, dict.fromkeys(request.columns, 1), batch_size=EXPORT_BATCH_SIZE
                )
                if prepared.sort:
                    cursor = cursor.sort(prepared.sort)
                rows: list[list[str | None]] = []
                async for document in cursor:
                    rows.append([read_cell(document.get(name)) for name in request.columns])
                    if len(rows) == EXPORT_BATCH_SIZE:
                        yield ExportBatch(rows=rows)
                        rows = []
                if rows:
                    yield ExportBatch(rows=rows)
