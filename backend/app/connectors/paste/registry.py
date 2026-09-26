"""Every kind of paste between connections, in the order a list shows them (D164)."""

from app.adapters.protocol import DataAdapter
from app.connectors.paste.files import FileCopy, FileMove
from app.connectors.paste.kinds import PasteKind
from app.connectors.paste.models import PasteKindName
from app.connectors.paste.relation_csv import RelationCsv
from app.connectors.paste.rows import RowsIntoRelation, RowsNewRelation
from app.core.access import Access, at_least

KINDS: tuple[PasteKind, ...] = (
    FileCopy(),
    FileMove(),
    RelationCsv(),
    RowsNewRelation(),
    RowsIntoRelation(),
)


def kind_named(name: PasteKindName) -> PasteKind:
    return next(kind for kind in KINDS if kind.name == name)


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
        if kind.serves(source, destination)
        and at_least(source_access, kind.source_requires)
        and at_least(destination_access, kind.destination_requires)
    ]
