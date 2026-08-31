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
    # Whether this node also answers `relation-model`. Said by the source
    # rather than worked out by the client from the kind: a PostgreSQL schema
    # is not describable while its tables are, and among files only the ones
    # that declare their own columns are (D51).
    describable: bool = False


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
    | ReportNode,
    Field(discriminator="kind"),
]


# The kinds themselves, as a closed set. A route needs to speak about the kind
# of a node without holding one — deciding which actions a directory admits,
# for instance — and a bare string there would let a typo through silently.
# The test that this matches the union keeps the two from drifting apart.
NodeKind = Literal[
    "schema", "table", "view", "directory", "file", "dataset", "entry", "report"
]
