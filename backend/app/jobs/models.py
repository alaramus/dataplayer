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
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Index
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
]

# The lifecycle, and no state outside it.
#
#   queued → running → succeeded
#                    ↘ failed
#                    ↘ interrupted   (the process went away mid-flight)
#
# Cancellation is not here yet: stopping a pull halfway is a thing with its own
# semantics, and it arrives with retry and idempotency later in this phase.
JobState = Literal["queued", "running", "succeeded", "failed", "interrupted"]

TERMINAL: frozenset[str] = frozenset({"succeeded", "failed", "interrupted"})


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
    state: JobState
    step: str | None
    step_index: int
    step_count: int
    message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


def public(job: Job) -> JobPublic:
    return JobPublic.model_validate(job, from_attributes=True)


def is_terminal(state: str) -> bool:
    return state in TERMINAL
