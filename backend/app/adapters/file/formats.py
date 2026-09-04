"""File formats and the representations each one offers."""

from pathlib import PurePosixPath
from typing import Literal

from app.adapters.content import NodeRepresentation

DELIMITED_EXTENSIONS: frozenset[str] = frozenset({".csv", ".tsv"})
JSON_EXTENSIONS: frozenset[str] = frozenset({".json"})
JSON_LINES_EXTENSIONS: frozenset[str] = frozenset({".jsonl", ".ndjson"})
IMAGE_EXTENSIONS: frozenset[str] = frozenset({".jpeg", ".jpg", ".png"})
MARKDOWN_EXTENSIONS: frozenset[str] = frozenset({".markdown", ".md"})
# Only `.log`. A `.txt` is as likely to be a note as a log, and offering every
# text file a table of one column called "line" is offering nothing.
LOG_EXTENSIONS: frozenset[str] = frozenset({".log"})
PARQUET_EXTENSIONS: frozenset[str] = frozenset({".parquet"})
# What a browser can play, and nothing beyond it: `.avi` stays opaque because
# no browser plays it, and a viewer would be a promise this source cannot keep.
AUDIO_EXTENSIONS: frozenset[str] = frozenset(
    {".flac", ".m4a", ".mp3", ".oga", ".ogg", ".opus", ".wav"}
)
VIDEO_EXTENSIONS: frozenset[str] = frozenset(
    {".m4v", ".mov", ".mp4", ".ogv", ".webm"}
)
PDF_EXTENSIONS: frozenset[str] = frozenset({".pdf"})
# ZIP alone: a tar has no index, so listing it means reading it end to end and
# reading one entry means reading it again (D53).
ARCHIVE_EXTENSIONS: frozenset[str] = frozenset({".zip"})
# `.xls` is deliberately absent: the legacy binary format is a different
# container needing a different library, so it stays opaque and downloadable.
WORKBOOK_EXTENSIONS: frozenset[str] = frozenset({".xlsm", ".xlsx"})

# Classification is intentionally by name in the catalog: inspecting every
# entry would cost one open per file. The content reader checks the bytes when
# that one node is actually opened.
BINARY_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".7z",
        ".avi",
        ".backup",
        ".bin",
        ".bz2",
        ".class",
        ".dll",
        ".doc",
        ".docx",
        # What `pg_dump --format=custom` writes, which is what this
        # application's own backups are. Named here rather than left to the
        # byte sniff: the sniff runs when a file is opened, so without this
        # the catalog offers a text viewer, the click opens a panel and the
        # refusal arrives after the request that had to be made to find out.
        ".dump",
        ".exe",
        ".gif",
        ".gz",
        ".ico",
        ".iso",
        ".jar",
        ".jpeg",
        ".jpg",
        ".odt",
        ".pgdump",
        ".png",
        ".ppt",
        ".pptx",
        ".rar",
        ".so",
        ".tar",
        ".tgz",
        ".ttf",
        ".webp",
        ".woff",
        ".woff2",
        ".xls",
        ".zst",
    }
)

FileFormat = Literal[
    "delimited",
    "json",
    "jsonl",
    "log",
    "text",
    "markdown",
    "image",
    "parquet",
    "workbook",
    "audio",
    "video",
    "pdf",
    "archive",
    "opaque",
]

TABLE = NodeRepresentation(kind="table", title="View as table")
TEXT = NodeRepresentation(kind="text", title="View as text")
JSON = NodeRepresentation(kind="json", title="View JSON")
JSON_LINES = NodeRepresentation(kind="jsonl", title="View JSON lines")
IMAGE = NodeRepresentation(kind="image", title="View image")
MARKDOWN = NodeRepresentation(kind="markdown", title="View as document")
AUDIO = NodeRepresentation(kind="audio", title="Play")
VIDEO = NodeRepresentation(kind="video", title="Play")
PDF = NodeRepresentation(kind="pdf", title="Read")


