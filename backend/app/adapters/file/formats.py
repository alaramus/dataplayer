"""File formats and the representations each one offers."""

from pathlib import PurePosixPath
from typing import Literal

from app.adapters.content import NodeRepresentation

DELIMITED_EXTENSIONS: frozenset[str] = frozenset({".csv", ".tsv"})
JSON_EXTENSIONS: frozenset[str] = frozenset({".json"})
JSON_LINES_EXTENSIONS: frozenset[str] = frozenset({".jsonl", ".ndjson"})
IMAGE_EXTENSIONS: frozenset[str] = frozenset({".jpeg", ".jpg", ".png"})
MARKDOWN_EXTENSIONS: frozenset[str] = frozenset({".markdown", ".md"})

# Classification is intentionally by name in the catalog: inspecting every
# entry would cost one open per file. The content reader checks the bytes when
# that one node is actually opened.
BINARY_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".7z",
        ".avi",
        ".bin",
        ".bz2",
        ".class",
        ".dll",
        ".doc",
        ".docx",
        ".exe",
        ".gif",
        ".gz",
        ".ico",
        ".iso",
        ".jar",
        ".jpeg",
        ".jpg",
        ".mp3",
        ".mp4",
        ".odt",
        ".ogg",
        ".pdf",
        ".png",
        ".ppt",
        ".pptx",
        ".rar",
        ".so",
        ".tar",
        ".tgz",
        ".ttf",
        ".wav",
        ".webm",
        ".webp",
        ".woff",
        ".woff2",
        ".xls",
        ".xlsx",
        ".zip",
        ".zst",
    }
)

FileFormat = Literal[
    "delimited", "json", "jsonl", "text", "markdown", "image", "opaque"
]

TABLE = NodeRepresentation(kind="table", title="View as table")
TEXT = NodeRepresentation(kind="text", title="View as text")
JSON = NodeRepresentation(kind="json", title="View JSON")
JSON_LINES = NodeRepresentation(kind="jsonl", title="View JSON lines")
IMAGE = NodeRepresentation(kind="image", title="View image")
MARKDOWN = NodeRepresentation(kind="markdown", title="View as document")


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
        case "opaque":
            # Media representations are added on this same contract in the
            # next slice; claiming one before a safe content route exists
            # would turn a click into a promise the source cannot keep.
            return []
