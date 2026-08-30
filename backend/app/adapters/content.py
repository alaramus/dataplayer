"""Bounded, content-native representations of a catalog node."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


RepresentationKind = Literal["table", "text", "json", "jsonl"]
ContentRepresentationKind = Literal["text", "json", "jsonl"]


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


class TextContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["text"] = "text"
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


ContentResult = Annotated[
    TextContent | JsonContent | JsonLinesContent,
    Field(discriminator="kind"),
]


# Resolve the recursive aliases after every class participating in them exists.
JsonArray.model_rebuild()
JsonObjectEntry.model_rebuild()
JsonObject.model_rebuild()
