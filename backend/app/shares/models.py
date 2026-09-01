"""The share record, the log of who opened it, and what the API says about both.

D58: none of this carries a right. A row here names a place in the application
and who made the address; whether the person holding it may read anything is
still a grant on the connection (D33).
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel
from pydantic import Field as PydanticField
from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.core.schemas import get_datetime_utc
from app.shares.view import SharedView

# 128 bits in base64url is 22 characters. The column is wider so that a longer
# token can be issued later without a migration.
TOKEN_BYTES = 16
MAX_NODE_ID = 1024
MAX_LABEL = 255


class Share(SQLModel, table=True):
    """One address: a connection, a node, and the view over it.

    The names of the connection and the node are copied in at creation, because
    the screen shown to a reader without a grant cannot ask the source what
    anything is called. They are as they were then, and the owner — who can
    read the source — sees the current ones.

    `view` is stored as JSON and validated through `SharedView` on the way in
    and on the way out. The column is storage; the boundary is the model.
    """

    __table_args__ = (
        # D59: the same view shared twice is the same record. Held by the
        # database and not only by the lookup before an insert, because two
        # windows of one person press the button at the same moment.
        UniqueConstraint("author_id", "fingerprint", name="uq_share_author_view"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    token: str = Field(max_length=64, unique=True, index=True)
    author_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True
    )
    connector_id: uuid.UUID = Field(
        foreign_key="connector.id", nullable=False, ondelete="CASCADE", index=True
    )
    node_id: str = Field(max_length=MAX_NODE_ID)
    connector_label: str = Field(max_length=MAX_LABEL)
    node_label: str = Field(max_length=MAX_LABEL)
    view: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))
    fingerprint: str = Field(max_length=64)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )


class ShareOpen(SQLModel, table=True):
    """That somebody opened a link, once per person.

    The question this answers is "did it reach them", so the author's own opens
    are not written: their own name in their own log is noise to filter out by
    eye every time.
    """

    share_id: uuid.UUID = Field(
        foreign_key="share.id", primary_key=True, ondelete="CASCADE"
    )
    user_id: uuid.UUID = Field(
        foreign_key="user.id", primary_key=True, ondelete="CASCADE"
    )
    opens: int = Field(default=1)
    first_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )
    last_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )


class ShareCreate(BaseModel):
    """Make an address for what the caller is looking at.

    The node's label comes from the client because it is what the catalog put
    on screen, and the server would have to walk the source to learn it. The
    connection's name is not accepted: the server has the row.
    """

    connector_id: uuid.UUID
    node_id: str = PydanticField(min_length=1, max_length=MAX_NODE_ID)
    node_label: str = PydanticField(min_length=1, max_length=MAX_LABEL)
    view: SharedView


class ShareOpener(BaseModel):
    """One person who opened a link, and how often."""

    user_id: uuid.UUID
    email: str
    full_name: str | None = None
    opens: int
    first_at: datetime | None = None
    last_at: datetime | None = None


class SharePublic(BaseModel):
    """A link as the person who may see it does.

    `can_delete` is the answer to "may I remove this from here", decided by the
    server: the author removes their own, the owner of the connection removes
    any made to it.

    The body of the view is not here. A list of links is a list of addresses;
    the body matters only when one is followed, and leaving it out means a body
    written by a future version cannot spoil the list it appears in.
    """

    id: uuid.UUID
    token: str
    connector_id: uuid.UUID
    connector_label: str
    node_id: str
    node_label: str
    created_at: datetime | None = None
    shared_by: str
    can_delete: bool
    openers: list[ShareOpener] = PydanticField(default_factory=list)


class SharesPublic(BaseModel):
    data: list[SharePublic]


class ShareTarget(BaseModel):
    """A resolved link the caller may follow."""

    state: Literal["open"] = "open"
    share_id: uuid.UUID
    connector_id: uuid.UUID
    connector_label: str
    node_id: str
    node_label: str
    view: SharedView
    shared_by: str


class ShareBarred(BaseModel):
    """A resolved link the caller has no standing for.

    D60: a normal outcome of this route, not an error. It names the connection
    on purpose — a deliberate deviation from D33's silence, argued in
    `docs/architecture/sharing.md` — because a request for access that cannot
    say what it is about is not answerable.
    """

    state: Literal["no_access"] = "no_access"
    connector_label: str
    node_label: str
    shared_by: str
    # Stage 2 fills this in from the access request; until then a reader is
    # told what they are looking at and who to ask.
    requested: bool = False


ShareResolved = Annotated[
    ShareTarget | ShareBarred,
    PydanticField(discriminator="state"),
]
