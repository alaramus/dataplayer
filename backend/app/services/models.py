"""A service this server started, as a row that outlives the job that made it.

What is deliberately not here: the password. A service's credentials live in
the connector the service becomes and nowhere else, so there is exactly one
encrypted home for them (D4) and no second copy to keep in step. A creation
that fails before the connector exists leaves nothing usable, and what happens
to the container it left behind is the job's business rather than a secret's.
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydanticField
from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, SQLModel

from app.core.schemas import get_datetime_utc
from app.jobs.models import JobPublic

# What the runtime says about a service's container, plus the answer for a
# server that could not ask at all. Separate from `state`, which is what this
# application believes: the two disagreeing is exactly what a person needs to
# see.
ContainerReport = Literal["running", "stopped", "missing", "unknown"]

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
    # What the request that made it called itself, when it called itself
    # anything. A second request with the same id is the same request — a
    # double press, a retried POST — and answers with this row rather than
    # starting a second container (D84).
    request_id: uuid.UUID | None = Field(default=None, index=True)
    # What the connection to it is called. Settled when the service is asked
    # for, so that the name a person typed is theirs from the beginning and
    # the job has nothing to invent.
    connector_name: str = Field(max_length=255)
    # The connection this service became, once it is ready. Nulled rather than
    # cascaded: deleting the connector is not deleting the service, and a
    # service whose connector is gone is a thing somebody has to see.
    connector_id: uuid.UUID | None = Field(
        default=None, foreign_key="connector.id", ondelete="SET NULL", index=True
    )
    # Decided by the server when the service was planned, and kept because
    # every later command names the container rather than looking it up.
    container_name: str = Field(max_length=128)
    volume_name: str = Field(max_length=128)
    # Where it ended up. The port is absent until the container is running and
    # has been asked what the runtime gave it.
    published_port: int | None = Field(default=None)
    network: str | None = Field(default=None, max_length=128)
    # Whether it was asked for with a port on the host at all. Kept because
    # every later attempt is planned from this row: a service made reachable
    # from the machine stays reachable when it is started again.
    publish: bool = Field(default=False)
    # Whether it was asked to be filled with something to look at. A property
    # of the request rather than of the template, kept for the same reason.
    sample_data: bool = Field(default=False)
    # The credential slots the requester named themselves, as the template's
    # own field names. A JSON column and never a secret: `password` is not a
    # slot anybody may name, exactly so that nothing here has to be encrypted
    # (D4).
    chosen_credentials: dict[str, str] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    # When the password this server made up was shown to its owner, if it
    # ever was. A stamp rather than a flag, because "when" is the useful
    # answer and a flag is derivable from it. Shown once, deliberately: it is
    # in the connector as an encrypted secret from then on, which is the only
    # place a password lives (D4).
    credentials_shown_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
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
    # What the runtime says is actually there, when it was asked. `missing` is
    # a service whose container somebody removed by hand, and `unknown` is a
    # server that could not ask (D84).
    container_state: ContainerReport
    container_name: str
    # The port on the machine this server runs on, when it was published
    # there. Shown so a person can tell a service they can reach themselves
    # from one only this application can.
    published_port: int | None
    # The connection this service became. What a screen opens once the job has
    # succeeded, and empty until then.
    connector_id: uuid.UUID | None
    connector_name: str
    # Whether the password this server made up has already been shown. What
    # greys out the button that would show it: it is shown once, and a button
    # that would refuse is worse than no button (D82).
    credentials_shown: bool
    created_at: datetime
    job: JobPublic | None = None


# What a name in somebody's own database server may look like. Letters,
# digits and underscores, starting with a letter — the intersection of what
# PostgreSQL accepts unquoted and what survives being an environment variable
# in a container's specification, which is where these two values go.
NAME_PATTERN = r"^[A-Za-z][A-Za-z0-9_]{0,62}$"


class AutomaticStart(BaseModel):
    """Start it with everything decided here, and ask nothing.

    Carries no fields at all, deliberately: this is the demonstration path,
    where a person presses one button and receives a database with something
    in it. Even the name is made up, because a person who has not been asked
    for one has not got one in mind.
    """

    model_config = ConfigDict(extra="forbid")

    mode: Literal["automatic"] = "automatic"


class ChosenStart(BaseModel):
    """Start it the way the person asking said.

    Every field here is either a label in this application's own database or a
    name inside the server being started. Nothing about the container is on
    this list — not the image, not the command, not a path, not a port number
    — because none of that is a request's to choose (D80).

    The password is not here either. A chosen one would have to be written
    down between this request and the job that uses it, and the only encrypted
    home for a service's password is the connector it becomes (D4, D84); it is
    made up by the server and shown once instead.
    """

    model_config = ConfigDict(extra="forbid")

    mode: Literal["chosen"] = "chosen"
    name: str = PydanticField(min_length=1, max_length=255)
    # The credential slots this template calls choosable. Which they are is
    # checked against the template, so a value for a slot it did not open is
    # refused rather than ignored.
    user: str | None = PydanticField(default=None, pattern=NAME_PATTERN)
    database: str | None = PydanticField(default=None, pattern=NAME_PATTERN)
    # Whether the machine this server runs on may reach it too, on a port the
    # runtime picks and the loopback address only (D86).
    publish: bool = True
    # Whether to put something in it worth looking at.
    sample_data: bool = False


StartRequest = Annotated[AutomaticStart | ChosenStart, PydanticField(discriminator="mode")]
"""The two ways to ask for a service, as shapes rather than as optional fields.

A bag of nullable fields would make "automatic" a thing a client assembles by
leaving everything out, and would make every reader of it wonder what a half
filled one means. These are two shapes, and a request is one of them.
"""


class ServiceRequest(BaseModel):
    """Everything a client may say about a service it wants.

    The template names what will run (D80); the rest is how the person asking
    wants it set up, and the shape of that says which of the two ways they
    asked.
    """

    template_key: str
    # The client's own id for this request, so that pressing twice starts one
    # service. Chosen by the client for the same reason a run's id is (D64):
    # only the caller knows that two requests are the same intention.
    request_id: uuid.UUID | None = None
    start: StartRequest = PydanticField(default_factory=AutomaticStart)


class ServiceCredentials(BaseModel):
    """How to reach a service from outside this application, once.

    A service is used through the connection it became, and this application
    never needs these: they are here because a person who started a database
    may want to open it in their own tools, and the password was made up by
    the server rather than chosen by them.

    Shown once and then not again. It stays where every credential in this
    application stays — encrypted in the connector — and there is no second
    way to read it out.
    """

    host: str | None
    port: int | None
    user: str | None
    database: str | None
    password: str
    # Why there is no address, when there is none: a service that was started
    # without a port on the host is reachable by this server and by nothing
    # else.
    unreachable_reason: str | None = None


class ServiceAccepted(BaseModel):
    """What comes back from asking for something to happen.

    Both halves: the service as it now stands, and the job that is doing the
    work. A request never waits for a pull, so the answer is what was accepted
    rather than what happened (D81).
    """

    service: ServicePublic
    job: JobPublic
