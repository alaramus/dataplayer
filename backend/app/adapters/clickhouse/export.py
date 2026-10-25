"""Every row matching a page's query, streamed in bounded batches (D45)."""

from collections.abc import AsyncIterator

from app.adapters.clickhouse.fetch import ClickhouseFetch
from app.adapters.clickhouse.session import ClickhouseSession
from app.adapters.clickhouse.sql import Params
from app.adapters.clickhouse.types import read_cell
from app.adapters.export import EXPORT_BATCH_SIZE, ExportBatch, ExportRequest
from app.adapters.fetch import FetchRequest
from app.core.translation import say


class ClickhouseExport:
    def __init__(self, session: ClickhouseSession, fetch: ClickhouseFetch) -> None:
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
        known = {column.name: column for column in prepared.columns}
        unknown = [name for name in request.columns if name not in known]
        if unknown:
            raise ValueError(say('Unknown export column: "{column}"', column=unknown[0]))
        params = Params()
        statement = prepared.statement(params, [known[name] for name in request.columns])
        async for rows in self._session.stream(
            statement.text(), params.values, batch_size=EXPORT_BATCH_SIZE
        ):
            yield ExportBatch(rows=[[read_cell(value) for value in row] for row in rows])
