"""Whole-relation export through one PostgreSQL server-side cursor."""

from collections.abc import AsyncIterator

from app.adapters.export import EXPORT_BATCH_SIZE, ExportBatch, ExportRequest
from app.adapters.fetch import FetchRequest
from app.adapters.postgres.fetch import PostgresFetch, encode_cell
from app.adapters.postgres.session import PostgresSession


class PostgresExport:
    def __init__(self, session: PostgresSession, fetch: PostgresFetch) -> None:
        self._session = session
        self._fetch = fetch

    def export_rows(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        return self._stream(request)

    async def _stream(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        # A limit of one exists only to reuse the page query's validation
        # object. It never reaches the export statement, which has no limit or
        # offset at all.
        prepared = await self._fetch.prepare(
            FetchRequest(
                node_id=request.node_id,
                limit=1,
                filters=request.filters,
                sort=request.sort,
            )
        )
        statement, params, columns = self._fetch.build_export(
            prepared, request.columns
        )
        bound = tuple(params) if params else None
        async for rows in self._session.stream_query(
            statement.as_string(), bound, batch_size=EXPORT_BATCH_SIZE
        ):
            yield ExportBatch(
                rows=[
                    [encode_cell(row[column.name], column.type) for column in columns]
                    for row in rows
                ]
            )
