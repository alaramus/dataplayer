"""Bounded, content-native representations of a catalog node."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.adapters import jsontext

RepresentationKind = Literal[
    "table",
    "text",
    "json",
    "jsonl",
    "image",
    "markdown",
    "audio",
    "video",
    "pdf",
    "sql",
    "database",
]
ContentRepresentationKind = Literal[
    "text", "json", "jsonl", "image", "markdown", "audio", "video", "pdf", "sql", "database"
]
# The representations whose bytes a client reads through the ranged transport
# of D52 rather than holding whole.
StreamableRepresentationKind = Literal["audio", "video", "pdf"]
EditorValidationKind = Literal["json", "jsonl"]
ImageMediaType = Literal["image/png", "image/jpeg"]
# Closed sets, because each one is a promise about bytes the source verified.
AudioMediaType = Literal[
    "audio/mpeg", "audio/wav", "audio/ogg", "audio/mp4", "audio/flac"
]
VideoMediaType = Literal[
    "video/mp4", "video/webm", "video/ogg", "video/quicktime"
]


class NodeRepresentation(BaseModel):
    """One way a source says a node may be opened.

    The order in ``CatalogNode.representations`` matters: the first one is the
    source's preferred representation. ``kind`` is the viewer contract and
    ``title`` is the wording used when another representation is offered.
    """

    model_config = ConfigDict(extra="forbid")

    kind: RepresentationKind
    title: str = Field(min_length=1)


class ContentRequest(BaseModel):
    """One bounded content representation, distinct from tabular fetch."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    representation: ContentRepresentationKind
    # Used by record-oriented representations. A whole JSON document and a
    # text preview ignore paging because their own byte ceilings bound them.
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class EditorContentRequest(BaseModel):
    """Ask a source for the editable source of one content node."""

    model_config = ConfigDict(extra="forbid")

    node_id: str


class EditorContent(BaseModel):
    """A bounded source document and the version an update must still match."""

    model_config = ConfigDict(extra="forbid")

    text: str
    filename: str
    language_hint: str | None = None
    validation: EditorValidationKind | None = None
    version: str | None = None
    writable: bool
    truncated: bool = False
    reason: str | None = None


class UpdateContentRequest(BaseModel):
    """Replace one source document if its previously read version still exists."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    text: str
    version: str = Field(min_length=1)


class ContentUpdated(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str


class ContentConflict(Exception):
    """The source document no longer has the version the editor loaded."""


JsonScalarKind = Literal["null", "boolean", "number", "string"]


class JsonScalar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: JsonScalarKind
    # Numbers stay text so a JavaScript number never rounds an identifier.
    # Null alone has no value; strings, including an empty one, do.
    value: str | None

    @model_validator(mode="after")
    def value_matches_kind(self) -> JsonScalar:
        if self.kind == "null" and self.value is not None:
            raise ValueError("A JSON null cannot carry a value")
        if self.kind != "null" and self.value is None:
            raise ValueError("A JSON scalar must carry its value")
        return self


class JsonArray(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["array"] = "array"
    items: list[JsonValue]


class JsonObjectEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: JsonValue


class JsonObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["object"] = "object"
    entries: list[JsonObjectEntry]


JsonValue = Annotated[
    JsonScalar | JsonArray | JsonObject,
    Field(discriminator="kind"),
]


def json_tree(value: Any) -> JsonValue:
    """A value read by `jsontext.load` as the tree a JSON viewer draws."""
    if value is None:
        return JsonScalar(kind="null", value=None)
    if isinstance(value, jsontext.JsonNumber):
        return JsonScalar(kind="number", value=value.text)
    if isinstance(value, bool):
        return JsonScalar(kind="boolean", value="true" if value else "false")
    if isinstance(value, str):
        return JsonScalar(kind="string", value=value)
    if isinstance(value, list):
        return JsonArray(items=[json_tree(item) for item in value])
    if isinstance(value, dict):
        return JsonObject(
            entries=[
                JsonObjectEntry(name=name, value=json_tree(item))
                for name, item in value.items()
            ]
        )
    raise TypeError("Not a JSON value")


class TextContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["text"] = "text"
    text: str
    truncated: bool = False
    notice: str | None = None


class SqlContent(BaseModel):
    """A bounded, read-only SQL document issued by its source.

    It is not ``TextContent`` because ``text`` is the editable source-document
    contract of D48 in the current client. SQL shown here is a representation
    of another object and cannot honestly be saved back as that object's text.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["sql"] = "sql"
    text: str
    truncated: bool = False
    notice: str | None = None


class MarkdownContent(BaseModel):
    """The bounded source of a document that the browser renders itself.

    No HTML crosses this boundary: rendering, and every sanitising step it
    needs, happens in one place in the client. See D50.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["markdown"] = "markdown"
    text: str
    truncated: bool = False
    notice: str | None = None


class JsonContent(BaseModel):
    """A document tree, or its honest bounded source when parsing failed."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["json"] = "json"
    value: JsonValue | None = None
    source_text: str | None = None
    truncated: bool = False
    notice: str | None = None

    @model_validator(mode="after")
    def has_tree_or_source(self) -> JsonContent:
        if (self.value is None) == (self.source_text is None):
            raise ValueError("JSON content must carry either a value or source text")
        return self


