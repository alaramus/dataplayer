"""A service this server started, as a row that outlives the job that made it.

What is deliberately not here: the password. A service's credentials live in
the connector the service becomes and nowhere else, so there is exactly one
encrypted home for them (D4) and no second copy to keep in step. A creation
that fails before the connector exists leaves nothing usable, and what happens
to the container it left behind is the job's business rather than a secret's.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel

from app.core.schemas import get_datetime_utc
from app.jobs.models import JobPublic

# Where a service is in its life. `creating` and `removing` are states of the
# thing rather than of the job that is doing it: a job ends, and the service
# it was making is still there or is not.
ServiceState = Literal["creating", "running", "stopped", "failed", "removing"]

# What a service may not be asked to do anything about: one is being made and
# one is being taken away, and a second command about either would be a race.
BUSY_STATES: frozenset[str] = frozenset({"creating", "removing"})


class ManagedService(SQLModel, table=True):
    """One container this installation is responsible for."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True
    )
    # The key of the template it was made from. Not a foreign key: templates
    # are code, and the row records which one rather than pointing at a table.
    template_key: str = Field(max_length=32)
    # Decided by the server when the service was planned, and kept because
    # every later command names the container rather than looking it up.
    container_name: str = Field(max_length=128)
    volume_name: str = Field(max_length=128)
    # Where it ended up. Both are absent until something places it there.
    published_port: int | None = Field(default=None)
    network: str | None = Field(default=None, max_length=128)
    state: str = Field(default="creating", max_length=16, index=True)
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class ServicePublic(BaseModel):
    """A service as its owner reads it.

    Carries its most recent job, so a screen that comes back after a reload
    knows what to watch without asking a second question.
    """

    id: uuid.UUID
    template_key: str
    # The template's own words, so no screen keeps a second name for a kind of
    # service.
    title: str
    state: ServiceState
    container_name: str
    published_port: int | None
    created_at: datetime
    job: JobPublic | None = None


class ServiceRequest(BaseModel):
    """Everything a client may say about a service it wants.

    One field. What runs is the template's (D80), and where it runs is the
    server's.
    """

    template_key: str


class ServiceAccepted(BaseModel):
    """What comes back from asking for something to happen.

    Both halves: the service as it now stands, and the job that is doing the
    work. A request never waits for a pull, so the answer is what was accepted
    rather than what happened (D81).
    """

    service: ServicePublic
    job: JobPublic
