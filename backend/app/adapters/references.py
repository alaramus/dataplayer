"""Going from one row's foreign key to the rows it names.

The client sends back what it already read — the name of the reference and the
values standing in that row — and gets a place to go. It never composes the
predicate, never maps its own columns onto the target's, and never takes a node
id apart (D21). The whole of the client's influence on the query is which
reference of which row it pointed at.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.catalog import CatalogNode
from app.adapters.fetch import Filter


class ReferenceValue(BaseModel):
    """One column of the key, with the value the caller read in that row."""

    model_config = ConfigDict(extra="forbid")

    column: str
    value: str | None


class FollowReferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    # The source's own name for the reference, as the fetch result gave it.
    reference: str
    # A row handle would not do: handles exist only where the source can
    # version a row, and a keyless table can still hold a foreign key.
    values: Annotated[list[ReferenceValue], Field(min_length=1, max_length=64)]


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
