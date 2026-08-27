"""Reading a file as rows.

The reader is chosen from what the file is, matched exhaustively, so adding a
content kind without a reader fails type checking. The old application
branched on the extension in six places inside one method.
"""

from pathlib import Path
from typing import assert_never

from anyio import to_thread

from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.file.readers import CsvReader, Page, Reader, TextReader, classify
from app.adapters.file.session import FileSession

CSV_READER = CsvReader()
TEXT_READER = TextReader()

# Enough to catch a binary file without reading it whole.
_SNIFF_BYTES = 4096


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
        )

    def _read(self, path: Path, request: FetchRequest) -> Page:
        if not path.exists():
            raise ValueError(f"No such file: {request.node_id}")
        if path.is_dir():
            raise ValueError(f"A directory cannot be read as rows: {request.node_id}")

        reader = _reader_for(path, request.node_id)
        if _looks_binary(path):
            # Classification goes by name; the bytes get the last word.
            raise ValueError(f"This file is binary: {request.node_id}")
        return reader.read(path, request.limit, request.offset)


def _reader_for(path: Path, node_id: str) -> Reader:
    content_kind = classify(path.name)
    match content_kind:
        case "table":
            return CSV_READER
        case "text":
            return TEXT_READER
        case "opaque":
            raise ValueError(f"This file cannot be read as rows: {node_id}")
        case unreachable:
            assert_never(unreachable)


def _looks_binary(path: Path) -> bool:
    with path.open("rb") as handle:
        return b"\x00" in handle.read(_SNIFF_BYTES)
