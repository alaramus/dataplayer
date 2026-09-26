"""Every link that could be drawn among the rows of a pipeline (D176).

Asked first of the connections, by what they are and the person's standing
(D174), and only then of the rows of the pairs that can meet at all, as a
link being drawn is asked (`offers.Asking`). What a link makes is a row of
its card here too (D178).
"""

import uuid
from collections import defaultdict

from pydantic import BaseModel, ConfigDict, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.resources import ResourceStore
from app.connectors.paste.registry import open_kinds
from app.pipelines.models import Card, LinkEnd, PipelineContent
from app.pipelines.offers import Asking
from app.pipelines.results import Foresight
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


type _Pair = tuple[Card, LinkEnd, Card, LinkEnd]


def _key(end: LinkEnd) -> tuple[uuid.UUID, str | None, uuid.UUID | None]:
    return (end.card_id, end.node_id, end.made_by)


async def hint(
    session: AsyncSession,
    user: User,
    resources: ResourceStore,
    content: PipelineContent,
    card_id: uuid.UUID | None,
) -> Hint:
    asking = Asking(session, user, resources, content, strict=False)
    results: dict[uuid.UUID, list[LinkEnd]] = defaultdict(list)
    for row in Foresight(content).rows():
        results[row.card_id].append(LinkEnd(card_id=row.card_id, made_by=row.link_id))

    def ends(card: Card) -> list[LinkEnd]:
        ticked = [LinkEnd(card_id=card.id, node_id=row.node_id) for row in card.rows]
        return ticked + results[card.id]

    drawn = {(_key(link.source), _key(link.target)) for link in content.links}
    pairs: list[_Pair] = []
    for source in content.cards:
        for target in content.cards:
            if source.connector_id == target.connector_id:
                continue
            ends_read = (await asking.adapter(source), await asking.adapter(target))
            if ends_read[0] is None or ends_read[1] is None:
                # A card that cannot be read already says so; it takes no hint.
                continue
            if not open_kinds(*ends_read[0], *ends_read[1]):
                continue
            pairs.extend(
                (source, start, target, end)
                for start in ends(source)
                if start.node_id is not None or start.made_by is not None
                for end in ends(target)
                if (_key(start), _key(end)) not in drawn
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
    for _source, start, _target, end in pairs:
        offers = await asking.offers(start, end)
        # A taken name is a choice the panel asks, not a reason against.
        titles = [offer.title for offer in offers if offer.available or offer.name_conflict]
        if titles:
            links.append(HintLink(source=start, target=end, titles=titles))
    return Hint(links=links, notice=notice)