class JsonLine(BaseModel):
    """One physical JSONL record, valid or named as invalid."""

    model_config = ConfigDict(extra="forbid")

    line_number: int = Field(ge=1)
    value: JsonValue | None = None
    source_text: str | None = None
    truncated: bool = False
    notice: str | None = None

    @model_validator(mode="after")
    def has_value_or_source(self) -> JsonLine:
        if (self.value is None) == (self.source_text is None):
            raise ValueError("A JSON line must carry either a value or source text")
        return self


class JsonLinesContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["jsonl"] = "jsonl"
    items: list[JsonLine]
    has_more: bool
    offset: int = Field(ge=0)


class ImageContent(BaseModel):
    """Verified facts about one bounded image preview."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["image"] = "image"
    filename: str = Field(min_length=1)
    media_type: ImageMediaType
    size_bytes: int = Field(ge=0)
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    # Minted by the transport after the source has verified the representation.
    # Optional inside the adapter boundary; the HTTP route always fills it.
    preview_url: str | None = None


class AudioContent(BaseModel):
    """Verified facts about one sound file, and where its bytes are read.

    What the container states and nothing more: a duration the header does not
    carry is absent rather than estimated, and whether this browser can play
    the codecs inside is the browser's answer (D52).
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["audio"] = "audio"
    filename: str = Field(min_length=1)
    media_type: AudioMediaType
    size_bytes: int = Field(ge=0)
    duration_seconds: float | None = Field(default=None, ge=0)
    channels: int | None = Field(default=None, ge=1)
    sample_rate: int | None = Field(default=None, ge=1)
    # Minted by the transport after the source has verified the container.
    stream_url: str | None = None


class VideoContent(BaseModel):
    """Verified facts about one recording, and where its bytes are read."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["video"] = "video"
    filename: str = Field(min_length=1)
    media_type: VideoMediaType
    size_bytes: int = Field(ge=0)
    duration_seconds: float | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    stream_url: str | None = None


class PdfContent(BaseModel):
    """A verified PDF, which the application draws rather than the browser."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["pdf"] = "pdf"
    filename: str = Field(min_length=1)
    media_type: Literal["application/pdf"] = "application/pdf"
    size_bytes: int = Field(ge=0)
    # As the header spells it, "1.7" or "2.0". A file that states none is not
    # a PDF this source serves.
    version: str = Field(min_length=1)
    stream_url: str | None = None


@dataclass(frozen=True)
class ContentStream:
    """Bytes a caller reads part of, after the source has verified them.

    Separate from `BoundedContentPreview`, which is bytes already held whole:
    a recording is asked for by range, and the range is decided by the
    transport once it knows the size — so the reader is a function of two
    offsets rather than one iterator (D52).
    """

    media_type: str
    filename: str
    size_bytes: int
    # Inclusive offsets, as HTTP names them.
    read: Callable[[int, int], AsyncIterator[bytes]]


@dataclass(frozen=True)
class BoundedContentPreview:
    """Verified bytes for one inline preview, already below its hard bound."""

    body: bytes
    media_type: ImageMediaType
    filename: str
    width: int
    height: int


class DatabaseRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    kind: Literal["table", "view", "virtual"]
    # What the database last counted, when it ever did; nothing counts rows.
    row_estimate: int | None = None


class DatabaseContent(BaseModel):
    """A database file seen from a file source: what it holds, not its rows (D262)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["database"] = "database"
    engine: str
    size_bytes: int
    relations: list[DatabaseRelation]
    # How many relations the file has; more than are listed when it was cut.
    total: int


# Who reads a database file a file source lists, by engine (D262). The
# engine's package registers its reader as it is imported, so a file source
# reaches a database driver without importing it: a driver stays inside the
# package that opens files with it.
DatabaseReader = Callable[[Path], DatabaseContent]
_DATABASE_READERS: dict[str, DatabaseReader] = {}


def register_database_reader(engine: str, reader: DatabaseReader) -> None:
    _DATABASE_READERS[engine] = reader


def database_reader(engine: str) -> DatabaseReader | None:
    return _DATABASE_READERS.get(engine)


ContentResult = Annotated[
    TextContent
    | SqlContent
    | MarkdownContent
    | JsonContent
    | JsonLinesContent
    | ImageContent
    | AudioContent
    | VideoContent
    | PdfContent
    | DatabaseContent,
    Field(discriminator="kind"),
]

# The results whose bytes arrive through the ranged route rather than in the
# answer itself. One tuple, so the route that mints a ticket and the test that
# checks every streamable representation cannot drift apart.
STREAMED_CONTENT = (AudioContent, VideoContent, PdfContent)


# Resolve the recursive aliases after every class participating in them exists.
JsonArray.model_rebuild()
JsonObjectEntry.model_rebuild()
JsonObject.model_rebuild()
