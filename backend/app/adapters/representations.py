"""The closed vocabulary for how a source opens a node."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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
    # A JSON value drawn as a tree, read only: a source's own description of
    # a node, where `json` is a file's text to edit (D295).
    "tree",
    # A relation's rows read as whole documents, a page at a time (D295).
    "documents",
    # A market's symbol watched live: price, chart, book and trades (D323).
    "market",
    # What a node's document means, as a page of blocks; declared before the
    # `tree` of the same document (D419).
    "view",
]
ContentRepresentationKind = Literal[
    "text", "json", "jsonl", "image", "markdown", "audio", "video", "pdf", "sql", "database", "tree", "view"
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

    The order in a node's representations matters: the first one is preferred.
    """

    model_config = ConfigDict(extra="forbid")

    kind: RepresentationKind
    title: str = Field(min_length=1)
