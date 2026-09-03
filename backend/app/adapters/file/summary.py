"""Describing one node of a file source: its facts, and what its format states.

Nothing here is a viewer and nothing here is an action (D75). Every reader is
one this source already had — the archive's central directory, the workbook's
sheet list, the Parquet footer, the media header — and the only reading written
for this capability is the one pass that counts the lines of a text file, which
nothing else needed.

Two ceilings hold it up: a file larger than `MAX_COUNTED_BYTES` is not counted
and says so, and a directory of more than `MAX_ENTRIES` is not counted for the
reason its listing is refused.
"""

import codecs
import csv
import os
import re
import stat as filestat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from anyio import to_thread
from PIL import Image, UnidentifiedImageError

from app.adapters.dataset import WorksheetDataset
from app.adapters.delimited import delimiter_name, delimiter_of, usable_names
from app.adapters.file import archive, media, parquet, workbook
from app.adapters.file.catalog import MAX_ENTRIES
from app.adapters.file.content import IMAGE_MEDIA_TYPES
from app.adapters.file.formats import (
    TABLE,
    format_of,
    representations_inside_archive,
    representations_of,
)
from app.adapters.file.members import ResolvedNode, resolve_node
from app.adapters.file.session import FileSession
from app.adapters.protocol import NodeNotFound
from app.adapters.summary import (
    ArchiveContents,
    AudioContents,
    DelimitedContents,
    DirectoryContents,
    EntryContents,
    ImageContents,
    LineEndings,
    NodeContents,
    NodeSummary,
    PdfContents,
    TextContents,
    TextEncoding,
    VideoContents,
    WorkbookContents,
)

# What is read to count lines or rows. Well above the 4 MB a document is edited
# whole at (D48) and far below what a log directory holds: the point is that a
# file nobody would wait for is not waited for.
MAX_COUNTED_BYTES = 32 * 1024 * 1024

COUNT_CHUNK_BYTES = 256 * 1024

# Both spellings and the lone carriage return, longest first so a `\r\n` is one
# terminator rather than two.
_TERMINATOR = re.compile(rb"\r\n|\n|\r")

_TOO_LARGE = (
    f"This file is larger than {MAX_COUNTED_BYTES // (1024 * 1024)} MB "
    "and was not read through"
)


class FileSummaries:
    """The `node-summary` capability of the file source."""

    def __init__(self, session: FileSession) -> None:
        self._session = session

    async def node_summary(self, node_id: str) -> NodeSummary:
        return await to_thread.run_sync(self._describe, node_id)

    def _describe(self, node_id: str) -> NodeSummary:
        # Resolution judges containment before anything is opened, exactly as
        # every other read of this source does (D8).
        resolved = resolve_node(self._session, node_id)
        if resolved.member is not None:
            return _member(resolved, node_id)
        path = resolved.path
        if not path.exists():
            raise NodeNotFound(node_id)
        return _directory(path, node_id) if path.is_dir() else _file(path, node_id)


def _file(path: Path, node_id: str) -> NodeSummary:
    facts = _facts(path.stat())
    contents, notice = _contents(path)
    return NodeSummary(
        node_id=node_id,
        name=path.name,
        kind="file",
        representations=representations_of(path.name),
        size_bytes=facts.size_bytes,
        modified_at=facts.modified_at,
        accessed_at=facts.accessed_at,
        created_at=facts.created_at,
        permissions=facts.permissions,
        contents=contents,
        notice=notice,
    )


def _directory(path: Path, node_id: str) -> NodeSummary:
    facts = _facts(path.stat())
    return NodeSummary(
        node_id=node_id,
        name=path.name,
        kind="directory",
        # A folder is walked into rather than opened, so it declares none — the
        # same answer its catalog node gives.
        representations=[],
        size_bytes=facts.size_bytes,
        modified_at=facts.modified_at,
        accessed_at=facts.accessed_at,
        created_at=facts.created_at,
        permissions=facts.permissions,
        contents=_directory_contents(path),
    )


