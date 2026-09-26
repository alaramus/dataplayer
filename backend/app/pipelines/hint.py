"""Every link that could be drawn among the rows of a pipeline (D176).

Asked first of the connections, by what they are and the person's standing
(D174), and only then of the rows of the pairs that can meet at all: each
kind's own offer, as the pair window asks it (D167).
"""

import uuid

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.protocol import DataAdapter
from app.adapters.resources import ResourceStore
from app.connectors.access import resolve_adapter
from app.connectors.paste.kinds import PasteKind
from app.connectors.paste.models import PastePair
from app.connectors.paste.registry import open_kinds
from app.core.access import Access
from app.pipelines.models import Card, CardRow, LinkEnd, PipelineContent
from app.users.models import User

# Pairs of rows one hint asks about. Each is a kind's offer, and an offer may
# read both ends, so this is what bounds how long the button takes.
MAX_HINT_PAIRS = 400


class HintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The card selected, which a canvas too large to hint whole is narrowed to.
    card_id: uuid.UUID | None = None


class HintLink(BaseModel):
    source: LinkEnd
    target: LinkEnd
    # What it would do, in the kinds' own words.
    titles: list[str] = Field(min_length=1)


class Hint(BaseModel):
    links: list[HintLink]
    # Why fewer than all were asked, when fewer were.
    notice: str | None = None


type _Pair = tuple[Card, CardRow, Card, CardRow, list[PasteKind]]


async def hint(
    session: AsyncSession,
    user: User,
    resources: ResourceStore,
    content: PipelineContent,
    card_id: uuid.UUID | None,
) -> Hint:
    adapters: dict[uuid.UUID, tuple[DataAdapter, Access] | None] = {}
    for connector_id in {card.connector_id for card in content.cards}:
        try:
            adapters[connector_id] = await resolve_adapter(
                session, connector_id, user, resources, requires="read"
            )
        except HTTPException:
            # A card that cannot be read already says so; it takes no hint.
            adapters[connector_id] = None
    drawn = {
        (link.source.card_id, link.source.node_id, link.target.card_id, link.target.node_id)
        for link in content.links
    }
    pairs: list[_Pair] = []
    for source in content.cards:
        for target in content.cards:
            ends = (adapters.get(source.connector_id), adapters.get(target.connector_id))
            if source.connector_id == target.connector_id or ends[0] is None or ends[1] is None:
                continue
            kinds = open_kinds(ends[0][0], ends[0][1], ends[1][0], ends[1][1])
            if not kinds:
                continue
            pairs.extend(
                (source, row, target, place, kinds)
                for row in source.rows
                if row.node_id is not None
                for place in target.rows
                if (source.id, row.node_id, target.id, place.node_id) not in drawn
            )
    notice: str | None = None
    if len(pairs) > MAX_HINT_PAIRS:
        if card_id is None:
            return Hint(
                links=[],
                notice="This canvas holds too many rows to hint at once: select a card first",
            )
        pairs = [pair for pair in pairs if card_id in (pair[0].id, pair[2].id)]
        notice = "Only the links of the selected card are hinted"
        if len(pairs) > MAX_HINT_PAIRS:
            pairs = pairs[:MAX_HINT_PAIRS]
            notice = f"Only the first {MAX_HINT_PAIRS} pairs of rows of the selected card are hinted"
    links: list[HintLink] = []
    for source, row, target, place, kinds in pairs:
        source_adapter = adapters[source.connector_id]
        target_adapter = adapters[target.connector_id]
        if source_adapter is None or target_adapter is None or row.node_id is None:
            continue
        titles: list[str] = []
        for kind in kinds:
            offer = await kind.offer(
                source_adapter[0],
                target_adapter[0],
                PastePair(
                    source_connector_id=source.connector_id,
                    source_node_ids=[row.node_id],
                    mode=kind.mode,
                    destination_node_id=place.node_id,
                    target_node_id=place.node_id,
                ),
            )
            # A taken name is a choice the panel asks, not a reason against.
            if offer.available or offer.name_conflict:
                titles.append(kind.title)
        if titles:
            links.append(
                HintLink(
                    source=LinkEnd(card_id=source.id, node_id=row.node_id),
                    target=LinkEnd(card_id=target.id, node_id=place.node_id),
                    titles=titles,
                )
            )
    return Hint(links=links, notice=notice)
