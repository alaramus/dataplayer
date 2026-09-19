"""A service this server started, as a row that outlives the job that made it.

The password a service runs with lives in the connector it becomes and nowhere
else (D4). The one exception is a password somebody typed themselves: it has
to survive the gap between the request and the job that starts the container,
so it is kept here encrypted under the same key the connector's secrets use,
and erased the moment the connector holds it.
"""

import re
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, SecretStr
from pydantic import Field as PydanticField
from sqlalchemy import JSON, Column, DateTime, LargeBinary
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

# What a service is for. A connection is a person's (D83); the metrics store
# belongs to the installation (D126), so it is in no person's list, counts
# against no person's ceiling and is reachable by no route of this module.
ServicePurpose = Literal["connection", "metrics_store"]


class ManagedService(SQLModel, table=True):
    """One container this installation is responsible for."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True
    )
    # The key of the template it was made from. Not a foreign key: templates
    # are code, and the row records which one rather than pointing at a table.
    template_key: str = Field(max_length=32)
    purpose: str = Field(default="connection", max_length=16, index=True)
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
    # from the machine stays reachable when it is started again. Everything
    # started from now on is, so this is what old rows are read by rather than
    # a question anybody is asked.
    publish: bool = Field(default=False)
    # Which port on the host somebody asked for, when they asked for one at
    # all. Null is the ordinary case and means the runtime picks; a number is
    # a person who will point something at it that already knows the port.
    requested_port: int | None = Field(default=None)
    # Whether it was asked to be filled with something to look at. A property
    # of the request rather than of the template, kept for the same reason.
    sample_data: bool = Field(default=False)
    # The credential slots the requester named themselves, as the template's
    # own field names. A JSON column and never a secret: a typed password goes
    # in the encrypted column below rather than in here, so nothing in this
    # one has to be treated as a secret at all (D4).
    chosen_credentials: dict[str, str] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    # Where this service's password comes from: made up here, typed by the
    # person who asked, or absent because they asked for a server that wants
    # none. A column rather than something inferred from the two below,
    # because "no password" and "the password has been handed over already"
    # would otherwise look the same.
    password_mode: str = Field(default="generated", max_length=16)
    # A password somebody typed, encrypted under the connector key, and only
    # until the connector exists. The job that starts the container needs it
    # after the request that carried it is over, and the alternative — a
    # secret in a job row, or in a process's memory across a restart — is
    # worse. `_save_connector` erases it, so a finished service has exactly
    # one home for its password again (D4).
    chosen_password: bytes | None = Field(
        default=None, sa_column=Column(LargeBinary, nullable=True)
    )
    # When the password was handed to its owner, if it ever was. A stamp
    # rather than a flag, because "when" is the useful answer and a flag is
    # derivable from it. Once, deliberately: it is handed over at the moment
    # the service becomes usable and is an encrypted secret of the connector
    # from then on, which is the only place a password lives (D4).
    credentials_shown_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    # When this service became a connection. Kept after the connector itself
    # is deleted, which is the whole reason it exists: `connector_id` going
    # null then looks exactly like a creation that never got that far, and a
    # running database would be offered a retry that would destroy it (D84).
    connected_at: datetime | None = Field(
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
    # Whether this service ever became a connection. With `connector_id` it
    # tells the two empty cases apart: one that never got that far, and one
    # whose connection its owner has since deleted. Only the first may be
    # started over; the second is a database somebody is still using (D84).
    was_connected: bool
    created_at: datetime
    job: JobPublic | None = None


# What a name in somebody's own database server may look like. Letters,
# digits and underscores, starting with a letter — the intersection of what
# PostgreSQL accepts unquoted and what survives being an environment variable
# in a container's specification, which is where these two values go.
NAME_PATTERN = r"^[A-Za-z][A-Za-z0-9_]{0,62}$"

# What a password somebody types may be made of: printable ASCII with no
# space in it. The same reasoning as the alphabet the server generates from,
# arrived at from the other side — this string becomes an environment
# variable in a container specification, an argument on a command line and
# part of a connection string, and a space or a control character survives
# none of those reliably. Eight characters because a database published on
# the machine is worth that much.
PASSWORD_PATTERN = r"[!-~]{8,128}"
# What to say when one does not fit, naming the rule and never the value.
UNUSABLE_PASSWORD = (
    "A password is 8 to 128 characters, with no spaces and nothing exotic in it"
)


def password_survives_where_it_goes(value: str) -> bool:
    """Whether a typed password can be everything it has to become.

    `fullmatch` rather than anchors, so that a trailing newline is not let
    through by `$` — the one character that would break an environment
    variable in a container specification without looking wrong in a form.
    """
    return re.fullmatch(PASSWORD_PATTERN, value) is not None


class GeneratedPassword(BaseModel):
    """Let the server make one up, which is what it does when nobody says.

    Carries nothing, deliberately: how a secret is made is one rule, and a
    request that could influence it is a request that could weaken it (D80).
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["generated"] = "generated"