def format_of(name: str) -> FileFormat:
    suffix = PurePosixPath(name).suffix.lower()
    if suffix in DELIMITED_EXTENSIONS:
        return "delimited"
    if suffix in JSON_EXTENSIONS:
        return "json"
    if suffix in JSON_LINES_EXTENSIONS:
        return "jsonl"
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in MARKDOWN_EXTENSIONS:
        return "markdown"
    if suffix in LOG_EXTENSIONS:
        return "log"
    if suffix in PARQUET_EXTENSIONS:
        return "parquet"
    if suffix in WORKBOOK_EXTENSIONS:
        return "workbook"
    if suffix in AUDIO_EXTENSIONS:
        return "audio"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    if suffix in PDF_EXTENSIONS:
        return "pdf"
    if suffix in ARCHIVE_EXTENSIONS:
        return "archive"
    if suffix in BINARY_EXTENSIONS:
        return "opaque"
    return "text"


def representations_of(name: str) -> list[NodeRepresentation]:
    """Available representations, preferred one first."""
    match format_of(name):
        case "delimited":
            return [TABLE]
        case "json":
            return [JSON, TABLE]
        case "jsonl":
            return [JSON_LINES, TABLE]
        case "log":
            # Text first, because that is what a log is and reading it is what
            # people do to one. A table second, because a log line is not
            # shapeless: it carries a time, a level and a message, and every
            # tool that shows logs shows those as columns. What shape this
            # file's lines are in is read off the file itself — see `logs.py`.
            return [TEXT, TABLE]
        case "text":
            # A text file has no columns of its own, so numbering its lines
            # was a table in name only. It is offered as source, and nothing
            # else.
            return [TEXT]
        case "markdown":
            # Rendered first, source second: the same bytes, and the editor of
            # D48 is what the second one opens.
            return [MARKDOWN, TEXT]
        case "image":
            return [IMAGE]
        case "parquet":
            # A columnar file states its own columns and their types, so its
            # table is the file rather than a projection of one (D51).
            return [TABLE]
        case "workbook":
            # A workbook is not one table. Its sheets are children, and each of
            # them declares the table; the file itself opens nothing.
            return []
        case "audio":
            return [AUDIO]
        case "video":
            return [VIDEO]
        case "pdf":
            return [PDF]
        case "archive":
            # An archive has no viewer of its own: it is walked into, and what
            # is inside it has the viewers (D53).
            return []
        case "opaque":
            # An archive, a font, a legacy document: still listed, still
            # downloadable, and honest about having no viewer rather than
            # opening something that cannot be shown.
            return []


# Which representations are the source of a document rather than a rendering
# of it. Everything here is served by the one editor route, so a format that
# offers any of them has text to show.
SOURCE_KINDS: frozenset[str] = frozenset({"text", "json", "jsonl", "markdown"})


def offers_source(name: str) -> bool:
    """Whether this file can be shown as the text it is made of.

    Derived from what the format offers rather than listed a second time. The
    two used to be separate lists, and they drifted the moment `.log` was
    added: a log's first representation is text, and opening it answered
    "this file does not offer source editing" while its table worked.
    """
    return any(item.kind in SOURCE_KINDS for item in representations_of(name))


def is_container(name: str) -> bool:
    """Whether this file holds nodes of its own, rather than one document.

    Asked by the catalog before it says a file has children and by the id
    resolver before it reads what follows a file's id as a member.
    """
    return format_of(name) in {"workbook", "archive"}


# What can be read out of an archive entry: every viewer a bounded expansion
# can feed. Parquet and workbooks seek around their own bytes, media and PDF
# are streamed by range, and a nested archive would need a reader inside a
# reader — those entries are listed with no viewer at all (D53).
INSIDE_ARCHIVE: frozenset[str] = frozenset(
    {"table", "text", "json", "jsonl", "markdown", "image"}
)


def representations_inside_archive(name: str) -> list[NodeRepresentation]:
    """The representations of one entry, which are fewer than a file's."""
    return [
        item for item in representations_of(name) if item.kind in INSIDE_ARCHIVE
    ]
