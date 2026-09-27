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
    SchemaEffect,
    StatementClass,
    StatementStatus,
)
from app.core.schemas import get_datetime_utc
from app.queries.snapshot import SnapshotView

# What one press of Run was aimed at. Ordinary Run takes one statement — the
# selection or the one under the caret — and never falls back to the whole
# document; running a script is the deliberately different command (D65).
ExecutionScope = Literal["statement", "script"]

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

# What has become of what a run changed. `none` is a read: it changed
# nothing, so there is nothing to say about it.
WriteState = Literal["none", "pending", "committed", "rolled_back"]


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
    # Names and shape, never values. A run is kept for as long as history is
    # kept, and a value somebody typed into a form — secret or not — is not
    # part of what happened, it is part of what was typed (D63).
    parameters: list[Any] = Field(
        default_factory=list, sa_column=Column(JSONB, nullable=False)
    )
    mode: str = Field(default="read", max_length=16)
    scope: str = Field(default="statement", max_length=16)
    write_state: str = Field(default="none", max_length=16)
    # Ending a transaction settles every run that went through it.
    transaction_id: str | None = Field(default=None, max_length=64, index=True)
    timeout_seconds: int = Field(default=30)
    status: str = Field(default="accepted", max_length=16, index=True)
    # What this run was asked to do, hashed. Two commands with one id must be
    # the same command; this is how that is decided without keeping the text
    # in the clear to compare it.
    fingerprint: str = Field(max_length=64)
    statement_count: int = Field(default=0)
    # What the source said its structure changes mean for what is on screen,
    # kept only once they are permanent. A manual run's effect belongs to the
    # transaction until somebody commits it, and a rollback issues none (D66).
    effect: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
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
    # What a change touched, as the source counted it (D66).
    affected_rows: int | None = Field(default=None)
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


class PrepareRequest(BaseModel):
    """Text to be read by the source, and nothing to be done with it."""

    model_config = ConfigDict(extra="forbid")

    connector_id: uuid.UUID
    text: str = PydanticField(max_length=MAX_TEXT_BYTES)


class RunParameter(BaseModel):
    """One binding a client supplies for this run.

    `secret` says the value is not to be remembered anywhere. It is not stored
    here in either case — a run keeps names and shape — and the flag travels so
    the console can say why a value it once had is not offered again.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = PydanticField(min_length=1, max_length=63)
    value: str | None = None
    secret: bool = False


class ParameterMetadata(BaseModel):
    """What a run remembers about a binding: everything except the value."""

    name: str
    is_null: bool
    secret: bool


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
    # The transaction this run belongs to, in manual mode and only there.
    transaction_id: str | None = PydanticField(default=None, max_length=64)
    # That the person has been told what a statement of this run would do
    # and said yes to it. Asked every time, never remembered (D66).
    confirm_high_risk: bool = False
    # A fresh acknowledgement for a write under the owner's confirm policy.
    confirm_write: bool = False
    scope: ExecutionScope = "statement"
    parameters: list[RunParameter] = PydanticField(default_factory=list)
    timeout_seconds: int | None = PydanticField(default=None, ge=1)


class StatementPublic(BaseModel):
    """One statement of a run, as the console reads it."""

    ordinal: int
    kind: StatementClass
    status: StatementStatus
    duration_ms: int | None = None
    command_tag: str | None = None
    row_count: int | None = None
    affected_rows: int | None = None
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
    scope: ExecutionScope
    # Where the changes of this run stand: nothing to say for a read,
    # pending while a manual transaction is open, settled once it ends.
    write_state: WriteState = "none"
    timeout_seconds: int
    statement_count: int
    parameters: list[ParameterMetadata] = PydanticField(default_factory=list)
    error: str | None = None
    # What the source says has to be re-read, once this run's structure changes
    # are permanent. Absent while they are pending and after a rollback (D66).
    effect: SchemaEffect | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    statements: list[StatementPublic] = PydanticField(default_factory=list)


class TransactionStart(BaseModel):
    """Asking for a transaction to be held open (D66)."""

    model_config = ConfigDict(extra="forbid")

    connector_id: uuid.UUID
    document_id: uuid.UUID | None = None
    timeout_seconds: int | None = PydanticField(default=None, ge=1)


class RehearsalStart(BaseModel):
    """What a console sends to have a change tried out and undone.

    The same text Run would take, so the rehearsal describes what would
    actually happen rather than a tidier statement nobody is about to run. In
    a transaction it is rehearsed inside that transaction, which is why the id
    travels with it (D66).
    """

    model_config = ConfigDict(extra="forbid")

    connector_id: uuid.UUID
    text: str = PydanticField(max_length=MAX_TEXT_BYTES)
    document_id: uuid.UUID | None = None
    transaction_id: str | None = PydanticField(default=None, max_length=64)
    parameters: list[RunParameter] = PydanticField(default_factory=list)
    timeout_seconds: int | None = PydanticField(default=None, ge=1)


class ExplainStart(BaseModel):
    """What a console sends to have one statement planned."""

    model_config = ConfigDict(extra="forbid")

    text: str = PydanticField(max_length=MAX_TEXT_BYTES)
    document_id: uuid.UUID | None = None
    parameters: list[RunParameter] = PydanticField(default_factory=list)
    timeout_seconds: int | None = PydanticField(default=None, ge=1)


class FormatRequest(BaseModel):
    """Text to lay out again, in the source's own dialect."""

    model_config = ConfigDict(extra="forbid")

    text: str = PydanticField(max_length=MAX_TEXT_BYTES)


class FormattedQuery(BaseModel):
    text: str


class RunText(BaseModel):
    """What one run executed, asked for on its own."""

    id: uuid.UUID
    text: str


class SnapshotPageRequest(BaseModel):
    """A window on a captured result, with what to show and in what order."""

    model_config = ConfigDict(extra="forbid")

    view: SnapshotView = PydanticField(default_factory=SnapshotView)
    offset: int = PydanticField(default=0, ge=0)
    limit: int = PydanticField(default=100, ge=1, le=500)


class SnapshotDownloadRequest(BaseModel):
    """What to save: the page on screen, or every captured row of this view."""

    model_config = ConfigDict(extra="forbid")

    scope: Literal["page", "all"] = "page"
    title: str = PydanticField(default="result", min_length=1, max_length=255)
    view: SnapshotView = PydanticField(default_factory=SnapshotView)
    offset: int = PydanticField(default=0, ge=0)
    limit: int = PydanticField(default=100, ge=1, le=500)
    # The ids of the columns on screen, in their order; every captured column
    # when absent.
    columns: list[str] | None = PydanticField(default=None, min_length=1)


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
