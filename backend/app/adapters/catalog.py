from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.content import NodeRepresentation


class BaseNode(BaseModel):
    """Fields every catalog node has, whatever the source.

    There are deliberately only four of them. In the old application every
    node was a plain dict, which let each adapter give a shared key its own
    meaning — `schema` held a database schema name for PostgreSQL and the
    literal "directory" for S3. Anything beyond these four lives on a node
    class of its own.
    """

    # Extra keys are rejected rather than ignored: a field belonging to another
    # kind of node must fail loudly, not travel unnoticed.
    model_config = ConfigDict(extra="forbid")

    # Opaque outside the adapter that produced it. PostgreSQL encodes
    # "public" and "public.users"; an object store encodes a prefix.
    id: str
    name: str
    has_children: bool
    # Preferred representation first. Empty means the node can be browsed or
    # acted on but has no content viewer yet.
    representations: list[NodeRepresentation]


class SchemaNode(BaseNode):
    kind: Literal["schema"] = "schema"
    is_system: bool = False


class TableNode(BaseNode):
    kind: Literal["table"] = "table"
    # Estimated on purpose: an exact count costs a full scan. The name says so
    # instead of pairing a count with a separate precision flag.
    row_count_estimate: int | None = None
    size_bytes: int | None = None
    is_system: bool = False


class ViewNode(BaseNode):
    kind: Literal["view"] = "view"
    is_materialized: bool = False
    is_system: bool = False


class DirectoryNode(BaseNode):
    kind: Literal["directory"] = "directory"
    modified_at: datetime | None = None


class FileNode(BaseNode):
    kind: Literal["file"] = "file"
    has_children: bool = False
    size_bytes: int
    modified_at: datetime | None = None


# Adding a kind means adding a class here. The friction is intended: a key can
# be added to a dict silently, a class cannot.
CatalogNode = Annotated[
    SchemaNode | TableNode | ViewNode | DirectoryNode | FileNode,
    Field(discriminator="kind"),
]


# The kinds themselves, as a closed set. A route needs to speak about the kind
# of a node without holding one — deciding which actions a directory admits,
# for instance — and a bare string there would let a typo through silently.
# The test that this matches the union keeps the two from drifting apart.
NodeKind = Literal["schema", "table", "view", "directory", "file"]
