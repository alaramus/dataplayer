"""One press of Run, and what each of its statements did.

D63: a document changes and an execution does not. Everything here is written
once and then only completed — the text a run executed is the text it executed,
whatever the document has become since.
"""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydanticField
from sqlalchemy import Column, DateTime, Index, LargeBinary
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.adapters.query import (
    ExecutionMode,
    QueryDiagnostic,
    QueryNotice,
    ResultColumn,
    StatementClass,
    StatementStatus,
)
from app.core.schemas import get_datetime_utc

# The lifecycle, and no state outside it. `cancelling` is a state of its own
# because PostgreSQL cancellation can lose the race to completion: a run asked
# to stop stays here until the source says what actually happened (D64).
RunStatus = Literal[
    "accepted",
    "running",
    "cancelling",
    "cancelled",
    "succeeded",
    "failed",
    "timed_out",
    "interrupted",
]

TERMINAL: frozenset[str] = frozenset(
    {"cancelled", "succeeded", "failed", "timed_out", "interrupted"}
)

MAX_TEXT_BYTES = 256 * 1024


class ExecutionRun(SQLModel, table=True):
    """The snapshot of one execution.

    The id comes from the client, because starting a run is an idempotent
    command: pressing Run twice with the same id and the same payload is one
    run, and the same id with another payload is a conflict rather than a
    second execution nobody asked for (D64).
    """

    __table_args__ = (
        # History is read as "mine, newest first", and as "this document's".
        Index("ix_executionrun_owner_created", "owner_id", "created_at"),
    )

    id: uuid.UUID = Field(primary_key=True)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True
    )
    # Nulled rather than cascaded, like a document's: what ran is a fact, and
    # it outlives the connection it ran against.
    connector_id: uuid.UUID | None = Field(
        default=None, foreign_key="connector.id", ondelete="SET NULL", index=True
    )
    document_id: uuid.UUID | None = Field(
        default=None, foreign_key="querydocument.id", ondelete="SET NULL", index=True
    )
    document_revision: int | None = Field(default=None)
    # Encrypted under the query content key, like a document's body (D63).
    text: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    # Where in the document the executed text came from, so a later error can
    # point at it even when the document has moved on.
    range_start: int | None = Field(default=None)
    range_end: int | None = Field(default=None)
    search_path: list[str] = Field(
        default_factory=list, sa_column=Column(JSONB, nullable=False)
    )
    mode: str = Field(default="read", max_length=16)
    timeout_seconds: int = Field(default=30)
    status: str = Field(default="accepted", max_length=16, index=True)
    # What this run was asked to do, hashed. Two commands with one id must be
    # the same command; this is how that is decided without keeping the text
    # in the clear to compare it.
    fingerprint: str = Field(max_length=64)
    statement_count: int = Field(default=0)
    # A safe sentence when the run itself could not be carried out — the source
    # was unreachable, the context was refused. Statement failures live on the
    # statement.
    error: str | None = Field(default=None, max_length=500)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )
    started_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )
    finished_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )


class StatementRun(SQLModel, table=True):
    """The durable outcome of one statement of one run, in order."""

    run_id: uuid.UUID = Field(
        foreign_key="executionrun.id", primary_key=True, ondelete="CASCADE"
    )
    ordinal: int = Field(primary_key=True)
    kind: str = Field(max_length=16)
    status: str = Field(default="pending", max_length=16)
    duration_ms: int | None = Field(default=None)
    command_tag: str | None = Field(default=None, max_length=255)
    row_count: int | None = Field(default=None)
    # Into the process-local store, and only while it is still there. A result
    # does not survive a restart; the run that produced it does (D64).
    result_id: str | None = Field(default=None, max_length=64)
    truncated: bool = Field(default=False)
    diagnostic: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    notices: list[Any] = Field(
        default_factory=list, sa_column=Column(JSONB, nullable=False)
    )


class RunStart(BaseModel):
    """What a client sends to run something.

    The id is the client's, and so is the exact text: the caller has already
    decided whether this is a selection, the statement under the caret or a
    whole document, and the run keeps what it was given.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: uuid.UUID
    connector_id: uuid.UUID
    text: str = PydanticField(max_length=MAX_TEXT_BYTES)
    document_id: uuid.UUID | None = None
    document_revision: int | None = None
    range_start: int | None = PydanticField(default=None, ge=0)
    range_end: int | None = PydanticField(default=None, ge=0)
    mode: ExecutionMode = "read"
    timeout_seconds: int | None = PydanticField(default=None, ge=1)


class StatementPublic(BaseModel):
    """One statement of a run, as the console reads it."""

    ordinal: int
    kind: StatementClass
    status: StatementStatus
    duration_ms: int | None = None
    command_tag: str | None = None
    row_count: int | None = None
    result_id: str | None = None
    truncated: bool = False
    diagnostic: QueryDiagnostic | None = None
    notices: list[QueryNotice] = PydanticField(default_factory=list)


class RunPublic(BaseModel):
    """A run and everything durable about it.

    This is the authority on what happened. The socket says the same thing
    sooner, and a client that missed the message still reaches a terminal
    state by reading this (D64).
    """

    id: uuid.UUID
    connector_id: uuid.UUID | None
    document_id: uuid.UUID | None
    document_revision: int | None
    status: RunStatus
    mode: ExecutionMode
    timeout_seconds: int
    statement_count: int
    error: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    statements: list[StatementPublic] = PydanticField(default_factory=list)


class ResultPage(BaseModel):
    """A bounded window on one captured result.

    Paging reads the snapshot and never the source: the rows were read once,
    inside the transaction that produced them, and page two of a re-execution
    would be a different set of rows (D64).
    """

    result_id: str
    columns: list[ResultColumn]
    rows: list[list[str | None]]
    offset: int
    limit: int
    # Rows in the snapshot, which is not how many the statement would have
    # produced when `truncated` is true.
    total_rows: int
    truncated: bool
