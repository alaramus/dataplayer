"""Every row matching a page's query, streamed in bounded batches (D45, D257).

One read connection holds the statement open while the batches are taken from
it, so the rows come from one state of the file; a reader that stops early
closes the connection and with it the statement.
"""

import sqlite3
from collections.abc import AsyncIterator
from typing import Any

from app.adapters.export import EXPORT_BATCH_SIZE, ExportBatch, ExportRequest
from app.adapters.fetch import FetchRequest
from app.adapters.protocol import AdapterError
from app.adapters.sqlite.fetch import SqliteFetch
from app.adapters.sqlite.session import SqliteSession, classify
from app.adapters.sqlite.types import read_cell
from app.core.translation import N_, say


class SqliteExport:
    def __init__(self, session: SqliteSession, fetch: SqliteFetch) -> None:
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
        columns = [known[name] for name in request.columns]
        params: list[Any] = []
        text = prepared.selection(columns, params).text()
        handle = await self._session.handle(writes=False, fallback_message=N_("Export failed"))
        try:
            cursor = await handle.call(lambda connection: connection.execute(text, params))
            while rows := await handle.call(lambda _connection: cursor.fetchmany(EXPORT_BATCH_SIZE)):
                yield ExportBatch(
                    rows=[
                        [read_cell(value, column.type) for value, column in zip(row, columns, strict=True)]
                        for row in rows
                    ]
                )
        except sqlite3.Error as exc:
            error_kind, message = classify(exc, fallback_message=N_("Export failed"))
            raise AdapterError(error_kind, message) from None
        finally:
            await handle.close()
