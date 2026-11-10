"""Every row matching a page's filters, streamed in bounded batches (D45, D350).

The page's own statement, read on from paging state to paging state; a batch
the server answers short — a filtered read — is passed on as it is.
"""

from collections.abc import AsyncIterator

from app.adapters.cassandra.fetch import CassandraFetch
from app.adapters.cassandra.reports import in_section
from app.adapters.cassandra.session import CassandraSession
from app.adapters.cassandra.types import read_cell
from app.adapters.export import EXPORT_BATCH_SIZE, ExportBatch, ExportRequest
from app.adapters.fetch import FetchRequest
from app.core.translation import say


class CassandraExport:
    def __init__(self, session: CassandraSession, fetch: CassandraFetch) -> None:
        self._session = session
        self._fetch = fetch

    def export_rows(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        return self._stream(request)

    async def _stream(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        if in_section(request.node_id):
            raise ValueError(say("A report is downloaded a page at a time"))
        # A limit of one only to reuse the page's validation; the export has no
        # limit or offset at all.
        prepared = await self._fetch.prepare(
            FetchRequest(
                node_id=request.node_id,
                limit=1,
                filters=request.filters,
                sort=request.sort,
            )
        )
        position = {column.name: index for index, column in enumerate(prepared.columns)}
        unknown = [name for name in request.columns if name not in position]
        if unknown:
            raise ValueError(
                say('Unknown export column: "{column}"', column=unknown[0])
            )
        chosen = [position[name] for name in request.columns]
        types = [column.type for column in prepared.columns]
        state: bytes | None = None
        while True:
            answer = await self._session.page(
                prepared.statement,
                prepared.params,
                fetch_size=EXPORT_BATCH_SIZE,
                paging_state=state,
            )
            # A virtual table answers whole; it is cut into batches here.
            for start in range(0, len(answer.rows), EXPORT_BATCH_SIZE):
                rows = answer.rows[start : start + EXPORT_BATCH_SIZE]
                if rows:
                    yield ExportBatch(
                        rows=[
                            [read_cell(row[index], types[index]) for index in chosen]
                            for row in rows
                        ]
                    )
            state = answer.paging_state
            if state is None:
                return
