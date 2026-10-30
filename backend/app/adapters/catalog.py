from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.content import NodeRepresentation
from app.adapters.frameworks import DetectedFramework
from app.adapters.specializations import (
    TimescaleContinuousAggregate,
    TimescaleHypertable,
)


class BaseNode(BaseModel):
    """Fields every catalog node has, whatever the source.

    There are deliberately only four of them. A plain dict per node lets each
    adapter give a shared key its own meaning — `schema` holding a schema name
    for PostgreSQL and the literal "directory" for an object store. Anything
    beyond these four lives on a node class of its own.
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
    # Whether this node also answers `relation-model`. Said by the source
    # rather than worked out by the client from the kind: a PostgreSQL schema
    # is not describable while its tables are, and among files only the ones
    # that declare their own columns are (D51).
    describable: bool = False
    # Whether this node also answers `node-summary`: how big, since when, what
    # it may be opened as, and what its format states about itself. Said by the
    # source for the reason `describable` is said by it — a client that worked
    # it out from the kind would be deciding what a source can answer (D75).
    summarizable: bool = False


class SchemaNode(BaseNode):
    kind: Literal["schema"] = "schema"
    # What the source calls it, where that is not a schema: a MySQL database
    # is a schema to everything else here (D229), and is named as a database.
    term: Literal["schema", "database"] = "schema"
    is_system: bool = False
    frameworks: list[DetectedFramework] = Field(default_factory=list)


class TableNode(BaseNode):
    kind: Literal["table"] = "table"
    # What the source calls it, where that is not a table: a MongoDB
    # collection is a table to everything else here (D283).
    term: Literal["table", "collection"] = "table"
    # Estimated on purpose: an exact count costs a full scan. The name says so
    # instead of pairing a count with a separate precision flag.
    row_count_estimate: int | None = None
    size_bytes: int | None = None
    is_system: bool = False
    specialization: TimescaleHypertable | None = None


class ViewNode(BaseNode):
    kind: Literal["view"] = "view"
    is_materialized: bool = False
    is_system: bool = False
    specialization: TimescaleContinuousAggregate | None = None


class DirectoryNode(BaseNode):
    kind: Literal["directory"] = "directory"
    modified_at: datetime | None = None


class FileNode(BaseNode):
    kind: Literal["file"] = "file"
    has_children: bool = False
    size_bytes: int
    modified_at: datetime | None = None


class DatasetNode(BaseNode):
    """A tabular member of a container file, such as one sheet of a workbook.

    Deliberately not a file: it has no bytes of its own, so rename, delete and
    download are ruled out by the kinds those actions name, and it needs no
    rule of its own (D51). Its counts are what the container stated when it was
    listed; a container that states none leaves them empty rather than making
    the listing read the whole member to find out.
    """

    kind: Literal["dataset"] = "dataset"
    has_children: bool = False
    row_count: int | None = None
    column_count: int | None = None
    hidden: bool = False


class EntryNode(BaseNode):
    """One member of an archive, which may itself hold others (D53).

    Not a file: it has no bytes on disk of its own, so rename, delete, a new
    folder and an upload are out of it by the kinds those actions name. Not a
    directory either, for the same reason — a folder inside an archive is an
    entry whose `has_children` is true.
    """

    kind: Literal["entry"] = "entry"
    size_bytes: int | None = None
    compressed_bytes: int | None = None
    modified_at: datetime | None = None
    # Listed and never followed: a link written inside a file is still a link.
    is_link: bool = False
    is_encrypted: bool = False


class ReportNode(BaseNode):
    """A named read-only answer a source gives about itself, or a section of them.

    Not a view: there is no relation to describe, no owner and no constraint,
    and the statement behind it lives in this repository rather than on the
    server (D55). The section holding a source's reports is a report with
    children, the way a folder inside an archive is an entry with children.

    `description` is the one line that makes a name like "Processes" mean
    something without opening it; the source writes it, because only the source
    knows what its report answers.
    """

    kind: Literal["report"] = "report"
    description: str | None = None


class DatabaseNode(BaseNode):
    """One numbered key space of a key-value server.

    Not a schema. A schema is a namespace inside one database and several of
    them can be looked at together, because they share a connection and a
    transaction; these are separate key spaces on the same server that share
    nothing but the port, and a key in one is invisible from another. Reusing
    `schema` would be giving one kind two meanings, which is the thing
    `BaseNode` is shaped to prevent.

    It is still a grouping rather than a folder: the number chosen when the
    connection was written says where to start, not where to stay (D91).
    """

    kind: Literal["database"] = "database"
    has_children: bool = True
    # Which one the connection itself names, and therefore the one the catalog
    # opens on. Said by the source, because only the source knows what its
    # connection was written with.
    preferred: bool = False
    # How many keys the server reports in it, or nothing when it reports none.
    # Read from one INFO rather than a DBSIZE per database.
    keys: int | None = None


class KeyNode(BaseNode):
    """One key of a key-value store.

    Not a table, though it is read as rows: a table has columns of its own and
    a relation to describe, and a key has a Redis data type and an expiry
    clock. Reusing `table` here would give one kind two meanings — exactly
    what `BaseNode` is shaped to prevent — and every
    action that names a table would then be offered on a key.

    The prefix a key hangs under is a `directory`: a container of nodes with
    nothing else to say about itself, which is what a namespace is.
    """

    kind: Literal["key"] = "key"
    has_children: bool = False
    # What the server says is in it. A closed set, because it is: Redis has
    # these and no more.
    data_type: Literal["string", "list", "set", "zset", "hash", "stream"]
    # Seconds until it disappears, or nothing when it will not. Read at the
    # moment of listing, and therefore already out of date — which is why it
    # is a caption rather than anything a decision is made from.
    ttl_seconds: int | None = None
    # How many of whatever it holds: characters of a string, fields of a hash,
    # members of a set. One number, because "how big is it" is one question
    # however the answer is counted.
    length: int | None = None


# Adding a kind means adding a class here. The friction is intended: a key can
# be added to a dict silently, a class cannot.
CatalogNode = Annotated[
    SchemaNode
    | TableNode
    | ViewNode
    | DirectoryNode
    | FileNode
    | DatasetNode
    | EntryNode
    | ReportNode
    | DatabaseNode
    | KeyNode,
    Field(discriminator="kind"),
]


# The kinds themselves, as a closed set. A route needs to speak about the kind
# of a node without holding one — deciding which actions a directory admits,
# for instance — and a bare string there would let a typo through silently.
# The test that this matches the union keeps the two from drifting apart.
NodeKind = Literal[
    "schema",
    "table",
    "view",
    "directory",
    "file",
    "dataset",
    "entry",
    "report",
    "database",
    "key",
]


# How a node may be opened from somewhere other than its catalog: the catalog
# pointing at it, what it prefers to be read as, its rows, its structure, or
# what it is. One closed set for everybody who opens a node from elsewhere —
# the agent and the search — so the workspace understands one list (D197).
NodeView = Literal["catalog", "preferred", "rows", "structure", "summary"]