@dataclass(frozen=True)
class _Facts:
    """What one `stat` states, before a format is asked anything."""

    size_bytes: int
    modified_at: datetime
    accessed_at: datetime
    created_at: datetime | None
    permissions: str


def _facts(stat: os.stat_result) -> _Facts:
    """The size, the times and the mode, as the platform states them.

    A creation time is reported only where the platform keeps one. Linux keeps
    `st_ctime`, which is when the inode last changed — a different fact wearing
    the same name, and filling this field with it would be a plausible lie.
    """
    birth: float | None = getattr(stat, "st_birthtime", None)
    return _Facts(
        size_bytes=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
        accessed_at=datetime.fromtimestamp(stat.st_atime, tz=UTC),
        created_at=None if birth is None else datetime.fromtimestamp(birth, tz=UTC),
        permissions=filestat.filemode(stat.st_mode),
    )


def _member(resolved: ResolvedNode, node_id: str) -> NodeSummary:
    """A node that lives inside a container file: a sheet, or an archive entry."""
    if format_of(resolved.path.name) == "archive":
        return _entry(resolved, node_id)
    return _worksheet(resolved, node_id)


def _entry(resolved: ResolvedNode, node_id: str) -> NodeSummary:
    member = resolved.member
    if member is None:
        raise NodeNotFound(node_id)
    try:
        entry = archive.entry_at(resolved.path, member)
    except ValueError:
        raise NodeNotFound(node_id) from None
    return NodeSummary(
        node_id=node_id,
        name=entry.name,
        kind="entry",
        representations=(
            representations_inside_archive(entry.name) if entry.readable else []
        ),
        size_bytes=None if entry.is_directory else entry.size_bytes,
        modified_at=entry.modified_at,
        contents=EntryContents(
            compressed_bytes=None if entry.is_directory else entry.compressed_bytes,
            encrypted=entry.is_encrypted,
            link=entry.is_link,
        ),
        # An entry is not expanded to be described: what it holds costs a write
        # of up to 32 MB (D53), and this question is not worth one.
        notice=None,
    )


def _worksheet(resolved: ResolvedNode, node_id: str) -> NodeSummary:
    member = resolved.member
    if member is None or not member.isdigit():
        raise NodeNotFound(node_id)
    try:
        sheets = workbook.sheets(resolved.path)
    except ValueError as exc:
        raise NodeNotFound(node_id) from exc
    facts = next(
        (sheet for sheet in sheets if sheet.position == int(member)), None
    )
    if facts is None:
        raise NodeNotFound(node_id)
    return NodeSummary(
        node_id=node_id,
        name=facts.title,
        kind="dataset",
        representations=[TABLE],
        # A sheet has no bytes and no times of its own; the workbook has both,
        # and answering with the workbook's would be answering about the wrong
        # node.
        contents=WorksheetDataset(
            workbook=resolved.path.name,
            sheet_name=facts.title,
            sheet_position=facts.position,
            sheet_count=len(sheets),
            hidden=facts.hidden,
            rows=facts.rows,
            columns=facts.columns,
        ),
    )


def _contents(path: Path) -> tuple[NodeContents | None, str | None]:
    """What the format states, or why it could not say.

    Every message here is written in this repository. A reader's own refusal is
    passed on, an `OSError` is not: its text carries the path of the file, and
    driver text never reaches a caller (ENGINEERING).
    """
    try:
        return _read_contents(path), None
    except ValueError as exc:
        return None, str(exc)
    except OSError:
        return None, "This file could not be read"


def _read_contents(path: Path) -> NodeContents | None:
    match format_of(path.name):
        case "delimited":
            return _delimited_contents(path)
        case "text" | "markdown" | "json" | "jsonl" | "log":
            # A log is text as far as this is concerned: how many lines, what
            # encoding, how long the longest one is. What shape those lines are
            # in is a question the table asks, not the summary.
            return _text_contents(path)
        case "parquet":
            return parquet.describe(path)[1]
        case "workbook":
            return _workbook_contents(path)
        case "archive":
            return _archive_contents(path)
        case "image":
            return _image_contents(path)
        case "audio":
            facts = media.audio_facts(path)
            return AudioContents(
                media_type=facts.media_type,
                duration_seconds=facts.duration_seconds,
                channels=facts.channels,
                sample_rate=facts.sample_rate,
            )
        case "video":
            video = media.video_facts(path)
            return VideoContents(
                media_type=video.media_type,
                duration_seconds=video.duration_seconds,
                width=video.width,
                height=video.height,
            )
        case "pdf":
            return PdfContents(version=media.pdf_facts(path).version)
        case "opaque":
            # A font, an executable, a legacy document: the facts every file
            # has are the whole answer, and inventing more would need a
            # decoder this source does not have.
            return None


