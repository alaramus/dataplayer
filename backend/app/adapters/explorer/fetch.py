"""Reading a file as rows.

The reader is chosen from the format of the file, matched exhaustively, so
adding a format without a reader fails type checking. The old application
branched on the extension in six places inside one method.
"""

from pathlib import Path
from typing import Any, Literal, assert_never

from anyio import to_thread

from app.adapters.explorer import archive, parquet, workbook
from app.adapters.explorer.binary import looks_binary
from app.adapters.explorer.formats import format_of
from app.adapters.explorer.members import ResolvedNode, resolve_node
from app.adapters.explorer.readers import (
    FILE_FILTER_OPERATORS,
    CsvReader,
    JsonTableReader,
    LogReader,
    Page,
    Reader,
    TextReader,
)
from app.adapters.explorer.storage import Storage
from app.adapters.explorer.update import encode_handle
from app.adapters.fetch import FetchRequest, FetchResult
from app.core.config import settings

CSV_READER = CsvReader()
TEXT_READER = TextReader()
JSON_TABLE_READER = JsonTableReader()
LOG_READER = LogReader()

TextualFormat = Literal["delimited", "json", "jsonl", "log", "text"]


class ExplorerFetch:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    async def fetch(self, request: FetchRequest) -> FetchResult:
        # A file has no index to order by, and ordering one page of it would be
        # ordering the page rather than the file. Looking a value up is a scan
        # the source can do honestly, and does (D109).
        if request.sort:
            raise ValueError("This source cannot sort rows")

        # One hop into the worker thread, resolution included: deciding what a
        # node id names asks the filesystem, which blocks like the read does.
        page, editable, version = await to_thread.run_sync(self._read, request)
        columns = [
            column.model_copy(update=_column_capabilities(editable))
            for column in page.columns
        ]
        return FetchResult(
            columns=columns,
            rows=page.rows,
            has_more=page.has_more,
            # The row's own place in the file, which is not its place on the
            # page once a filter has left rows out (D109).
            row_handles=(
                [encode_handle(position, version) for position in page.positions]
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
        resolved = resolve_node(self._storage, request.node_id)
        if resolved.member is not None:
            with self._storage.local_file(resolved.place) as container:
                if format_of(resolved.name) == "archive":
                    # Expanded into a temporary file and read like any other,
                    # so a table inside an archive needs no second reader
                    # (D53). Paging expands it once per page, which is what
                    # the ceiling is for.
                    with archive.expanded(container, resolved.member) as entry:
                        page = self._read_path(entry, request, name=entry_name(resolved))
                        return page, False, None
                return self._sheet(resolved, container, request), False, None

        found = resolved.entry
        if found is None:
            raise ValueError(f"No such file: {request.node_id}")
        if found.is_directory:
            raise ValueError(f"A directory cannot be read as rows: {request.node_id}")
        place = resolved.place
        before = self._storage.version(place)
        with self._storage.local_file(place) as path:
            page = self._read_path(path, request, name=place.name)
        editable = (
            format_of(place.name) == "delimited"
            and found.size_bytes <= settings.MAX_UPLOAD_BYTES
            and len(page.columns) > 0
        )
        after = self._storage.version(place)
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
                return parquet.read_page(
                    path, request.limit, request.offset, request.filters
                )
            case "workbook":
                # The first sheet somebody would see on opening it in a
                # spreadsheet: a hidden one is hidden because whoever wrote
                # the file did not mean it to be read first. Every other sheet
                # is a member of this node and is read by naming it.
                return workbook.read_page(
                    path,
                    _first_sheet(path),
                    request.limit,
                    request.offset,
                    request.filters,
                )
            case "delimited" | "json" | "jsonl" | "log" | "text" as textual:
                if looks_binary(path):
                    # Classification goes by name; the bytes get the last word.
                    raise ValueError(f"This file is binary: {request.node_id}")
                return _reader_for(textual).read(
                    path, request.limit, request.offset, request.filters
                )
            case "markdown" | "image" | "audio" | "video" | "pdf" | "archive" | "opaque":
                raise ValueError(f"This file cannot be read as rows: {request.node_id}")
            case unreachable:
                assert_never(unreachable)

    def _sheet(
        self, resolved: ResolvedNode, path: Path, request: FetchRequest
    ) -> Page:
        """One page of one worksheet, named by the member part of the id."""
        member = resolved.member
        if member is None or not member.isdigit():
            raise ValueError(f"No such sheet: {request.node_id}")
        return workbook.read_page(
            path, int(member), request.limit, request.offset, request.filters
        )


def _column_capabilities(editable: bool) -> dict[str, Any]:
    """What the file source states every column of a page can do.

    Filtering is stated for every tabular projection, editing only where the
    representation is one the source can write back (D48).
    """
    if not editable:
        return {"filter_operators": FILE_FILTER_OPERATORS}
    return {
        "filter_operators": FILE_FILTER_OPERATORS,
        "editable": True,
        "nullable": True,
        "insertable": True,
    }


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
