"""Work the server owns: what it is, how far it got, and how it ended.

A job is not a request that takes a long time. It is a row: it survives the
request that asked for it, the socket that watched it and the process that ran
it. Closing a tab does not stop one, and a restart does not lose one — it ends
it honestly as `interrupted` (D81).

The old application had none of this. `asyncio.create_task` started the work
and a dictionary in the process — `cache_activity[f'{id}.{user_id}']` — held a
single boolean about it, which a reload lost and a second worker never saw.
"""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.core.schemas import get_datetime_utc

# Every kind of work this application owns. One closed set, here, rather than
# a string a caller invents: a job whose kind nothing recognises is a job
# nothing will ever carry out.
#
# The names are data, so this package does not import the features that own
# them: what `service.create` *does* lives with services, and a later
# `backup.create` will live with backups.
JobKind = Literal[
    "service.create",
    "service.start",
    "service.stop",
    "service.restart",
    "service.delete",
    "backup.create",
    "backup.restore",
    # A reviewed action over a fixed set of source targets (D123).
    "source.operation",
    # The installation's TimescaleDB, started as a service (D126).
    "metrics.store.create",
    # Files or a table carried from one connection into another (D168).
    "paste.transfer",
    # Every link of a pipeline, one after another (D177).
    "pipeline.run",
    # Words looked for inside the files of chosen connections (S7). Its words
    # and matches are held in memory and never written here.
    "search.contents",
]

# The lifecycle, and no state outside it.
#
#   queued → running → succeeded
#                    ↘ failed
#                    ↘ cancelled     (somebody asked it to stop)
#                    ↘ interrupted   (the process went away mid-flight)
#
# There is no `cancelling`: a task stops at its next await, and what it had
# already done to the world is a question for whoever looks at the thing it
# was doing — a cancelled create is retried or removed, never resumed (D84).
JobState = Literal[
    "queued", "running", "succeeded", "failed", "cancelled", "interrupted"
]

TERMINAL: frozenset[str] = frozenset(
    {"succeeded", "failed", "cancelled", "interrupted"}
)


class Job(SQLModel, table=True):
    """One piece of owned work, from the moment it is accepted."""

    __table_args__ = (
        # Read as "mine, newest first", and as "everything about this thing".
        Index("ix_job_owner_created", "owner_id", "created_at"),
        Index("ix_job_subject_created", "subject_id", "created_at"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True
    )
    kind: str = Field(max_length=32, index=True)
    # What the job is about. No foreign key on purpose: a job is a fact about
    # something that happened, and the thing it happened to may be gone — a
    # delete job outlives the service it removed.
    subject_id: uuid.UUID | None = Field(default=None, index=True)
    # What the job was asked for, when a kind of work needs more than a
    # subject to know what to do — which backup to write back, say. Never a
    # secret: a job row is not encrypted, and the things a job needs to keep
    # secret it reads from the connector it is about.
    parameters: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    state: str = Field(default="queued", max_length=16, index=True)
    # Where it is now, in the words the handler declared. A name rather than a
    # percentage: nothing here knows how long a pull takes, and inventing a
    # number is how a progress bar comes to lie (D64 says the same about runs).
    step: str | None = Field(default=None, max_length=64)
    step_index: int = Field(default=0)
    step_count: int = Field(default=0)
    # One sentence for a person: what it did, or why it could not. Never
    # driver text — see D81.
    message: str | None = Field(default=None, max_length=512)
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    started_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    finished_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class JobPublic(BaseModel):
    """A job as its owner reads it.

    The authority on what happened, and the fallback for a client that missed
    a socket message — the same arrangement a query run has (D64).
    """

    id: uuid.UUID
    kind: JobKind
    subject_id: uuid.UUID | None
    parameters: dict[str, Any] | None
    state: JobState
    step: str | None
    step_index: int
    step_count: int
    message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class JobsPublic(BaseModel):
    data: list[JobPublic]
    count: int
    active_count: int


def public(job: Job) -> JobPublic:
    return JobPublic.model_validate(job, from_attributes=True)


def is_terminal(state: str) -> bool:
    return state in TERMINAL
