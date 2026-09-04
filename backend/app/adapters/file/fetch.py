"""Reading a file as rows.

The reader is chosen from the format of the file, matched exhaustively, so
adding a format without a reader fails type checking. The old application
branched on the extension in six places inside one method.
"""

from pathlib import Path
from typing import Literal, assert_never

from anyio import to_thread

from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.file import archive, parquet, workbook
from app.adapters.file.binary import looks_binary
from app.adapters.file.formats import format_of
from app.adapters.file.members import ResolvedNode, resolve_node
from app.adapters.file.readers import (
    CsvReader,
    JsonTableReader,
    LogReader,
    Page,
    Reader,
    TextReader,
)
from app.adapters.file.session import FileSession
from app.adapters.file.update import encode_handle, file_version
from app.core.config import settings

CSV_READER = CsvReader()
TEXT_READER = TextReader()
JSON_TABLE_READER = JsonTableReader()
LOG_READER = LogReader()

TextualFormat = Literal["delimited", "json", "jsonl", "log", "text"]


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
        page, editable, version = await to_thread.run_sync(self._read, request)
        columns = [
            column.model_copy(
                update={"editable": True, "nullable": True, "insertable": True}
            )
            if editable
            else column
            for column in page.columns
        ]
        return FetchResult(
            columns=columns,
            rows=page.rows,
            has_more=page.has_more,
            row_handles=(
                [encode_handle(request.offset + index, version) for index in range(len(page.rows))]
                if editable and version is not None
                else [None for _ in page.rows]
            ),
            update_supported=editable,
            update_reason=None if editable else "This file representation is read-only",
            insert_supported=editable,
            insert_reason=None if editable else "This file representation is read-only",
            delete_supported=editable,
            delete_reason=None if editable else "This file representation is read-only",
        )

    def _read(self, request: FetchRequest) -> tuple[Page, bool, str | None]:
        resolved = resolve_node(self._session, request.node_id)
        if resolved.member is not None:
            if format_of(resolved.path.name) == "archive":
                # Expanded into a temporary file and read like any other, so a
                # table inside an archive needs no second reader (D53). Paging
                # expands it once per page, which is what the ceiling is for.
                with archive.expanded(resolved.path, resolved.member) as entry:
                    return self._read_path(entry, request, name=entry_name(resolved)), False, None
            return self._sheet(resolved, request), False, None

        path = resolved.path
        if not path.exists():
            raise ValueError(f"No such file: {request.node_id}")
        if path.is_dir():
            raise ValueError(f"A directory cannot be read as rows: {request.node_id}")
        before = file_version(path)
        page = self._read_path(path, request, name=path.name)
        editable = (
            format_of(path.name) == "delimited"
            and path.stat().st_size <= settings.MAX_UPLOAD_BYTES
            and len(page.columns) > 0
        )
        after = file_version(path)
        if editable and before != after:
            raise ValueError("The file changed while this page was being read; reload it")
        return page, editable, after if editable else None

    def _read_path(self, path: Path, request: FetchRequest, *, name: str) -> Page:
        """One page out of a path, with the reader chosen by the node's name.

        The name is passed rather than taken from the path, because an entry
        expanded out of an archive lives in a temporary file whose name says
        nothing about what is in it.
        """
        match format_of(name):
            case "parquet":
                # Binary by nature, so the sniff below would refuse it. Its own
                # magic bytes are what the footer read checks instead.
                return parquet.read_page(path, request.limit, request.offset)
            case "workbook":
                # The first sheet somebody would see on opening it in a
                # spreadsheet: a hidden one is hidden because whoever wrote
                # the file did not mean it to be read first. Every other sheet
                # is a member of this node and is read by naming it.
                return workbook.read_page(
                    path, _first_sheet(path), request.limit, request.offset
                )
            case "delimited" | "json" | "jsonl" | "log" | "text" as textual:
                if looks_binary(path):
                    # Classification goes by name; the bytes get the last word.
                    raise ValueError(f"This file is binary: {request.node_id}")
                return _reader_for(textual).read(path, request.limit, request.offset)
            case "markdown" | "image" | "audio" | "video" | "pdf" | "archive" | "opaque":
                raise ValueError(f"This file cannot be read as rows: {request.node_id}")
            case unreachable:
                assert_never(unreachable)

    def _sheet(self, resolved: ResolvedNode, request: FetchRequest) -> Page:
        """One page of one worksheet, named by the member part of the id."""
        member = resolved.member
        if member is None or not member.isdigit():
            raise ValueError(f"No such sheet: {request.node_id}")
        return workbook.read_page(
            resolved.path, int(member), request.limit, request.offset
        )


def _first_sheet(path: Path) -> int:
    """Which sheet a workbook opens as, and a refusal when it has none.

    Visible ones first, in the workbook's own order; a file of nothing but
    hidden sheets falls back to the first of those rather than refusing,
    because a person who opened it wants to see what is in it.
    """
    found = workbook.sheets(path)
    if not found:
        raise ValueError(f"This workbook has no sheets: {path.name}")
    visible = [sheet for sheet in found if not sheet.hidden]
    return (visible or found)[0].position


def entry_name(resolved: ResolvedNode) -> str:
    """The name of a member, which is what decides how it is read."""
    member = resolved.member or ""
    return member.rsplit("/", 1)[-1]


def _reader_for(file_format: TextualFormat) -> Reader:
    match file_format:
        case "delimited":
            return CSV_READER
        case "json" | "jsonl":
            return JSON_TABLE_READER
        case "log":
            return LOG_READER
        case "text":
            return TEXT_READER
        case unreachable:
            assert_never(unreachable)