@dataclass(frozen=True)
class _TextScan:
    """One pass over the bytes of a file, and everything it can state."""

    encoding: TextEncoding
    lines: int | None = None
    longest_line_bytes: int | None = None
    line_endings: LineEndings | None = None
    not_counted: str | None = None


def _text_contents(path: Path) -> TextContents:
    scan = _scan(path)
    return TextContents(
        encoding=scan.encoding,
        lines=scan.lines,
        longest_line_bytes=scan.longest_line_bytes,
        line_endings=scan.line_endings,
        not_counted=scan.not_counted,
    )


def _delimited_contents(path: Path) -> DelimitedContents:
    scan = _scan(path)
    if scan.not_counted is not None:
        return DelimitedContents(
            encoding=scan.encoding, not_counted=scan.not_counted
        )
    try:
        delimiter, columns, rows = _count_rows(path)
    except csv.Error:
        # A field longer than the parser's limit, or a line it cannot read.
        # The file is still a file, and its own facts still stand.
        return DelimitedContents(
            encoding=scan.encoding,
            not_counted="This file could not be read as delimited rows",
        )
    return DelimitedContents(
        delimiter=delimiter_name(delimiter),
        columns=columns,
        rows=rows,
        encoding=scan.encoding,
    )


def _count_rows(path: Path) -> tuple[str, int, int]:
    """The delimiter, the width of the header and the number of data rows.

    Counted by `csv` rather than by newlines: a quoted value may hold a line
    ending, and a count that ignored that would disagree with the grid.
    """
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        delimiter = delimiter_of(path.name, handle.readline())
        handle.seek(0)
        reader = csv.reader(handle, delimiter=delimiter)
        header = next(reader, None)
        if header is None:
            return delimiter, 0, 0
        return delimiter, len(usable_names(header)), sum(1 for _ in reader)


def _workbook_contents(path: Path) -> WorkbookContents:
    sheets = workbook.sheets(path)
    return WorkbookContents(
        sheets=len(sheets),
        hidden_sheets=sum(1 for sheet in sheets if sheet.hidden),
    )


def _archive_contents(path: Path) -> ArchiveContents:
    totals = archive.totals(path)
    return ArchiveContents(
        entries=totals.entries,
        files=totals.files,
        directories=totals.directories,
        size_bytes=totals.size_bytes,
        compressed_bytes=totals.compressed_bytes,
        encrypted=totals.encrypted,
        links=totals.links,
    )


def _image_contents(path: Path) -> ImageContents:
    """The header of an image, without decoding a pixel.

    Pillow reads the header on `open` and the raster only when it is asked for
    one, so this costs a few kilobytes whatever the image weighs. Its own
    messages name the file, so the refusal is ours.
    """
    try:
        with Image.open(path) as image:
            media_type = IMAGE_MEDIA_TYPES.get(image.format or "")
            width, height = image.size
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError):
        raise ValueError("This file is not a valid PNG or JPEG image") from None
    if media_type is None:
        raise ValueError("Only PNG and JPEG images are described here")
    if width < 1 or height < 1:
        raise ValueError("This image states no size")
    return ImageContents(media_type=media_type, width=width, height=height)


