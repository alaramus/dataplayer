"""What a kept list of names is, in the database and in the API (D212–D215).

Two tables of the search's own: `search_keep`, a connection's choice and the
state of its passes, and `search_name`, the names themselves. Rows of their
own rather than columns of the connector: the list is the search's, and a
connector knows nothing of it.
"""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Column, DateTime, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.core.schemas import get_datetime_utc

# How fresh a list must be, as the owner chooses it (D212).
KeepWindow = Literal[3600, 21600, 86400, 604800]
DEFAULT_WINDOW: KeepWindow = 86400

# How the last pass ended: everything read, part of it, or nothing usable.
PassOutcome = Literal["kept", "partial", "failed"]

# What a screen says of a connection's list.
KeepStatus = Literal["off", "waiting", "reading", "kept", "partial", "failed"]


def _moment(nullable: bool = True) -> Any:
    return Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=nullable),
    )


class SearchKeep(SQLModel, table=True):
    """A connection whose names are kept, and how its passes went.

    A row exists while the owner keeps the list; switching it off deletes the
    row and the names together (D212).
    """

    __tablename__ = "search_keep"

    connector_id: uuid.UUID = Field(
        foreign_key="connector.id", primary_key=True, ondelete="CASCADE"
    )
    window_seconds: int = Field(default=DEFAULT_WINDOW)
    changed_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    # Something in DataPlayer renamed what the list holds (D216).
    stale_at: datetime | None = _moment()
    # The owner asked for a pass now; the worker clears it when it takes it.
    refresh_asked_at: datetime | None = _moment()
    # The pass running or last run.
    pass_started_at: datetime | None = _moment()
    pass_ended_at: datetime | None = _moment()
    outcome: str | None = Field(default=None, max_length=16)
    # The end of the last pass that wrote the list, and when that pass began:
    # a change after the beginning is not in the list.
    kept_at: datetime | None = _moment()
    kept_started_at: datetime | None = _moment()
    # What that pass said when it stopped short; null when it read everything.
    kept_notice: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    names: int = Field(default=0)
    # Why the last pass stopped short or failed, in a sentence that is safe.
    notice: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    error_kind: str | None = Field(default=None, max_length=32)


class SearchName(SQLModel, table=True):
    """One name a connection holds, as the last pass read it (D213)."""

    __tablename__ = "search_name"
    __table_args__ = (
        Index(
            "ix_search_name_folded",
            "folded",
            postgresql_using="gin",
            postgresql_ops={"folded": "gin_trgm_ops"},
        ),
    )

    connector_id: uuid.UUID = Field(
        foreign_key="connector.id", primary_key=True, ondelete="CASCADE"
    )
    node_id: str = Field(sa_column=Column(Text, primary_key=True))
    parent_id: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    scope: str = Field(sa_column=Column(Text, nullable=False))
    # What the words are matched against, and the same folded by the rule.
    name: str = Field(sa_column=Column(Text, nullable=False))
    folded: str = Field(sa_column=Column(Text, nullable=False))
    kind: str = Field(max_length=32)
    location: str = Field(sa_column=Column(Text, nullable=False))
    node: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))
    ancestors: list[dict[str, Any]] | None = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    pass_id: uuid.UUID


class SearchContentScope(SQLModel, table=True):
    """A folder whose files' text is kept, or the whole connection (D217).

    Read by the pass that follows the names, so a scope exists only while the
    connection keeps its names.
    """

    __tablename__ = "search_content_scope"

    connector_id: uuid.UUID = Field(
        foreign_key="connector.id", primary_key=True, ondelete="CASCADE"
    )
    # The folder's node id; the empty string is the whole connection.
    node_id: str = Field(sa_column=Column(Text, primary_key=True))
    added_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    # The last contents pass over it.
    read_at: datetime | None = _moment()
    files: int = Field(default=0)
    # Files the rule does not read: binary, or larger than the storage's ceiling.
    unread: int = Field(default=0)
    notice: str | None = Field(default=None, sa_column=Column(Text, nullable=True))


class SearchContentFile(SQLModel, table=True):
    """One file whose text is kept, and what it was when it was read (D218)."""

    __tablename__ = "search_content_file"

    connector_id: uuid.UUID = Field(
        foreign_key="connector.id", primary_key=True, ondelete="CASCADE"
    )
    node_id: str = Field(sa_column=Column(Text, primary_key=True))
    # Its time and size as the names pass read them: unchanged, it is not read.
    version: str = Field(sa_column=Column(Text, nullable=False))
    # Of the bytes: changed time and the same text, the chunks are not rewritten.
    digest: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    # Not text by the rule: kept as a row so it is not read again unchanged.
    readable: bool = Field(default=True)


class SearchChunk(SQLModel, table=True):
    """A run of a file's lines, the unit the trigram index finds (D219)."""

    __tablename__ = "search_chunk"
    __table_args__ = (
        Index(
            "ix_search_chunk_folded",
            "folded",
            postgresql_using="gin",
            postgresql_ops={"folded": "gin_trgm_ops"},
        ),
    )

    connector_id: uuid.UUID = Field(
        foreign_key="connector.id", primary_key=True, ondelete="CASCADE"
    )
    node_id: str = Field(sa_column=Column(Text, primary_key=True))
    seq: int = Field(primary_key=True)
    # The number of its first line, counted from 1.
    line: int
    text: str = Field(sa_column=Column(Text, nullable=False))
    folded: str = Field(sa_column=Column(Text, nullable=False))


class ContentsScopeState(BaseModel):
    node_id: str
    files: int = 0
    unread: int = 0
    read_at: datetime | None = None
    notice: str | None = None


class ContentsAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The folder; absent or empty for the whole connection.
    node_id: str | None = None


class KeepState(BaseModel):
    """What a person is told of one connection's list."""

    connector_id: uuid.UUID
    name: str
    adapter_type: str
    # The owner's address when it is not the person's own.
    owner_email: str | None = None
    # Only the owner keeps or stops keeping a list (D212).
    may_change: bool
    # Whether this type can keep a list at all.
    available: bool
    status: KeepStatus
    window_seconds: KeepWindow = DEFAULT_WINDOW
    names: int = 0
    kept_at: datetime | None = None
    pass_started_at: datetime | None = None
    pass_ended_at: datetime | None = None
    refresh_asked: bool = False
    stale: bool = False
    notice: str | None = None
    error_kind: str | None = None
    # Whether this type can keep its files' text, and the folders that do (D217).
    contents_available: bool = False
    contents: list[ContentsScopeState] = []


class KeepOverview(BaseModel):
    """Every kept list the person can see, and which types can keep one."""

    lists: list[KeepState]
    types: list[str]


class KeepUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keep: bool
    window_seconds: KeepWindow = DEFAULT_WINDOW
