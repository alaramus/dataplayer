"""Reading a file as rows.

The reader is chosen from the format of the file, matched exhaustively, so
adding a format without a reader fails type checking. The old application
branched on the extension in six places inside one method.
"""

from pathlib import Path
from typing import assert_never

from anyio import to_thread

from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.file.binary import looks_binary
from app.adapters.file.formats import format_of
from app.adapters.file.readers import (
    CsvReader,
    JsonTableReader,
    Page,
    Reader,
    TextReader,
)
from app.adapters.file.session import FileSession

CSV_READER = CsvReader()
TEXT_READER = TextReader()
JSON_TABLE_READER = JsonTableReader()


class FileFetch:
    def __init__(self, session: FileSession) -> None:
        self._session = session

    async def fetch(self, request: FetchRequest) -> FetchResult:
        # Neither is possible over a file: there is no index to order by, and
        # the columns of a delimited file have no types to compare. Saying so
        # beats sorting one page and calling it sorted.
        if request.sort:
            raise ValueError("This source cannot sort rows")
        if request.filters:
            raise ValueError("This source cannot filter rows")

        path = self._session.resolve(request.node_id)
        page = await to_thread.run_sync(self._read, path, request)
        return FetchResult(
            columns=page.columns,
            rows=page.rows,
            has_more=page.has_more,
            row_handles=[None for _ in page.rows],
            update_reason="This source is read-only",
            insert_reason="This source is read-only",
            delete_reason="This source is read-only",
        )

    def _read(self, path: Path, request: FetchRequest) -> Page:
        if not path.exists():
            raise ValueError(f"No such file: {request.node_id}")
        if path.is_dir():
            raise ValueError(f"A directory cannot be read as rows: {request.node_id}")

        reader = _reader_for(path, request.node_id)
        if looks_binary(path):
            # Classification goes by name; the bytes get the last word.
            raise ValueError(f"This file is binary: {request.node_id}")
        return reader.read(path, request.limit, request.offset)


def _reader_for(path: Path, node_id: str) -> Reader:
    match format_of(path.name):
        case "delimited":
            return CSV_READER
        case "json" | "jsonl":
            return JSON_TABLE_READER
        case "text":
            return TEXT_READER
        case "image" | "opaque":
            raise ValueError(f"This file cannot be read as rows: {node_id}")
        case unreachable:
            assert_never(unreachable)
