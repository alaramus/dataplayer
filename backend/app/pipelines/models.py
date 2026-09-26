"""A pipeline: connections laid out on a canvas as cards of what was ticked
in them (D175), and links drawn between their rows (D176). Its runs are jobs
(D177), and nothing of them is kept here.

The body is read and written whole and never queried into, as a dashboard's
is (D129): one JSON column, validated on the way in and again on the way out.
A row that no longer validates is shown empty and marked broken rather than
refused, so one damaged row does not lock its owner out of the rest.
"""

import uuid
from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator
from pydantic import Field as PydanticField
from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, SQLModel

from app.adapters.catalog import NodeKind
from app.connectors.paste.models import Conflict, PasteColumn, PasteKindName
from app.core.schemas import get_datetime_utc

MAX_PIPELINES = 100
MAX_CARDS = 50
MAX_LINKS = 200
MAX_ROWS = 100
MAX_NAME = 120
MAX_LABEL = 255
# A node id is the source's own string; a file's is its path.
MAX_NODE_ID = 4096
MAX_TRAIL = 32
# Far beyond any canvas a person pans across, and short of a number that
# stops being one when it is drawn.
MAX_COORDINATE = 1_000_000.0


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CardRow(_Strict):
    """One ticked node, named as it was when it was ticked.

    No node id is the top of the connection: a place too, where a folder of
    personal storage has nothing above it to be ticked in.
    """

    node_id: str | None = PydanticField(default=None, min_length=1, max_length=MAX_NODE_ID)
    label: str = PydanticField(min_length=1, max_length=MAX_LABEL)
    kind: NodeKind | None = None
    # The names of the places above it, top first, so two tables of one name
    # in two schemas can be told apart on the card.
    trail: list[str] = PydanticField(default_factory=list, max_length=MAX_TRAIL)

    @model_validator(mode="after")
    def trail_is_names(self) -> Self:
        if any(len(step) > MAX_LABEL for step in self.trail):
            raise ValueError("A place above a node is named too long")
        return self


class Card(_Strict):
    """A connection on the canvas, and the rows ticked in it.

    It names nodes and does not hold them: what they are is asked of the
    source when the card is checked (D175).
    """

    id: uuid.UUID
    connector_id: uuid.UUID
    # The connection's name when it was dropped, for a card whose connection
    # has gone since and can no longer be asked.
    connector_name: str = PydanticField(min_length=1, max_length=MAX_LABEL)
    x: float = PydanticField(ge=-MAX_COORDINATE, le=MAX_COORDINATE)
    y: float = PydanticField(ge=-MAX_COORDINATE, le=MAX_COORDINATE)
    rows: list[CardRow] = PydanticField(min_length=1, max_length=MAX_ROWS)

    @model_validator(mode="after")
    def rows_are_distinct(self) -> Self:
        ids = [row.node_id for row in self.rows]
        if len(ids) != len(set(ids)):
            raise ValueError("A card holds the same node twice")
        return self


class LinkEnd(_Strict):
    """A row of a card, by the card and the node the row names."""

    card_id: uuid.UUID
    node_id: str | None = PydanticField(default=None, min_length=1, max_length=MAX_NODE_ID)


class Link(_Strict):
    """A paste from one row into another, with the choices it runs by (D176).

    The target row is both the place a kind puts something in and the table
    it writes into; each kind takes the one it understands, as the pair
    window's destination does (D167).
    """

    id: uuid.UUID
    source: LinkEnd
    target: LinkEnd
    kind: PasteKindName
    # The operation's title when it was chosen, for the line on the canvas;
    # what runs is the kind.
    title: str = PydanticField(min_length=1, max_length=MAX_LABEL)
    conflict: Conflict = "refuse"
    name: str | None = PydanticField(default=None, min_length=1, max_length=255)
    columns: list[PasteColumn] | None = PydanticField(default=None, max_length=100)


class PipelineContent(_Strict):
    cards: list[Card] = PydanticField(default_factory=list, max_length=MAX_CARDS)
    links: list[Link] = PydanticField(default_factory=list, max_length=MAX_LINKS)

    @model_validator(mode="after")
    def ids_are_unique(self) -> Self:
        cards = [card.id for card in self.cards]
        if len(cards) != len(set(cards)):
            raise ValueError("Two cards have the same id")
        links = [link.id for link in self.links]
        if len(links) != len(set(links)):
            raise ValueError("Two links have the same id")
        return self

    @model_validator(mode="after")
    def links_join_rows_of_two_connections(self) -> Self:
        cards = {card.id: card for card in self.cards}
        ends: set[tuple[uuid.UUID, str | None, uuid.UUID, str | None]] = set()
        for link in self.links:
            source = cards.get(link.source.card_id)
            target = cards.get(link.target.card_id)
            if source is None or target is None:
                raise ValueError("A link names a card that is not on the pipeline")
            if not _holds(source, link.source.node_id) or not _holds(target, link.target.node_id):
                raise ValueError("A link names a row its card does not hold")
            if link.source.node_id is None:
                raise ValueError("A link cannot start at the top of a connection")
            # Inside one connection is its catalog's own Paste (D74).
            if source.connector_id == target.connector_id:
                raise ValueError("A link joins two different connections")
            pair = (source.id, link.source.node_id, target.id, link.target.node_id)
            if pair in ends:
                raise ValueError("Two links join the same rows")
            ends.add(pair)
        return self

    def card(self, card_id: uuid.UUID) -> Card | None:
        return next((card for card in self.cards if card.id == card_id), None)

    def link(self, link_id: uuid.UUID) -> Link | None:
        return next((link for link in self.links if link.id == link_id), None)


def _holds(card: Card, node_id: str | None) -> bool:
    return any(row.node_id == node_id for row in card.rows)


class Pipeline(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True
    )
    name: str = Field(max_length=MAX_NAME)
    content: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    # Raised by every save. A save naming an older version is refused, so two
    # tabs editing one pipeline do not silently undo each other.
    version: int = Field(default=1)
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class PipelineCreate(_Strict):
    name: str = PydanticField(min_length=1, max_length=MAX_NAME)


class PipelineSave(PipelineContent):
    name: str = PydanticField(min_length=1, max_length=MAX_NAME)
    version: int = PydanticField(ge=1)


class PipelineSummary(BaseModel):
    """What the switcher lists: a pipeline by its name."""

    id: uuid.UUID
    name: str
    updated_at: datetime


class LinkPlace(BaseModel):
    """Where a link comes in a run, as the canvas numbers it (D177)."""

    link_id: uuid.UUID
    number: int
    # Why it goes first among links writing into each other, where it does.
    circle: str | None = None


class PipelinePublic(PipelineContent):
    id: uuid.UUID
    name: str
    version: int
    updated_at: datetime
    # The stored content could not be read and is shown empty.
    broken: bool = False
    order: list[LinkPlace] = PydanticField(default_factory=list)


class CardState(BaseModel):
    """What a card's connection says of it now.

    `problem` is why the connection could not be asked at all; `missing` the
    rows it answered do not exist. A source that cannot say where a node lives
    is not asked, and says so by `checked`.
    """

    problem: str | None = None
    missing: list[str] = PydanticField(default_factory=list)
    checked: bool = True


def summary(pipeline: Pipeline) -> PipelineSummary:
    return PipelineSummary(id=pipeline.id, name=pipeline.name, updated_at=pipeline.updated_at)


def content_of(pipeline: Pipeline) -> PipelineContent | None:
    try:
        return PipelineContent.model_validate(pipeline.content)
    except ValidationError:
        return None
