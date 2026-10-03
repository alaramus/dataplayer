"""What the search is asked, and the lines it answers with (D197–D203).

The contract is the same in every phase: a later phase adds a way to answer a
cell, never a field here that an earlier answer lacked (D203).
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.adapters.catalog import CatalogNode, NodeView
from app.adapters.errors import ErrorKind
from app.adapters.search import (
    MAX_QUERY_LENGTH,
    MAX_WORDS,
    Ancestor,
    MatchClass,
    SearchedField,
    words_of,
)
from app.core.access import Access

# Typing asks what is cheap and near; Search — Enter, or the Search tab — asks
# everything a mode may spend (D200). Looking inside files is neither: it is a
# job (S7).
SearchMode = Literal["typing", "search"]

# What a cell matches in its place, a closed set: the one a source is asked
# for, so the two cannot drift apart.
SearchField = SearchedField

# How a cell is answered: asked now, read from what was kept, or not at all.
Way = Literal["live", "kept", "none"]

# What answering a cell costs, stated without asking anybody (D200).
Cost = Literal["instant", "cheap", "costly", "job"]

# Where a request comes from. One answer is in flight per person and lane: a
# newer one from the field cancels the older, while the Search tab, a gesture
# in it and the type catalog each keep their own (D200).
Lane = Literal["field", "tab", "follow", "types"]

# The kinds of thing the application keeps that the search finds by asking
# itself. One provider each, except conversations, which answer for the three
# kinds of chat.
ProviderKey = Literal[
    "saved_queries",
    "pipelines",
    "dashboards",
    "conversations",
    "services",
    "ssh_keys",
    "guide",
    "source_types",
    "open_tabs",
    "recent",
]

# What a found application object is. Closed, so an intent nothing opens
# cannot be sent.
ObjectType = Literal[
    "saved_query",
    "pipeline",
    "dashboard",
    "conversation",
    "quick_chat",
    "project",
    "service",
    "ssh_key",
    "guide_page",
    "source_type",
    "tab",
    "tab_group",
]

# Why a cell was not asked, in a closed set the screen words (D201).
SkipReason = Literal[
    "switched_off",
    "cannot_search",
    "unreachable",
    "too_costly",
    "not_in_context",
    "not_asked",
]

# What a hit matched: its name, a detail beside the name (a connection's host),
# a body (a guide page's text), the contents of a file, or a relation's columns.
MatchedField = Literal["name", "details", "body", "contents", "columns"]

MIN_WORD_CHARACTERS = 2
MAX_CONTEXT = 8
MAX_RECENT = 50
MAX_BROWSER_PLACES = 200
# A node id is the source's own string; a file's is its path.
MAX_NODE_ID = 4096
MAX_OBJECT_ID = 500
MAX_NODE_KIND = 64
# A Redis key is a name too, and may be long.
MAX_NODE_NAME = 1000


def _cut(limit: int) -> BeforeValidator:
    """Text the browser shows, cut to `limit` rather than refused: one long
    name must not refuse the whole search it travels in."""
    return BeforeValidator(
        lambda value: value[:limit] if isinstance(value, str) else value
    )


class _Strict(BaseModel):
    # What the server writes always has every field, so the client's types
    # say so: a line's `type` is a discriminator, never an optional one.
    model_config = ConfigDict(
        extra="forbid", json_schema_serialization_defaults_required=True
    )


# --- places and cells --------------------------------------------------------


class ConnectionsPlace(_Strict):
    """The connections themselves, as rows: found by name, type and host."""

    kind: Literal["connections"] = "connections"


class ConnectionPlace(_Strict):
    """One connection, or a level of one: what is inside it."""

    kind: Literal["connection"] = "connection"
    connector_id: uuid.UUID
    # The level a scope starts from; the root when absent.
    node_id: str | None = None


class ObjectsPlace(_Strict):
    """One kind of thing the application keeps."""

    kind: Literal["objects"] = "objects"
    provider: ProviderKey


Place = Annotated[
    ConnectionsPlace | ConnectionPlace | ObjectsPlace, Field(discriminator="kind")
]


class Cell(_Strict):
    """A place and a field: what a way is chosen for and an outcome reported."""

    place: Place
    field: SearchField


def cell_key(cell: Cell) -> str:
    """One string per cell, the same on every line that talks about it."""
    place = cell.place
    if isinstance(place, ConnectionsPlace):
        where = "connections"
    elif isinstance(place, ConnectionPlace):
        where = f"connection:{place.connector_id}"
        if place.node_id is not None:
            where += f":{place.node_id}"
    else:
        where = f"objects:{place.provider}"
    return f"{where}/{cell.field}"


# --- the request -------------------------------------------------------------


class RecentTarget(_Strict):
    """Something the person last opened from the search, as the browser kept it.

    A hint, never a grant: the server names it again only through the same
    visibility the search itself uses (D199).
    """

    kind: Literal["connection", "node", "object"]
    connector_id: uuid.UUID | None = None
    node_id: str | None = Field(default=None, max_length=MAX_NODE_ID)
    # A node's name and kind as they were when it was opened: the server
    # cannot have them without asking the node's source.
    name: Annotated[str | None, _cut(MAX_NODE_NAME)] = None
    node_kind: str | None = Field(default=None, max_length=MAX_NODE_KIND)
    object_type: ObjectType | None = None
    object_id: str | None = Field(default=None, max_length=MAX_OBJECT_ID)


class BrowserPlace(_Strict):
    """An open tab or a saved tab group: only the browser knows them (S9)."""

    object_type: Literal["tab", "tab_group"]
    object_id: str = Field(max_length=MAX_OBJECT_ID)
    # A panel's title is its node's name, and its detail a connection and a
    # location in it.
    title: Annotated[str, _cut(MAX_NODE_NAME)]
    detail: Annotated[str | None, _cut(MAX_NODE_ID)] = None


class SearchRequest(_Strict):
    """What a person typed, where they are, and what this answer may spend."""

    words: str = Field(max_length=MAX_QUERY_LENGTH)
    mode: SearchMode
    lane: Lane = "field"
    # The connections whose panels are open, the current one first (D200).
    context: list[uuid.UUID] = Field(default_factory=list, max_length=MAX_CONTEXT)
    # Ask only these places. A scope (D205), a gesture on one outcome ("Try
    # again", "Search only this connection"), or the type catalog asking its
    # one provider.
    only: list[Place] | None = Field(default=None, max_length=MAX_CONTEXT)
    # Ask the places named in `only` whatever their health, backoff or the
    # ceiling on connections says: "Search anyway", "Search these too". Never
    # past what the mode may spend: typing asks nothing costly (D200, D204).
    insist: bool = False
    # What was opened from the search lately, newest first (S6).
    recent: list[RecentTarget] = Field(default_factory=list, max_length=MAX_RECENT)
    # Open tabs and saved tab groups (S9).
    browser: list[BrowserPlace] = Field(
        default_factory=list, max_length=MAX_BROWSER_PLACES
    )

    @field_validator("words")
    @classmethod
    def _words(cls, value: str) -> str:
        stripped = value.strip()
        # Nothing at all is an empty search, which `_something_asked` admits
        # only with what was opened lately.
        if stripped and len(stripped) < MIN_WORD_CHARACTERS:
            raise ValueError(
                f"A search needs at least {MIN_WORD_CHARACTERS} characters"
            )
        if len(words_of(stripped)) > MAX_WORDS:
            raise ValueError(f"A search takes at most {MAX_WORDS} words")
        return stripped

    @model_validator(mode="after")
    def _something_asked(self) -> Self:
        """An empty search lists what was opened lately, and nothing else (S6)."""
        if not self.words and not self.recent:
            raise ValueError(
                f"A search needs at least {MIN_WORD_CHARACTERS} characters"
            )
        return self


# --- a hit -------------------------------------------------------------------


class Segment(_Strict):
    """A run of text, marked when it is what matched.

    Text rather than offsets: a Python offset counts code points and a
    JavaScript one UTF-16 units, so an offset would mark the wrong letters
    after an emoji (D198).
    """

    text: str
    hit: bool = False


class ConnectionTarget(_Strict):
    kind: Literal["connection"] = "connection"
    connector_id: uuid.UUID


class NodeTarget(_Strict):
    """A node, as a pointer: enough to open it, never the thing itself (D198)."""

    kind: Literal["node"] = "node"
    connector_id: uuid.UUID
    node_id: str
    parent_id: str | None = None
    # Where it is, in the source's own words.
    location: str = ""
    name: str
    node_kind: str
    # Always empty in this plan; where a row would go one day.
    sub_key: str | None = None
    # The path from the root, for a source with no node path (a Redis key).
    ancestors: list[Ancestor] | None = None
    # The node as its listing builds it. Live always fills it.
    node: CatalogNode | None = None


class ObjectTarget(_Strict):
    kind: Literal["object"] = "object"
    object_type: ObjectType
    object_id: str


Target = Annotated[
    ConnectionTarget | NodeTarget | ObjectTarget, Field(discriminator="kind")
]


def target_key(target: ConnectionTarget | NodeTarget | ObjectTarget) -> str:
    """One string per thing found, so a thing found twice is one hit (D198)."""
    if isinstance(target, ConnectionTarget):
        return f"connection:{target.connector_id}"
    if isinstance(target, NodeTarget):
        return f"node:{target.connector_id}:{target.node_id}:{target.sub_key or ''}"
    return f"object:{target.object_type}:{target.object_id}"


def recent_target(
    recent: RecentTarget,
) -> ConnectionTarget | NodeTarget | ObjectTarget | None:
    """What the browser kept, as the target it was found as; None when not whole.

    One way from a kept target to a key, so recency orders by `target_key`
    exactly as the hits are keyed (D202).
    """
    if recent.kind == "connection" and recent.connector_id is not None:
        return ConnectionTarget(connector_id=recent.connector_id)
    if (
        recent.kind == "node"
        and recent.connector_id is not None
        and recent.node_id is not None
    ):
        return NodeTarget(
            connector_id=recent.connector_id,
            node_id=recent.node_id,
            name=recent.name or recent.node_id,
            node_kind=recent.node_kind or "node",
        )
    if (
        recent.kind == "object"
        and recent.object_type is not None
        and recent.object_id is not None
    ):
        return ObjectTarget(object_type=recent.object_type, object_id=recent.object_id)
    return None


class Facts(_Strict):
    """What the Search tab filters and sorts by, where the place knows it."""

    # The kind of thing: a source type for a connection, a node kind, an
    # object type.
    kind: str
    # When the thing itself last changed.
    changed_at: datetime | None = None
    # Whose it is, when it is not the person's.
    owner: str | None = None
    # A connection switched off is found by its name and never asked (D20).
    switched_off: bool = False


class Match(_Strict):
    field: MatchedField
    match_class: MatchClass
    # Where inside the thing, for a viewer to open at: a line of a file.
    line: int | None = None
    excerpt: list[Segment] = Field(default_factory=list)


# How a found thing opens: a node in one of its views, a connection's catalog
# or its window, and one intent per kind of application object (D205).
OpenIntent = NodeView | Literal["connection"] | ObjectType


class Hit(_Strict):
    key: str
    target: Target
    title: str
    detail: str | None = None
    facts: Facts
    match: Match
    # The person's level where the thing has levels. It decides nothing (D199).
    access: Access | None = None
    open: OpenIntent
    via: Way = "live"
    as_of: datetime | None = None


# --- outcomes and lines ------------------------------------------------------


class Outcome(_Strict):
    """What happened to one cell in this answer (D201)."""

    way: Way
    status: Literal["complete", "stopped", "late", "failed", "skipped"]
    reason: SkipReason | None = None
    # The source's own words about why it stopped (D76).
    notice: str | None = None
    # A failure, reduced: its kind and a safe sentence, never driver text.
    error_kind: ErrorKind | None = None
    message: str | None = None
    # Whether asking this cell alone would find more.
    more: bool = False
    # When what answered was read; absent means now.
    as_of: datetime | None = None
    # How long it was given, for "Didn't answer in 2 s".
    deadline_seconds: float | None = None
    # Since when it has been unreachable, for "Can't be reached since 14:02".
    since: datetime | None = None
    # The person owns the connection, so a locked key may be unlocked here.
    owned: bool = False


class Group(_Strict):
    """Where a cell's hits are drawn. Ordered by `rank`, which is fixed (D202)."""

    key: str
    title: str
    rank: int


class PlannedCell(_Strict):
    key: str
    cell: Cell
    group: Group
    cost: Cost
    way: Way
    # The connection a cell asks, for the screen's gestures.
    connector_id: uuid.UUID | None = None


class PlanLine(_Strict):
    """First: every cell of this answer, so a screen can say what is pending."""

    type: Literal["plan"] = "plan"
    mode: SearchMode
    cells: list[PlannedCell]


class CellLine(_Strict):
    """One cell, finished: its outcome and what it found."""

    type: Literal["cell"] = "cell"
    key: str
    outcome: Outcome
    hits: list[Hit] = Field(default_factory=list)


class BestLine(_Strict):
    """The best name matches of the cheap cells, once, never reordered (D202)."""

    type: Literal["best"] = "best"
    hits: list[Hit]


class EndLine(_Strict):
    type: Literal["end"] = "end"
    # Every cell asked was complete and nothing was found.
    nothing_found: bool = False
    # How many cells were asked, for "Nothing found in all 12 places".
    asked: int = 0
    # A newer answer took this one's place.
    superseded: bool = False


SearchLine = Annotated[
    PlanLine | CellLine | BestLine | EndLine, Field(discriminator="type")
]
