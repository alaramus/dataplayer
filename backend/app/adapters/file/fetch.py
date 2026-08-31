"""Reading a file as rows.

The reader is chosen from the format of the file, matched exhaustively, so
adding a format without a reader fails type checking. The old application
branched on the extension in six places inside one method.
"""

from typing import Literal, assert_never

from anyio import to_thread

from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.file import parquet, workbook
from app.adapters.file.binary import looks_binary
from app.adapters.file.formats import format_of
from app.adapters.file.members import ResolvedNode, resolve_node
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

TextualFormat = Literal["delimited", "json", "jsonl", "text"]


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

        # One hop into the worker thread, resolution included: deciding what a
        # node id names asks the filesystem, which blocks like the read does.
        page = await to_thread.run_sync(self._read, request)
        return FetchResult(
            columns=page.columns,
            rows=page.rows,
            has_more=page.has_more,
            row_handles=[None for _ in page.rows],
            update_reason="This source is read-only",
            insert_reason="This source is read-only",
            delete_reason="This source is read-only",
        )

    def _read(self, request: FetchRequest) -> Page:
        resolved = resolve_node(self._session, request.node_id)
        if resolved.member is not None:
            return self._sheet(resolved, request)

        path = resolved.path
        if not path.exists():
            raise ValueError(f"No such file: {request.node_id}")
        if path.is_dir():
            raise ValueError(f"A directory cannot be read as rows: {request.node_id}")

        match format_of(path.name):
            case "parquet":
                # Binary by nature, so the sniff below would refuse it. Its own
                # magic bytes are what the footer read checks instead.
                return parquet.read_page(path, request.limit, request.offset)
            case "workbook":
                raise ValueError(
                    f"A workbook is read one sheet at a time: {request.node_id}"
                )
            case "delimited" | "json" | "jsonl" | "text" as textual:
                if looks_binary(path):
                    # Classification goes by name; the bytes get the last word.
                    raise ValueError(f"This file is binary: {request.node_id}")
                return _reader_for(textual).read(path, request.limit, request.offset)
            case "markdown" | "image" | "opaque":
                raise ValueError(f"This file cannot be read as rows: {request.node_id}")
            case unreachable:
                assert_never(unreachable)

    def _sheet(self, resolved: ResolvedNode, request: FetchRequest) -> Page:
        """One page of one worksheet, named by the member part of the id."""
        member = resolved.member
        if member is None or not member.isdigit():  # pragma: no cover - defensive
            raise ValueError(f"No such sheet: {request.node_id}")
        return workbook.read_page(
            resolved.path, int(member), request.limit, request.offset
        )


def _reader_for(file_format: TextualFormat) -> Reader:
    match file_format:
        case "delimited":
            return CSV_READER
        case "json" | "jsonl":
            return JSON_TABLE_READER
        case "text":
            return TEXT_READER
        case unreachable:
            assert_never(unreachable)
