"""Every kind of paste between connections, in the order a list shows them (D164)."""

from app.adapters.protocol import DataAdapter
from app.connectors.paste.files import FileCopy, FileMove
from app.connectors.paste.kinds import PasteKind, refused
from app.connectors.paste.models import PasteKindName, PasteOffer
from app.connectors.paste.relation_csv import RelationCsv
from app.connectors.paste.rows import RowsIntoRelation, RowsNewRelation
from app.connectors.paste.tables import TablesCopy
from app.core.access import Access, at_least

KINDS: tuple[PasteKind, ...] = (
    FileCopy(),
    FileMove(),
    RelationCsv(),
    TablesCopy(),
    RowsNewRelation(),
    RowsIntoRelation(),
)


def kind_named(name: PasteKindName) -> PasteKind:
    return next(kind for kind in KINDS if kind.name == name)


def outranked(offers: list[PasteOffer]) -> list[PasteOffer]:
    """The offers left once each that can run has stood in for the ones it
    outranks (D182): Paste opens the window that fits what was copied."""
    replaced = {
        name for offer in offers if offer.available for name in kind_named(offer.kind).outranks
    }
    return [offer for offer in offers if offer.kind not in replaced]


def open_kinds(
    source: DataAdapter,
    source_access: Access,
    destination: DataAdapter,
    destination_access: Access,
) -> list[PasteKind]:
    """What one connection can give another that this person may run (D174).

    Asked of what the two are and the person's standing on each, never of a
    node: no source is read to answer it.
    """
    return [
        kind
        for kind in KINDS
        if kind.pipelines
        and kind.serves(source, destination)
        and at_least(source_access, kind.source_requires)
        and at_least(destination_access, kind.destination_requires)
    ]


def short_of(
    kind: PasteKind, source_access: Access, destination_access: Access
) -> PasteOffer | None:
    """The kind refused for what it needs of each end beyond reading, or None."""
    if not at_least(destination_access, kind.destination_requires):
        return refused(
            kind, f"This needs {kind.destination_requires} access to this connection"
        )
    if not at_least(source_access, kind.source_requires):
        return refused(
            kind, f"This needs {kind.source_requires} access to the copied connection"
        )
    return None
