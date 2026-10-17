"""References the application keeps, between columns no source calls related.

D106: a declared reference is a row of the application's own with two ends,
and an end is a connection, a node in it and one of that node's columns.
Neither source is changed by drawing one, and neither end is the key: the
answer to following it — the rows where the far column equals this value — is
the same statement read from either side.

It lives in `connectors` rather than in an adapter for the reason D43 gives:
an adapter knows itself and nothing else, and a reference between two
connections is not a thing either of them can answer.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic import Field as Constrained
from sqlalchemy import DateTime, Index, UniqueConstraint, and_, or_
from sqlmodel import Field, SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.catalog import CatalogNode
from app.adapters.fetch import FetchColumn, FetchReference, FetchRequest, ScalarFilter
from app.adapters.protocol import SupportsFetch, SupportsNodePath
from app.adapters.references import (
    FollowReferenceRequest,
    NoReferencedRows,
    ReferenceConnection,
    ReferencedRows,
    ReferenceTarget,
)
from app.adapters.resources import ResourceStore
from app.connectors import crud
from app.connectors.access import get_or_404, resolve_source
from app.connectors.models import Connector
from app.core.schemas import get_datetime_utc
from app.core.translation import say
from app.users.models import User

# Which end of a reference something is. Not a direction and not a role: the
# letters exist so that a node referenced to itself still offers two distinct
# ways out, and swapping them changes nothing but which one is being stood on.
End = Literal["a", "b"]
ENDS: tuple[End, End] = ("a", "b")

# The names this module issues, and no adapter can. A follow route recognising
# one is doing a lookup rather than guessing whose reference it is.
NAME_PREFIX = "declared:"

MAX_NODE_ID = 1024
MAX_LABEL = 255
MAX_COLUMN = 255


class DeclaredReference(SQLModel, table=True):
    """One line somebody drew, kept for as long as both ends exist.

    Both connections are foreign keys with a cascade: a reference to a
    connection that has been deleted is not a reference to anything, and
    leaving the row would leave an arrow pointing at an id.
    """

    __table_args__ = (
        # D106: the same pair drawn twice is the same row. Held by the database
        # and not only by the lookup before the insert, because two windows of
        # one person can press the button at the same moment.
        UniqueConstraint(
            "author_id", "fingerprint", name="uq_declaredreference_author_pair"
        ),
        # Both ends are looked up on every page of either node.
        Index("ix_declaredreference_a", "author_id", "a_connector_id", "a_node_id"),
        Index("ix_declaredreference_b", "author_id", "b_connector_id", "b_node_id"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    author_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True
    )
    a_connector_id: uuid.UUID = Field(
        foreign_key="connector.id", nullable=False, ondelete="CASCADE"
    )
    a_node_id: str = Field(max_length=MAX_NODE_ID)
    a_column: str = Field(max_length=MAX_COLUMN)
    # The node's own label as it was when the reference was made, copied in for
    # the reason a share copies one (D58): naming a node means asking its
    # source, and a tooltip cannot afford a catalog read per page.
    a_label: str = Field(max_length=MAX_LABEL)
    b_connector_id: uuid.UUID = Field(
        foreign_key="connector.id", nullable=False, ondelete="CASCADE"
    )
    b_node_id: str = Field(max_length=MAX_NODE_ID)
    b_column: str = Field(max_length=MAX_COLUMN)
    b_label: str = Field(max_length=MAX_LABEL)
    fingerprint: str = Field(max_length=64)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )


class ReferenceEnd(BaseModel):
    """One end of a reference, as a client names it."""

    model_config = ConfigDict(extra="forbid")

    connector_id: uuid.UUID
    # The same opaque identifier the catalog produced. Never taken apart here:
    # only the adapter that issued it knows how to read one (D21).
    node_id: str = Constrained(max_length=MAX_NODE_ID)
    column: str = Constrained(min_length=1, max_length=MAX_COLUMN)


class DeclaredReferenceCreate(BaseModel):
    """The two ends, in no significant order."""

    model_config = ConfigDict(extra="forbid")

    ends: tuple[ReferenceEnd, ReferenceEnd]


class ReferenceEndPublic(ReferenceEnd):
    """An end with the names a screen shows it by.

    The connection's name is read live and the node's label is the stored one:
    the viewer holds `read` on the connection by the rule that makes the
    reference visible at all, but naming the node again would mean asking the
    source once per reference (D106).
    """

    connector_name: str
    adapter_type: str
    node_label: str


class DeclaredReferencePublic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    ends: tuple[ReferenceEndPublic, ReferenceEndPublic]
    created_at: datetime | None


@dataclass(frozen=True)
class StoredEnd:
    """One end read off a stored row, so nothing else indexes columns by letter."""

    connector_id: uuid.UUID
    node_id: str
    column: str
    label: str


def end_of(reference: DeclaredReference, end: End) -> StoredEnd:
    if end == "a":
        return StoredEnd(
            connector_id=reference.a_connector_id,
            node_id=reference.a_node_id,
            column=reference.a_column,
            label=reference.a_label,
        )
    return StoredEnd(
        connector_id=reference.b_connector_id,
        node_id=reference.b_node_id,
        column=reference.b_column,
        label=reference.b_label,
    )


def other(end: End) -> End:
    return "b" if end == "a" else "a"


def issued_name(reference_id: uuid.UUID, end: End) -> str:
    """What this reference is called on the page, from this end of it.

    The end is in the name because a node referenced to itself is standing on
    both, and the two ways out are different ways out.
    """
    return f"{NAME_PREFIX}{reference_id}:{end}"


def parse_name(name: str) -> tuple[uuid.UUID, End] | None:
    """The reference and end a name issued here means, or nothing at all."""
    if not name.startswith(NAME_PREFIX):
        return None
    body, _, end = name[len(NAME_PREFIX) :].rpartition(":")
    if end not in ENDS:
        return None
    try:
        return uuid.UUID(body), "a" if end == "a" else "b"
    except ValueError:
        return None


def fingerprint(first: ReferenceEnd, second: ReferenceEnd) -> str:
    """One value for one pair, whichever way round it was drawn."""
    pair = sorted(
        [str(end.connector_id), end.node_id, end.column] for end in (first, second)
    )
    return hashlib.sha256(
        json.dumps(pair, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class EndReading:
    """What both sources said about an end at the moment it was asked."""

    connector: Connector
    node: CatalogNode
    column: FetchColumn


async def read_end(
    session: AsyncSession,
    user: User,
    resources: ResourceStore | None,
    end: ReferenceEnd,
) -> EndReading:
    """The end as its source states it now, or the reason it cannot be one.

    D107: the column must exist and must admit equality, because an end that
    cannot be looked up is an arrow that fails on every click. Access is
    checked by `resolve_source`, so a connection the caller cannot read never
    gets as far as being read.
    """
    connector = await get_or_404(session, end.connector_id, user, requires="read")
    source = await resolve_source(
        session, end.connector_id, user, resources, requires="read"
    )
    adapter = source.adapter
    if not isinstance(adapter, SupportsFetch) or not isinstance(
        adapter, SupportsNodePath
    ):
        raise ValueError(say("This source cannot be an end of a reference"))

    # One row, for its columns: `fetch` is the only capability every source
    # states its filterable columns through, and the read cache absorbs the
    # repetition.
    page = await adapter.fetch(FetchRequest(node_id=end.node_id, limit=1))
    column = next((found for found in page.columns if found.name == end.column), None)
    if column is None:
        raise ValueError(
            say('"{node}" has no column "{column}"', node=end.node_id, column=end.column)
        )
    if "eq" not in column.filter_operators:
        raise ValueError(
            say(
                'This source cannot look up "{column}" values of type {type}',
                column=end.column,
                type=column.type.sql,
            )
        )
    node = (await adapter.path_to(end.node_id))[-1]
    return EndReading(connector=connector, node=node, column=column)


async def create(
    session: AsyncSession, *, author: User, ends: tuple[EndReading, EndReading]
) -> DeclaredReference:
    """Store the pair, or hand back the one that is already there."""
    asked = tuple(
        ReferenceEnd(
            connector_id=reading.connector.id,
            node_id=reading.node.id,
            column=reading.column.name,
        )
        for reading in ends
    )
    mark = fingerprint(asked[0], asked[1])
    existing = (
        await session.exec(
            select(DeclaredReference).where(
                DeclaredReference.author_id == author.id,
                DeclaredReference.fingerprint == mark,
            )
        )
    ).first()
    if existing is not None:
        return existing

    reference = DeclaredReference(
        author_id=author.id,
        a_connector_id=asked[0].connector_id,
        a_node_id=asked[0].node_id,
        a_column=asked[0].column,
        a_label=ends[0].node.name,
        b_connector_id=asked[1].connector_id,
        b_node_id=asked[1].node_id,
        b_column=asked[1].column,
        b_label=ends[1].node.name,
        fingerprint=mark,
    )
    session.add(reference)
    await session.commit()
    await session.refresh(reference)
    return reference


async def get_own(
    session: AsyncSession, *, author: User, reference_id: uuid.UUID
) -> DeclaredReference | None:
    """One reference of this author's, or nothing.

    Nothing covers both a reference that does not exist and one belonging to
    somebody else, for the reason `get_with_access` gives: an id space that
    answers differently is an oracle.
    """
    found = await session.get(DeclaredReference, reference_id)
    if found is None or found.author_id != author.id:
        return None
    return found


async def delete(session: AsyncSession, reference: DeclaredReference) -> None:
    await session.delete(reference)
    await session.commit()


async def _readable(
    session: AsyncSession,
    user: User,
    connector_id: uuid.UUID,
    seen: dict[uuid.UUID, Connector | None],
) -> Connector | None:
    """The connection if this user may still read it, switched on, or nothing.

    D106: a reference is visible only while both of its ends are. A revoked
    grant, a connection switched off and a deleted one all take the arrow off
    the screen rather than leaving one that answers 403.
    """
    if connector_id in seen:
        return seen[connector_id]
    found = await crud.get_with_access(
        session, connector_id=connector_id, user=user
    )
    connector = None
    if found is not None and found[0].enabled:
        connector = found[0]
    seen[connector_id] = connector
    return connector


async def _for_node(
    session: AsyncSession, *, author: User, connector_id: uuid.UUID, node_id: str
) -> list[DeclaredReference]:
    statement = select(DeclaredReference).where(
        DeclaredReference.author_id == author.id,
        or_(
            and_(
                col(DeclaredReference.a_connector_id) == connector_id,
                col(DeclaredReference.a_node_id) == node_id,
            ),
            and_(
                col(DeclaredReference.b_connector_id) == connector_id,
                col(DeclaredReference.b_node_id) == node_id,
            ),
        ),
    )
    return list((await session.exec(statement)).all())


async def references_for(
    session: AsyncSession, *, user: User, connector_id: uuid.UUID, node_id: str
) -> list[FetchReference]:
    """What this person has drawn from this node, as the grid already reads it.

    An ordinary `FetchResult.references` entry, so the arrow, the tooltip and
    the click are the ones D36 built and nothing on the screen learns that a
    second kind of reference exists.
    """
    seen: dict[uuid.UUID, Connector | None] = {}
    listed: list[FetchReference] = []
    for reference in await _for_node(
        session, author=user, connector_id=connector_id, node_id=node_id
    ):
        for end in ENDS:
            near = end_of(reference, end)
            if near.connector_id != connector_id or near.node_id != node_id:
                continue
            far = end_of(reference, other(end))
            connector = await _readable(session, user, far.connector_id, seen)
            if connector is None:
                continue
            listed.append(
                FetchReference(
                    name=issued_name(reference.id, end),
                    columns=[near.column],
                    target_title=(
                        far.label
                        if far.connector_id == connector_id
                        else f"{connector.name} · {far.label}"
                    ),
                )
            )
    return listed


async def follow(
    session: AsyncSession,
    *,
    user: User,
    resources: ResourceStore | None,
    connector_id: uuid.UUID,
    request: FollowReferenceRequest,
) -> ReferenceTarget:
    """Where a declared reference goes, read from the far source now (D107).

    Nothing is taken from the request but the name and the value. The name says
    which reference and which end; everything else — that the far node is still
    there, still has the column and still admits equality — is read again, and
    the predicate is built from that reading.
    """
    parsed = parse_name(request.reference)
    reference = (
        None
        if parsed is None
        else await get_own(session, author=user, reference_id=parsed[0])
    )
    if parsed is None or reference is None:
        raise ValueError(
            say('Relation has no reference "{name}"', name=request.reference)
        )

    near = end_of(reference, parsed[1])
    if near.connector_id != connector_id or near.node_id != request.node_id:
        raise ValueError(
            say('Relation has no reference "{name}"', name=request.reference)
        )

    if len(request.values) != 1 or request.values[0].column != near.column:
        raise ValueError(
            say('Reference "{name}" is over {column}', name=request.reference, column=near.column)
        )
    value = request.values[0].value
    if value is None:
        # The same answer D36 gives a key with a missing value: this row names
        # nothing, which is a fact about the data rather than a failure.
        return NoReferencedRows(reason=say("This row has no value for that reference"))

    far = end_of(reference, other(parsed[1]))
    end = ReferenceEnd(
        connector_id=far.connector_id, node_id=far.node_id, column=far.column
    )
    try:
        reading = await read_end(session, user, resources, end)
    except ValueError as exc:
        # The far source has changed under a reference that was drawn against
        # what it used to say: a header rewritten, a column dropped, a type it
        # will no longer compare. An answer about the data, not an error (D2d).
        return NoReferencedRows(reason=str(exc))

    return ReferencedRows(
        node=reading.node,
        connector=ReferenceConnection(
            id=reading.connector.id,
            name=reading.connector.name,
            adapter_type=reading.connector.adapter_type,
        ),
        filters=[ScalarFilter(column=far.column, op="eq", value=value)],
    )


def public_of(
    reference: DeclaredReference, connectors: dict[uuid.UUID, Connector]
) -> DeclaredReferencePublic:
    """One reference as a screen shows it, named by connections already read."""

    def side(end: End) -> ReferenceEndPublic:
        stored = end_of(reference, end)
        connector = connectors[stored.connector_id]
        return ReferenceEndPublic(
            connector_id=stored.connector_id,
            node_id=stored.node_id,
            column=stored.column,
            connector_name=connector.name,
            adapter_type=connector.adapter_type,
            node_label=stored.label,
        )

    return DeclaredReferencePublic(
        id=reference.id,
        ends=(side("a"), side("b")),
        created_at=reference.created_at,
    )


async def list_visible(
    session: AsyncSession,
    *,
    user: User,
    connector_id: uuid.UUID | None = None,
    node_id: str | None = None,
) -> list[DeclaredReferencePublic]:
    """Every reference of this person's that still has both of its ends.

    Filtered to one node when a node is named, which is what the structure of a
    relation asks for; unfiltered, it is the whole of what one person has drawn.
    """
    if connector_id is not None and node_id is not None:
        found = await _for_node(
            session, author=user, connector_id=connector_id, node_id=node_id
        )
    else:
        statement = select(DeclaredReference).where(
            DeclaredReference.author_id == user.id
        )
        if connector_id is not None:
            statement = statement.where(
                or_(
                    col(DeclaredReference.a_connector_id) == connector_id,
                    col(DeclaredReference.b_connector_id) == connector_id,
                )
            )
        found = list(
            (
                await session.exec(statement.order_by(col(DeclaredReference.created_at)))
            ).all()
        )

    seen: dict[uuid.UUID, Connector | None] = {}
    listed: list[DeclaredReferencePublic] = []
    for reference in found:
        connectors: dict[uuid.UUID, Connector] = {}
        for end in ENDS:
            stored = end_of(reference, end)
            connector = await _readable(session, user, stored.connector_id, seen)
            if connector is not None:
                connectors[stored.connector_id] = connector
        if any(
            end_of(reference, end).connector_id not in connectors for end in ENDS
        ):
            # One end is gone or no longer readable, so there is nothing here a
            # person could act on: the same rule that hides the arrow (D106).
            continue
        listed.append(public_of(reference, connectors))
    return listed
