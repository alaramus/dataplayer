"""Every kind of paste between connections, in the order a list shows them (D164)."""

from app.connectors.paste.files import FileCopy, FileMove
from app.connectors.paste.kinds import PasteKind
from app.connectors.paste.models import PasteKindName
from app.connectors.paste.relation_csv import RelationCsv
from app.connectors.paste.rows import RowsIntoRelation, RowsNewRelation

KINDS: tuple[PasteKind, ...] = (
    FileCopy(),
    FileMove(),
    RelationCsv(),
    RowsNewRelation(),
    RowsIntoRelation(),
)


def kind_named(name: PasteKindName) -> PasteKind:
    return next(kind for kind in KINDS if kind.name == name)
