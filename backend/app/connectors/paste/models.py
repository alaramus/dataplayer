"""What a paste between connections is asked with and answered with (D164)."""

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.fetch import FetchColumn

# Room for whatever a catalog lets a person tick. Each kind states its own,
# smaller ceiling as a reason, rather than the request failing validation.
MAX_CLIPBOARD_NODES = 1000

PasteKindName = Literal[
    "file_copy",
    "file_move",
    "relation_csv",
    "rows_new_relation",
    "rows_into_relation",
    "tables_copy",
]
ClipboardMode = Literal["copy", "move"]
Conflict = Literal["refuse", "replace", "rename"]
# The window an offer opens before it runs, named for the client to pick one
# by; `run` opens none.
PasteWorkflow = Literal["run", "file-name", "new-relation", "into-relation", "copy-tables"]
# What becomes of links to tables that were not ticked (D182): the tables are
# copied too, the links are not made, or they point at the originals.
TableLinks = Literal["copy", "drop", "keep"]


class PastePair(BaseModel):
    """What the clipboard holds and where Paste was chosen."""

    model_config = ConfigDict(extra="forbid")

    source_connector_id: uuid.UUID
    source_node_ids: list[str] = Field(min_length=1, max_length=MAX_CLIPBOARD_NODES)
    mode: ClipboardMode
    # The place Paste was chosen in.
    destination_node_id: str | None = None
    # The one node ticked there, when exactly one is. A kind that pastes into
    # a place ignores it (D166).
    target_node_id: str | None = None


class PasteColumn(BaseModel):
    """A source column, and the column it fills or becomes."""

    model_config = ConfigDict(extra="forbid")

    source: str
    target: str
    # For a new relation: its type in the destination's vocabulary.
    type_code: str | None = None


class TablesChoice(BaseModel):
    """What the window of a copy of tables chose (D182)."""

    model_config = ConfigDict(extra="forbid")

    # The new name of each table, by its node id at the source; a table
    # absent here is given a free one.
    names: dict[str, str] = Field(default_factory=dict)
    rows: bool = True
    # None: kept within one database, copied otherwise.
    links: TableLinks | None = None
    # Tables that point at the ticked ones, ticked in the window to join.
    also: list[str] = Field(default_factory=list, max_length=MAX_CLIPBOARD_NODES)


class PasteRun(PastePair):
    """One offer, run with the choices its window asked for."""

    kind: PasteKindName
    conflict: Conflict = "refuse"
    name: str | None = Field(default=None, min_length=1, max_length=255)
    columns: list[PasteColumn] | None = Field(default=None, max_length=100)
    tables: TablesChoice | None = None


class PasteOffer(BaseModel):
    kind: PasteKindName
    title: str
    # The clipboard verb it runs as: in a pair nothing is held, so the offer
    # says it (D167).
    mode: ClipboardMode = "copy"
    available: bool
    reason: str | None = None
    name_conflict: bool = False
    # The result is another kind of object than the source, so Paste asks
    # before it runs.
    converts: bool = False
    can_replace: bool = True
    # Whether running it changes the source connection too, success or not:
    # a failed move may already have removed earlier files.
    changes_source: bool = False
    workflow: PasteWorkflow = "run"
    # Whether running it makes a node of its own there — a file, a table, a
    # copy — which a pipeline's next link may read (D178).
    makes: bool = False
    # Set by a kind that asks for a name: what its field starts as.
    suggested_name: str | None = None
    # What a rows window pairs: the source's columns, and the insertable
    # columns of the ticked target.
    source_columns: list[FetchColumn] = Field(default_factory=list)
    target_columns: list[FetchColumn] = Field(default_factory=list)


class PasteOffers(BaseModel):
    offers: list[PasteOffer]


class PasteResult(BaseModel):
    """A paste done inside the request; a transfer answers with its job (D168)."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    outcome: Literal["done"] = "done"
    kind: PasteKindName
    message: str
    written: int
    rows: int | None = None
    name: str | None = None
    reload_node_ids: list[str | None]
    # The node it made, when it made one: a pipeline's next link reads it (D178).
    made_node_id: str | None = None


class PairSide(BaseModel):
    """One catalog of a pair: where it stands and what is ticked in it."""

    model_config = ConfigDict(extra="forbid")

    connector_id: uuid.UUID
    place: str | None = None
    ticked: list[str] = Field(default_factory=list, max_length=MAX_CLIPBOARD_NODES)


class PairRequest(BaseModel):
    """A pair asked one way: the ticks of `source` into `destination` (D167)."""

    model_config = ConfigDict(extra="forbid")

    source: PairSide
    destination: PairSide


class Availability(BaseModel):
    available: bool
    reason: str | None = None


class ClipboardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_ids: list[str] = Field(default_factory=list, max_length=MAX_CLIPBOARD_NODES)


class ClipboardOffer(BaseModel):
    """Whether Copy and Cut are drawn for a selection, and why one is off.

    None means no kind takes this source's nodes in that mode, so the command
    is not drawn at all.
    """

    can_copy: Availability | None = None
    can_cut: Availability | None = None


ForeseenKind = Literal["file", "folder", "table"]


class Foreseen(BaseModel):
    """A node as a pipeline's link will make it (D178): described, not read.

    What a kind is asked of in place of a node that may not exist yet. The
    columns are what it will read as rows, when it will.
    """

    model_config = ConfigDict(extra="forbid")

    kind: ForeseenKind
    name: str
    columns: list[FetchColumn] = Field(default_factory=list)


# One end of a pair a pipeline asks about: a node by its id, the top of a
# connection as None, or a node a link will make.
type PairEnd = str | Foreseen | None
