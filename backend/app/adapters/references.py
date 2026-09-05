"""Going from one row to the rows a key relates it to, either way round.

The client sends back what it already read — the name of the reference and the
values standing in that row — and gets a place to go. It never composes the
predicate, never maps its own columns onto the target's, and never takes a node
id apart (D21). The whole of the client's influence on the query is which
reference of which row it pointed at.

A key of this relation points away from it; a key of some other relation lands
on it. Both are followed by the same call and answered by the same union, and
which of the two is meant is said rather than guessed (D110).
"""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.catalog import CatalogNode
from app.adapters.fetch import Filter


class ReferenceValue(BaseModel):
    """One column of the key, with the value the caller read in that row."""

    model_config = ConfigDict(extra="forbid")

    column: str
    value: str | None


# Which way a reference is being followed. Said rather than worked out from the
# name: a constraint name is unique within a relation and not within a schema,
# so a key of this relation and a key landing on it can be called the same
# thing (D110).
FollowDirection = Literal["outgoing", "incoming"]


class ArrivingReference(BaseModel):
    """One key of another relation that lands on this one.

    The mirror of `FetchReference`, and deliberately the same shape: `columns`
    are this relation's, because they are the cells the way back is offered
    from, and the name is the handle to send back. What the key is called over
    there, and which of its columns stand for these, stay with the source —
    the same rule that keeps a target's columns out of `FetchReference`.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    columns: list[str] = Field(min_length=1)
    # What points here, for the menu that offers it. Not an id: what to open
    # arrives from the source when the reference is actually followed.
    source_title: str


class ArrivingReferencesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str


class FollowReferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    # The source's own name for the reference, as the fetch result gave it —
    # or as `arriving_references` gave it, for a key landing here.
    reference: str
    direction: FollowDirection = "outgoing"
    # A row handle would not do: handles exist only where the source can
    # version a row, and a keyless table can still hold a foreign key.
    values: Annotated[list[ReferenceValue], Field(min_length=1, max_length=64)]


class ReferenceConnection(BaseModel):
    """The connection a target lives in, as the screen needs to open a tab.

    An adapter never fills this in: it knows itself and not its own identity.
    The route does, because it is the one place that knows which connection it
    just asked (D108).
    """

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str
    adapter_type: str


class ReferencedRows(BaseModel):
    """Where to go, and the predicate that gets there.

    The target is a whole `CatalogNode` for the reason `path_to` answers with
    them (D21): the screen already knows how to open one, name its tab and
    decide whether it can be described, so nothing here needs a second model of
    a node or a second table of what a kind of node affords.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["rows"] = "rows"
    node: CatalogNode
    # Filled in on the way out, by the route rather than by the source that
    # answered. Null only inside the application, never in a reply: a declared
    # reference can land in another connection entirely (D108).
    connector: ReferenceConnection | None = None
    # Built by the source against the target's own columns, in the same closed
    # vocabulary any other filter uses, so the fetch it is handed to validates
    # it exactly as it validates a filter a user typed.
    filters: list[Filter] = Field(min_length=1)


class NoReferencedRows(BaseModel):
    """There is nowhere to go, and the source says why.

    Not an error: a row whose key is empty references nothing, and that is an
    answer about the data rather than a failure of the request. D2d — what a
    source cannot do is stated in the answer.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["none"] = "none"
    reason: str


ReferenceTarget = Annotated[
    ReferencedRows | NoReferencedRows,
    Field(discriminator="kind"),
]
