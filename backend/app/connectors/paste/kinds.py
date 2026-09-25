"""What one kind of paste between connections has to say about itself (D164)."""

from typing import Protocol

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

    async def run(
        self, source: DataAdapter, destination: DataAdapter, request: PasteRun
    ) -> PasteResult: ...


def offered(
    kind: PasteKind,
    *,
    available: bool,
    reason: str | None = None,
    name_conflict: bool = False,
    suggested_name: str | None = None,
    source_columns: list[FetchColumn] | None = None,
    target_columns: list[FetchColumn] | None = None,
) -> PasteOffer:
    """An offer of this kind, carrying what the kind always says about itself."""
    return PasteOffer(
        kind=kind.name,
        title=kind.title,
        available=available,
        reason=reason,
        name_conflict=name_conflict,
        converts=kind.converts,
        can_replace=kind.can_replace,
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
