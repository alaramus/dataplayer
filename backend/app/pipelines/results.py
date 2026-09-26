"""What the links of a pipeline make, foreseen (D178).

A link that makes something draws it as a row of the card it writes into,
and what that will be is its kind's answer about what the link reads: a
chain as far as it goes, each result described by the one before it, down to
a ticked row at its root. Nothing here reads a source; how a root is read is
the caller's.
"""

import uuid
from collections.abc import Callable

from app.adapters.catalog import NodeKind
from app.connectors.paste.models import Foreseen, ForeseenKind
from app.connectors.paste.registry import kind_named
from app.pipelines.models import Card, CardRow, LinkEnd, PipelineContent, ResultRow

_AS_NODE: dict[ForeseenKind, NodeKind] = {"file": "file", "folder": "directory", "table": "table"}

# How a ticked row starts a chain: by its label and what kind of node it is.
type Root = Callable[[Card, CardRow], Foreseen]


def foreseen_kind(kind: NodeKind | None) -> ForeseenKind:
    """A ticked node as a chain takes it: a place, a file, or rows."""
    if kind is None or kind in ("directory", "schema", "database"):
        return "folder"
    return "file" if kind == "file" else "table"


def by_label(card: Card, row: CardRow) -> Foreseen:
    """A ticked row as its card names it, nothing read."""
    del card
    return Foreseen(kind=foreseen_kind(row.kind), name=row.label)


def root_of(content: PipelineContent, end: LinkEnd) -> tuple[Card, CardRow] | None:
    """The ticked row a chain through this end starts from."""
    while end.made_by is not None:
        maker = content.link(end.made_by)
        if maker is None:
            return None
        end = maker.source
    card = content.card(end.card_id)
    row = None if card is None else next((one for one in card.rows if one.node_id == end.node_id), None)
    return None if card is None or row is None else (card, row)


class Foresight:
    """What each link makes and what each end holds, worked out once."""

    def __init__(self, content: PipelineContent, root: Root = by_label) -> None:
        self._content = content
        self._root = root
        self._made: dict[uuid.UUID, Foreseen | None] = {}

    def made(self, link_id: uuid.UUID) -> Foreseen | None:
        """What the link makes, or None when it makes nothing."""
        if link_id not in self._made:
            link = self._content.link(link_id)
            kind = None if link is None else kind_named(link.kind)
            read = None if link is None else self.at(link.source)
            self._made[link_id] = (
                None
                if link is None or kind is None or read is None or not kind.makes
                else kind.made(read, link.name, link.columns)
            )
        return self._made[link_id]

    def at(self, end: LinkEnd) -> Foreseen | None:
        """What an end holds: a ticked row as its root reads it, or a result."""
        if end.made_by is not None:
            return self.made(end.made_by)
        found = root_of(self._content, end)
        return None if found is None else self._root(*found)

    def rows(self) -> list[ResultRow]:
        """Every result, as a row of the card its link writes into."""
        return [
            ResultRow(
                link_id=link.id,
                card_id=link.target.card_id,
                name=made.name,
                kind=_AS_NODE[made.kind],
            )
            for link in self._content.links
            if (made := self.made(link.id)) is not None
        ]
