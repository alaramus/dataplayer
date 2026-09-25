"""What a paste between connections is asked with and answered with (D164)."""

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Room for whatever a catalog lets a person tick. Each kind states its own,
# smaller ceiling as a reason, rather than the request failing validation.
MAX_CLIPBOARD_NODES = 1000

PasteKindName = Literal["file_copy", "file_move", "relation_csv"]
ClipboardMode = Literal["copy", "move"]
Conflict = Literal["refuse", "replace", "rename"]


class PastePair(BaseModel):
    """What the clipboard holds and where Paste was chosen."""

    model_config = ConfigDict(extra="forbid")

    source_connector_id: uuid.UUID
    source_node_ids: list[str] = Field(min_length=1, max_length=MAX_CLIPBOARD_NODES)
    mode: ClipboardMode
    destination_node_id: str | None = None


class PasteRun(PastePair):
    """One offer, run with the choices its window asked for."""

    kind: PasteKindName
    conflict: Conflict = "refuse"
    name: str | None = Field(default=None, min_length=1, max_length=255)


class PasteOffer(BaseModel):
    kind: PasteKindName
    title: str
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
    # Set by a kind that asks for a name: what its field starts as.
    suggested_name: str | None = None


class PasteOffers(BaseModel):
    offers: list[PasteOffer]


class PasteResult(BaseModel):
    kind: PasteKindName
    message: str
    written: int
    rows: int | None = None
    name: str | None = None
    reload_node_ids: list[str | None]


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
