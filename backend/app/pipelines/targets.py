"""Where a row being dragged can go (D363).

Every row of the other cards, results (D178) and the tops of connections
included, answered with what a drop there would draw or why nothing would.
Asked first of the pair of connections (D174), reading no source, and only
then of each row, as a link being drawn is asked (`offers.Asking`). Past
`MAX_TARGET_ROWS` the rows are left unasked, and a screen asks a card's when
the pointer reaches it.
"""

import uuid

from pydantic import BaseModel, ConfigDict, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.resources import ResourceStore
from app.connectors.paste.registry import open_kinds
from app.core.problems import Problem
from app.core.translation import say
from app.pipelines.models import Card, LinkEnd, PipelineContent
from app.pipelines.offers import Asking
from app.pipelines.results import Foresight
from app.users.models import User

# Rows one drag asks of. Each is a kind's offer, and an offer may read both
# ends, so this is what bounds how long the tints take to arrive.
MAX_TARGET_ROWS = 400


class TargetsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: LinkEnd
    # Only this card's rows: the one the pointer reached on a canvas too
    # large to ask whole.
    card_id: uuid.UUID | None = None


class Target(BaseModel):
    end: LinkEnd
    # What a drop draws: the first operation that can run, by its title.
    kind: str | None = None
    title: str | None = None
    # Why nothing would; neither when the row was left unasked.
    reason: str | None = None


class Targets(BaseModel):
    targets: list[Target] = Field(default_factory=list)
    # Rows were left unasked: ask each card's as the pointer reaches it.
    partial: bool = False


def _key(end: LinkEnd) -> tuple[uuid.UUID, str | None, uuid.UUID | None]:
    return (end.card_id, end.node_id, end.made_by)


def _ends(content: PipelineContent, card: Card) -> list[LinkEnd]:
    ticked = [LinkEnd(card_id=card.id, node_id=row.node_id) for row in card.rows]
    made = [
        LinkEnd(card_id=row.card_id, made_by=row.link_id)
        for row in Foresight(content).rows()
        if row.card_id == card.id
    ]
    return ticked + made


async def targets(
    session: AsyncSession,
    user: User,
    resources: ResourceStore,
    content: PipelineContent,
    request: TargetsRequest,
) -> Targets:
    source = request.source
    source_card = content.card(source.card_id)
    if source_card is None:
        raise Problem(404, "pipelines.card_not_found")
    if not content.holds(source):
        raise Problem(404, "pipelines.row_not_found")
    asking = Asking(session, user, resources, content, strict=False)
    drawn = {_key(link.target) for link in content.links if _key(link.source) == _key(source)}
    answered: list[Target] = []
    asked: list[LinkEnd] = []
    from_here = await asking.adapter(source_card)
    for card in content.cards:
        if card.id == source_card.id or (request.card_id is not None and card.id != request.card_id):
            continue
        ends = _ends(content, card)
        if card.connector_id == source_card.connector_id:
            # Inside one connection is its catalog's own Paste (D74).
            reason = say("Same connection")
            answered.extend(Target(end=end, reason=reason) for end in ends)
            continue
        there = await asking.adapter(card)
        if from_here is None or there is None:
            # A card that cannot be read already says so; it takes nothing.
            continue
        if not open_kinds(*from_here, *there):
            reason = say("Nothing can go from here into this connection")
            answered.extend(Target(end=end, reason=reason) for end in ends)
            continue
        for end in ends:
            if _key(end) in drawn:
                answered.append(Target(end=end, reason=say("Already linked")))
            else:
                asked.append(end)
    if len(asked) > MAX_TARGET_ROWS:
        return Targets(targets=answered, partial=True)
    for end in asked:
        offers = await asking.offers(source, end)
        # A taken name is a choice the panel asks, not a reason against.
        usable = next((offer for offer in offers if offer.available or offer.name_conflict), None)
        if usable is not None:
            answered.append(Target(end=end, kind=usable.kind, title=say(usable.title)))
            continue
        refused = next((offer.reason for offer in offers if offer.reason), None)
        answered.append(Target(end=end, reason=refused or say("Nothing can go here")))
    return Targets(targets=answered)
