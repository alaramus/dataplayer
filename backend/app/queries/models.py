"""A query document, and what the API says about one.

D63: a console is one object in two stages rather than a scratch type and a
saved type. It is created as an unnamed draft, naming it changes only its
title, and what a user has written is encrypted at rest under a key of its own.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints
from pydantic import Field as PydanticField
from sqlalchemy import Column, DateTime, Index, LargeBinary
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.core.config import settings
from app.core.schemas import get_datetime_utc

MAX_TITLE = 255
# PostgreSQL truncates an identifier at 63 bytes, and a schema this side has
# never heard of is refused at execution time anyway (D63).
MAX_SCHEMA_NAME = 63
MAX_SEARCH_PATH = 32

SchemaName = Annotated[str, StringConstraints(min_length=1, max_length=MAX_SCHEMA_NAME)]
SearchPath = Annotated[list[SchemaName], PydanticField(max_length=MAX_SEARCH_PATH)]
DocumentTitle = Annotated[str, StringConstraints(max_length=MAX_TITLE)]

# How much of the body a list of documents shows. Long enough to recognise a
# draft nobody has named, short enough that a library is not a way to read
# everything at once.
PREVIEW_CHARS = 120


class EditorLayout(BaseModel):
    """Where the split sits and whether lines wrap, for one document (D65).

    Typed rather than an open dictionary, and stored as JSON: the column is
    storage and this model is the boundary, as in `Share.view`.
    """

    model_config = ConfigDict(extra="forbid")

    split_ratio: float = PydanticField(default=0.6, ge=0.1, le=0.9)
    wrap: bool = False


class QueryDocument(SQLModel, table=True):
    """One console, owned by one user and bound to one connection.

    The connection is nulled rather than cascaded when it goes: D63 says a
    document survives losing its context. What it loses is the ability to run,
    which is decided where running is, not here.

    `revision` is the whole conflict story. Autosave sends the revision it
    started from, and a write whose base does not match is refused rather than
    resolved by arrival order.
    """

    __table_args__ = (
        # The library is read as "mine, newest first", filtered by connection.
        Index("ix_querydocument_owner_updated", "owner_id", "updated_at"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True
    )
    connector_id: uuid.UUID | None = Field(
        default=None, foreign_key="connector.id", ondelete="SET NULL", index=True
    )
    # Plaintext on purpose: a title is how a person finds a document, and
    # D63 keeps operational metadata readable. The body is not.
    title: str | None = Field(default=None, max_length=MAX_TITLE)
    body: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    revision: int = Field(default=1)
    search_path: list[str] = Field(
        default_factory=list, sa_column=Column(JSONB, nullable=False)
    )
    layout: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False)
    )
    # Values this document was told to remember, encrypted like its body. Only
    # the ones a person chose to keep, and never one they marked secret: a
    # secret value is used and forgotten (D63).
    parameters: bytes | None = Field(
        default=None, sa_column=Column(LargeBinary, nullable=True)
    )
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )
    updated_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )
    # When it went to Trash. Thirty days later the sweep removes it for good.
    trashed_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        index=True,
    )


def _within_size(value: str) -> str:
    """D64's ceiling on one document, counted in bytes rather than characters.

    A megabyte of text is a megabyte whatever alphabet it is in, and a length
    in characters would let one script through and refuse another.
    """
    if len(value.encode()) > settings.QUERY_DOCUMENT_MAX_BYTES:
        raise ValueError(
            f"A document is at most {settings.QUERY_DOCUMENT_MAX_BYTES} bytes"
        )
    return value


DocumentBody = Annotated[str, AfterValidator(_within_size)]


# One remembered binding per name, or a null the author meant.
RememberedParameters = dict[str, str | None]


class QueryDocumentCreate(BaseModel):
    """A new console, or a copy of one whose owner chose to keep both.

    The connection is required: a document is developed against a source, and
    one that names none could not offer a schema context or a Run at all.
    """

    connector_id: uuid.UUID
    title: DocumentTitle | None = None
    body: DocumentBody = ""
    search_path: SearchPath = PydanticField(default_factory=list)
    layout: EditorLayout = PydanticField(default_factory=EditorLayout)
    parameters: RememberedParameters = PydanticField(default_factory=dict)


class QueryDocumentUpdate(BaseModel):
    """One autosave, or one deliberate change of title or context.

    `revision` is the revision this change was made on top of, and it is
    required: a save that does not say what it changed cannot be checked, and
    the last writer would win in silence.

    Every other field is optional and absent means unchanged, so the editor
    saves a body without restating the layout. Absent and null are different
    answers, told apart by the fields the caller actually set: a title sent as
    null takes the name off a document and makes it a draft again.
    """

    revision: int
    title: DocumentTitle | None = None
    body: DocumentBody | None = None
    search_path: SearchPath | None = None
    layout: EditorLayout | None = None
    parameters: RememberedParameters | None = None


class QueryDocumentPublic(BaseModel):
    """A document as its owner reads it, body and all."""

    id: uuid.UUID
    connector_id: uuid.UUID | None
    # The name of the connection, or nothing when it was deleted or is no
    # longer granted. Null is the whole statement that the context is
    # unavailable — there is no second flag saying the same thing (D63).
    connector_label: str | None
    title: str | None
    body: str
    revision: int
    search_path: list[str]
    layout: EditorLayout
    # What this document remembers being asked with. Empty is the ordinary
    # state, and a value marked secret when it ran is never here.
    parameters: RememberedParameters = PydanticField(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    trashed_at: datetime | None = None


class QueryDocumentSummary(BaseModel):
    """A document as a library lists it.

    The body is not here; a preview of its first line is, because most
    documents are drafts nobody has named and a list of "Untitled" is not
    navigation. The preview is built per response and never stored.
    """

    id: uuid.UUID
    connector_id: uuid.UUID | None
    connector_label: str | None
    title: str | None
    preview: str
    revision: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
    trashed_at: datetime | None = None


class QueryDocumentsPublic(BaseModel):
    data: list[QueryDocumentSummary]
    count: int