def _directory_contents(path: Path) -> DirectoryContents:
    """One level of a folder, counted with one listing.

    Bounded by the number its own listing is bounded by, so a folder the
    catalog refuses to list is a folder this refuses to count, with the same
    number in both messages.
    """
    files = 0
    directories = 0
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                if files + directories == MAX_ENTRIES:
                    return DirectoryContents(
                        not_counted=(
                            f"This folder holds more than {MAX_ENTRIES} entries"
                        )
                    )
                try:
                    is_directory = entry.is_dir()
                except OSError:
                    # A link whose target has gone: it is an entry of the
                    # folder, and it is not a folder.
                    is_directory = False
                if is_directory:
                    directories += 1
                else:
                    files += 1
    except OSError:
        return DirectoryContents(not_counted="This folder could not be read")
    return DirectoryContents(
        entries=files + directories, files=files, directories=directories
    )


def _scan(path: Path) -> _TextScan:
    """One pass over the bytes: the encoding, the lines and the longest of them.

    Chunked and bounded, so nothing here holds a file — or a line — whole. The
    terminator is looked for in both spellings and in the lone carriage return,
    because "which of them is in this file" is one of the things being asked.
    """
    if path.stat().st_size > MAX_COUNTED_BYTES:
        return _TextScan(encoding=_encoding_of_prefix(path), not_counted=_TOO_LARGE)

    decoder = codecs.getincrementaldecoder("utf-8")()
    valid = True
    bom = False
    first = True
    lf = 0
    crlf = 0
    carriage = 0
    longest = 0
    current = 0
    carry = b""

    with path.open("rb") as handle:
        while chunk := handle.read(COUNT_CHUNK_BYTES):
            if first:
                bom = chunk.startswith(codecs.BOM_UTF8)
                first = False
            if valid:
                try:
                    decoder.decode(chunk)
                except UnicodeDecodeError:
                    valid = False

            data = carry + chunk
            carry = b""
            if data.endswith(b"\r"):
                # Held back: the next chunk may open with the other half of a
                # `\r\n`, and a terminator split across a read is still one.
                data = data[:-1]
                carry = b"\r"

            position = 0
            for match in _TERMINATOR.finditer(data):
                current += match.start() - position
                longest = max(longest, current)
                current = 0
                position = match.end()
                if match.group() == b"\r\n":
                    crlf += 1
                elif match.group() == b"\n":
                    lf += 1
                else:
                    carriage += 1
            current += len(data) - position

    if carry:
        # The file ends with a carriage return, which terminates its last line.
        longest = max(longest, current)
        current = 0
        carriage += 1
    longest = max(longest, current)

    if valid:
        try:
            decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            # Truncated in the middle of a character: the bytes are not text.
            valid = False

    terminators = lf + crlf + carriage
    return _TextScan(
        encoding=_encoding(valid, bom),
        lines=terminators + (1 if current > 0 else 0),
        longest_line_bytes=longest,
        line_endings=_endings(lf, crlf, carriage),
        not_counted=None,
    )


def _encoding(valid: bool, bom: bool) -> TextEncoding:
    if not valid:
        return "not-utf-8"
    return "utf-8-bom" if bom else "utf-8"


def _encoding_of_prefix(path: Path) -> TextEncoding:
    """The encoding of a file too large to read through.

    One chunk decides it: a byte that is not UTF-8 in the first quarter of a
    megabyte is enough to say the file is not, while the absence of one says
    only that the beginning is — which is why the count beside it is absent and
    the reason is stated.
    """
    with path.open("rb") as handle:
        head = handle.read(COUNT_CHUNK_BYTES)
    decoder = codecs.getincrementaldecoder("utf-8")()
    try:
        decoder.decode(head)
    except UnicodeDecodeError:
        return "not-utf-8"
    return "utf-8-bom" if head.startswith(codecs.BOM_UTF8) else "utf-8"


def _endings(lf: int, crlf: int, carriage: int) -> LineEndings:
    present = [
        name
        for name, count in (("lf", lf), ("crlf", crlf), ("cr", carriage))
        if count > 0
    ]
    if not present:
        return "none"
    if len(present) > 1:
        return "mixed"
    single = present[0]
    # Narrowed by hand: a list comprehension cannot carry the literal type.
    if single == "lf":
        return "lf"
    return "crlf" if single == "crlf" else "cr"

