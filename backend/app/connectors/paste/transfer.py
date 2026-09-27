"""A paste carried out as an owned job: what it moves and how each piece ended (D168).

The kinds that move bytes plan here, in the request, and transfer later, in a
job that owns the `Transfer` below as its payload. The job itself lives above
this package; a kind only reports to a `TransferReport` it is handed.

The payload holds what was ticked, with counts, rather than every file: a
folder of ten thousand files rewritten into the row at every file would be
gigabytes of writes (D169).
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
    TablesChoice,
)

# What a transfer reads and writes at a time, and so how late a Stop can be.
PIECE_BYTES = 1024 * 1024
# Files that did not arrive, listed by path; the rest are counted.
MAX_PROBLEMS = 100

# `stopped` is the one in hand when the job was stopped: discarded, so nothing
# is left under its name. `kept` is a move whose copy arrived while its source
# stayed where it was.
TransferOutcome = Literal["pending", "running", "done", "kept", "failed", "stopped"]


class TransferItem(BaseModel):
    """One ticked file, folder or table, and what became of what it holds."""

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(max_length=4096)
    name: str = Field(max_length=255)
    is_folder: bool = False
    # What the request measured: bytes, and files below a folder (one for a
    # file or a table).
    size_bytes: int | None = None
    files: int = 1
    # What the job did with them.
    arrived: int = 0
    failed: int = 0
    skipped: int = 0
    # Of those that arrived, the sources a move removed.
    removed: int = 0
    outcome: TransferOutcome = "pending"
    # The name it has at the destination, when that is decided there: Keep
    # both renamed it, or it is the file a table became.
    published_as: str | None = Field(default=None, max_length=255)
    # Its node id at the destination once it arrived, whatever it was named:
    # a pipeline's next link reads it (D178).
    published_id: str | None = Field(default=None, max_length=4096)
    # A sentence that names the item, so a list of them reads on its own.
    message: str | None = Field(default=None, max_length=600)
    rows: int | None = None


class TransferProblem(BaseModel):
    """A file below a ticked folder that did not arrive, or was not removed."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(max_length=4096)
    message: str = Field(max_length=600)


class TransferPlan(BaseModel):
    """What the request found before anything moved."""

    items: list[TransferItem] = Field(min_length=1, max_length=MAX_CLIPBOARD_NODES)
    bytes_total: int | None
    # The folder it goes into; empty for the top of the connection.
    place: str
    # The file name asked for, when the kind writes one file of its own.
    name: str | None = None
    # A copy of tables as its window chose it, every name decided (D182).
    tables: TablesChoice | None = None


class Transfer(BaseModel):
    """The payload of a transfer job, written as it goes. Never a secret."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[2] = 2
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
    # What a copy of tables was planned with, so the job plans it again (D182).
    tables: TablesChoice | None = None
    items: list[TransferItem] = Field(min_length=1, max_length=MAX_CLIPBOARD_NODES)
    # Unknown for a table, whose CSV is as long as it turns out to be.
    bytes_total: int | None = None
    bytes_done: int = 0
    files_done: int = 0
    # The file in hand, by its path below what was ticked.
    current: str | None = Field(default=None, max_length=4096)
    # Files and folders put in place so far, for a client that re-reads as
    # they arrive.
    published: int = 0
    problems: list[TransferProblem] = Field(default_factory=list, max_length=MAX_PROBLEMS)
    problems_more: int = 0

    @property
    def files_total(self) -> int:
        return sum(item.files for item in self.items)

    def problem(self, path: str, message: str) -> None:
        if len(self.problems) < MAX_PROBLEMS:
            self.problems.append(TransferProblem(path=path, message=message))
        else:
            self.problems_more += 1


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

    async def progressed(self) -> None:
        """Something moved: written and told at most once a second (D169)."""
        ...

    async def removing(self) -> None:
        """Everything is copied, and a move's sources go now."""
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
