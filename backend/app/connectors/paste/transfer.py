"""A paste carried out as an owned job: what it moves and how each piece ended (D168).

The kinds that move bytes plan here, in the request, and transfer later, in a
job that owns the `Transfer` below as its payload. The job itself lives above
this package; a kind only reports to a `TransferReport` it is handed.
"""

import asyncio
import uuid
from collections.abc import Callable
from typing import Literal, Protocol

from anyio import CapacityLimiter, to_thread
from pydantic import BaseModel, ConfigDict, Field

from app.connectors.paste.models import (
    MAX_CLIPBOARD_NODES,
    ClipboardMode,
    Conflict,
    PasteKindName,
)

# What a transfer reads and writes at a time, and so how late a Stop can be.
PIECE_BYTES = 1024 * 1024

# `stopped` is the one in hand when the job was stopped: discarded, so nothing
# is left under its name. `kept` is a move whose copy arrived while its source
# stayed where it was.
TransferOutcome = Literal["pending", "running", "done", "kept", "failed", "stopped"]


class TransferItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(max_length=4096)
    name: str = Field(max_length=255)
    size_bytes: int | None = None
    outcome: TransferOutcome = "pending"
    # The name it has at the destination, when that is decided there: Keep
    # both renamed it, or it is the file a table became.
    published_as: str | None = Field(default=None, max_length=255)
    # A sentence that names the item, so a list of them reads on its own.
    message: str | None = Field(default=None, max_length=600)
    rows: int | None = None


class TransferPlan(BaseModel):
    """What the request found before anything moved."""

    items: list[TransferItem] = Field(min_length=1, max_length=MAX_CLIPBOARD_NODES)
    bytes_total: int | None
    # The folder it goes into; empty for the top of the connection.
    place: str
    # The file name asked for, when the kind writes one file of its own.
    name: str | None = None


class Transfer(BaseModel):
    """The payload of a transfer job, written as it goes. Never a secret."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    kind: PasteKindName
    title: str = Field(max_length=100)
    # The kind's own words while it runs and for an item that arrived, so
    # the screen names no kind: "Copying" and "copied".
    doing: str = Field(max_length=100)
    done: str = Field(max_length=100)
    mode: ClipboardMode
    conflict: Conflict
    source_connector_id: uuid.UUID
    source_label: str = Field(max_length=255)
    destination_connector_id: uuid.UUID
    destination_node_id: str | None = Field(default=None, max_length=4096)
    destination_label: str = Field(max_length=255)
    # What the folder is called in a sentence: its name, or the connection's
    # for the top of it.
    place_label: str = Field(max_length=255)
    name: str | None = Field(default=None, max_length=255)
    items: list[TransferItem] = Field(min_length=1, max_length=MAX_CLIPBOARD_NODES)
    # Unknown for a table, whose CSV is as long as it turns out to be.
    bytes_total: int | None = None
    bytes_done: int = 0
    # Files put in place so far, for a client that re-reads as they arrive.
    published: int = 0


class TransferStopped(Exception):
    """What no later item could survive: the rest are not attempted."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class TransferReport(Protocol):
    """Where a kind says how its transfer is going, and gets its threads."""

    async def in_thread[T](self, work: Callable[[], T]) -> T:
        """Blocking work, on the transfers' own threads (D168)."""
        ...

    async def changed(self) -> None:
        """An item's outcome changed: written and told now."""
        ...

    async def progressed(self) -> None:
        """Bytes moved: written and told at most once a second."""
        ...


async def in_worker[T](
    work: Callable[[], T], *, limiter: CapacityLimiter | None = None
) -> T:
    """Run one piece of blocking work, and on cancellation wait for it to end.

    A native cancel does not wait for a worker thread: anyio's shield covers
    its own cancel scopes only. Unwaited, the piece in hand would still be
    writing while the cleanup after a Stop removes the file it writes to.
    """
    running = asyncio.ensure_future(to_thread.run_sync(work, limiter=limiter))
    try:
        return await asyncio.shield(running)
    except asyncio.CancelledError:
        await asyncio.wait([running])
        if not running.cancelled():
            # Retrieved, so a failure of the abandoned piece is not reported
            # as never having been read.
            running.exception()
        raise