class ChosenPassword(BaseModel):
    """This one, because the person asking will type it somewhere else.

    A `SecretStr`, so nothing prints it by accident on the way through — the
    same protection the connector's own fields have.

    Deliberately without a `pattern`: a constraint that fails puts the value
    it rejected into the validation error, and a 422 body echoing somebody's
    password is exactly what `SecretStr` is here to prevent. What a usable one
    looks like is checked where the other refusals about a password are made,
    and the answer names the rule rather than the value.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["chosen"] = "chosen"
    value: SecretStr


class NoPassword(BaseModel):
    """None at all, for a server where that is a real configuration.

    Refused for a template that has no unprotected shape: a PostgreSQL which
    trusts every connection is not something this server will start, and
    saying so is better than quietly making one up instead.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["none"] = "none"


class OwnKey(BaseModel):
    """No password: one of the requester's own SSH keys signs in (D154).

    Named by id, like a connection names one (D146): the private half never
    leaves the store, and the public half the server is told to trust is read
    out of it by the job that starts the server.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["key"] = "key"
    key_id: uuid.UUID


# How a service's password was decided, once the request is over. The shapes
# below, flattened to the word the row keeps and the screens read.
PasswordMode = Literal["generated", "chosen", "none", "key"]


PasswordChoice = Annotated[
    GeneratedPassword | ChosenPassword | NoPassword | OwnKey,
    PydanticField(discriminator="kind"),
]
"""How a service is signed into, as shapes rather than nullable fields. A
`password: str | None` plus a `no_password: bool` has a combination that
means nothing, and something would eventually have to decide what it meant."""


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

    Every field here is either a label in this application's own database, a
    name inside the server being started, or the one number about placement a
    person can have a reason to care about. Nothing else about the container
    is on this list — not the image, not the command, not a path, not a
    network — because none of that is a request's to choose (D80).

    Whether it is reachable from this machine is not asked any more: it always
    is, on the loopback address and nowhere else (D86). A service nobody can
    open in their own tools was a choice that only ever produced a service
    somebody then had to remake.
    """

    model_config = ConfigDict(extra="forbid")

    mode: Literal["chosen"] = "chosen"
    name: str = PydanticField(min_length=1, max_length=255)
    # The credential slots this template calls choosable. Which they are is
    # checked against the template, so a value for a slot it did not open is
    # refused rather than ignored.
    user: str | None = PydanticField(default=None, pattern=NAME_PATTERN)
    database: str | None = PydanticField(default=None, pattern=NAME_PATTERN)
    # Which port on the machine it answers on. Zero — the default — means the
    # runtime picks a free one, which is the right answer for anybody without
    # a reason to care; a number is somebody who will point a configuration
    # file at it. The container port is still the template's, and a port
    # already taken is a refusal from the runtime rather than a silent move.
    port: int = PydanticField(default=0, ge=0, le=65535)
    # How the password is decided. Three shapes, because "the one I typed" and
    # "none at all" are different requests rather than one field left empty.
    password: PasswordChoice = PydanticField(default_factory=GeneratedPassword)
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
    """How to reach a service from outside this application, whenever asked.

    Everything but the password. A service is used through the connection it
    became, and what a person needs from this window is the address and the
    names — which they can be told again tomorrow, so it is not a thing to
    ration. The password is not here because this answer has no end: it is
    handed over once, at the moment the service becomes usable, by the other
    route.

    Read off the service row and its template rather than out of the
    connector, so that a person who deleted the connection can still be told
    where the container they still have is listening.
    """

    host: str | None
    port: int | None
    user: str | None
    database: str | None
    # Which of the three ways this service's password was decided, so the
    # window can say whether there is one to remember at all.
    password_mode: PasswordMode
    # The same thing again as one line, which is what most tools take. Written
    # by the source type rather than assembled on the client: the grammar of
    # an address has one home, and a screen that joined the parts itself would
    # be a second implementation of it that differed in the quoting first. No
    # password in it, like every other address this application composes.
    url: str | None = None
    # Why there is no address, when there is none: a service that was started
    # without a port on the host is reachable by this server and by nothing
    # else.
    unreachable_reason: str | None = None


class RevealedCredentials(ServiceCredentials):
    """The same, with the password, given exactly once.

    A larger answer to a narrower question rather than a flag on the one
    above: which of the two a caller got is decided by which route it called,
    so nothing has to read a boolean to know whether it is holding a secret.

    Once, at the moment the service becomes usable — that is when a password
    nobody was asked for is worth saying out loud, and the window that says it
    warns before it does. Every later question about the service answers
    without it.
    """

    # Null for a service started without one, which is a real configuration
    # rather than a missing value: there is nothing to remember, and the
    # window says that instead of showing an empty box.
    password: str | None


class ServiceAccepted(BaseModel):
    """What comes back from asking for something to happen.

    Both halves: the service as it now stands, and the job that is doing the
    work. A request never waits for a pull, so the answer is what was accepted
    rather than what happened (D81).
    """

    service: ServicePublic
    job: JobPublic
