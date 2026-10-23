"""Every row matching a page's query, streamed in bounded batches (D45)."""

from collections.abc import AsyncIterator

from app.adapters.export import EXPORT_BATCH_SIZE, ExportBatch, ExportRequest
from app.adapters.fetch import FetchRequest
from app.adapters.mysql.fetch import MysqlFetch
from app.adapters.mysql.session import MysqlSession
from app.adapters.mysql.types import read_cell
from app.core.translation import say


class MysqlExport:
    def __init__(self, session: MysqlSession, fetch: MysqlFetch) -> None:
        self._session = session
        self._fetch = fetch

    def export_rows(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        return self._stream(request)

    async def _stream(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        # A limit of one only to reuse the page's validation; the export has no
        # limit or offset at all.
        prepared = await self._fetch.prepare(
            FetchRequest(node_id=request.node_id, limit=1, filters=request.filters, sort=request.sort)
        )
        known = {column.name: column for column in prepared.shape.columns}
        unknown = [name for name in request.columns if name not in known]
        if unknown:
            raise ValueError(say('Unknown export column: "{column}"', column=unknown[0]))
        columns = [known[name] for name in request.columns]
        params: list[object] = []
        statement = prepared.statement(columns, params)
        async for rows in self._session.stream(
            statement.text(), tuple(params), batch_size=EXPORT_BATCH_SIZE
        ):
            yield ExportBatch(
                rows=[[read_cell(row[column.name], column.type) for column in columns] for row in rows]
            )
