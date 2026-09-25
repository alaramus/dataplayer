"""What one kind of paste between connections has to say about itself (D164)."""

from typing import Protocol, runtime_checkable

from app.adapters.fetch import FetchColumn
from app.adapters.protocol import DataAdapter
from app.connectors.paste.models import (
    Availability,
    ClipboardMode,
    PasteKindName,
    PasteOffer,
    PastePair,
    PasteResult,
    PasteRun,
    PasteWorkflow,
)
from app.connectors.paste.transfer import Transfer, TransferPlan, TransferReport
from app.core.access import Access


class PasteKind(Protocol):
    """One way a clipboard can land in another connection.

    Matched by the capabilities of the two adapters, never by their type, so
    a new source takes part by implementing what a kind asks for.
    """

    @property
    def name(self) -> PasteKindName: ...

    @property
    def title(self) -> str: ...

    @property
    def mode(self) -> ClipboardMode: ...

    @property
    def needs(self) -> str:
        """What the source must be, in the words that ask for it."""
        ...

    @property
    def workflow(self) -> PasteWorkflow: ...

    @property
    def converts(self) -> bool: ...

    @property
    def can_replace(self) -> bool: ...

    @property
    def source_requires(self) -> Access: ...

    @property
    def destination_requires(self) -> Access: ...

    @property
    def changes_source(self) -> bool: ...

    def takes_from(self, source: DataAdapter) -> bool:
        """Whether this source has what the kind reads, whatever the nodes."""
        ...

    def serves(self, source: DataAdapter, destination: DataAdapter) -> bool:
        """Whether both ends have what the kind needs, whatever the nodes."""
        ...

    async def supply(self, source: DataAdapter, node_ids: list[str]) -> Availability:
        """Whether these nodes can be put on the clipboard for this kind."""
        ...

    async def offer(
        self, source: DataAdapter, destination: DataAdapter, pair: PastePair
    ) -> PasteOffer:
        """What running it now would do, checked without changing anything."""
        ...


@runtime_checkable
class PastesNow(PasteKind, Protocol):
    """A kind carried out inside the request that asks for it."""

    async def run(
        self, source: DataAdapter, destination: DataAdapter, request: PasteRun
    ) -> PasteResult: ...


@runtime_checkable
class PastesAsJob(PasteKind, Protocol):
    """A kind that moves bytes, carried out as an owned job (D168).

    The request plans — everything that answers at once, a taken name
    included — and the job transfers.
    """

    @property
    def doing(self) -> str:
        """What it is doing, for the footer: "Copying"."""
        ...

    @property
    def done(self) -> str:
        """What became of an item that arrived: "copied"."""
        ...

    async def plan(
        self, source: DataAdapter, destination: DataAdapter, request: PasteRun
    ) -> TransferPlan: ...

    async def transfer(
        self,
        source: DataAdapter,
        destination: DataAdapter,
        transfer: Transfer,
        report: TransferReport,
    ) -> None:
        """Carry it out, writing each item's outcome into `transfer`.

        Raises TransferStopped when nothing further could arrive.
        """
        ...

    def told(self, transfer: Transfer, stopped: str | None = None) -> str:
        """The job's one sentence: what arrived, and what did not."""
        ...


def offered(
    kind: PasteKind,
    *,
    available: bool,
    reason: str | None = None,
    name_conflict: bool = False,
    suggested_name: str | None = None,
    source_columns: list[FetchColumn] | None = None,
    target_columns: list[FetchColumn] | None = None,
    can_replace: bool | None = None,
) -> PasteOffer:
    """An offer of this kind, carrying what the kind always says about itself.

    `can_replace` narrows the kind's own answer for this selection: a folder's
    taken name is never replaced (D169).
    """
    return PasteOffer(
        kind=kind.name,
        title=kind.title,
        mode=kind.mode,
        available=available,
        reason=reason,
        name_conflict=name_conflict,
        converts=kind.converts,
        can_replace=kind.can_replace if can_replace is None else can_replace,
        changes_source=kind.changes_source,
        workflow=kind.workflow,
        suggested_name=suggested_name,
        source_columns=source_columns or [],
        target_columns=target_columns or [],
    )


def refused(kind: PasteKind, reason: str) -> PasteOffer:
    return offered(kind, available=False, reason=reason)


def counted(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"
