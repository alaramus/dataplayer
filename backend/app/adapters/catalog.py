from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class BaseNode(BaseModel):
    """Fields every catalog node has, whatever the source.

    There are deliberately only three of them. In the old application every
    node was a plain dict, which let each adapter give a shared key its own
    meaning — `schema` held a database schema name for PostgreSQL and the
    literal "directory" for S3. Anything beyond these three lives on a node
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


class ColumnNode(BaseNode):
    kind: Literal["column"] = "column"
    has_children: bool = False
    data_type: str
    nullable: bool
    primary_key: bool = False


# Adding a kind means adding a class here. The friction is intended: a key can
# be added to a dict silently, a class cannot.
CatalogNode = Annotated[
    SchemaNode | TableNode | ViewNode | ColumnNode, Field(discriminator="kind")
]
