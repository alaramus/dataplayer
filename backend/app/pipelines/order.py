"""The order a pipeline's links run in (D177).

A card is read only after every link writing into it is done; links free to
go at once go by where they are drawn. Plain functions of the pipeline's
body: the screen draws the numbers this answers, and the run goes by them.
"""

import uuid
from dataclasses import dataclass

from app.pipelines.models import Card, Link, PipelineContent

# Why a link goes first where the arrows say nothing, in the order the
# position key compares them.
_BECAUSE = (
    "its card is furthest left",
    "its card is highest",
    "it starts from the highest row",
    "it was drawn first",
)


@dataclass(frozen=True)
class Placed:
    link: Link
    number: int
    # Set on the link a circle of links writing into each other was broken
    # at: which cards they are, and why this one goes first.
    circle: str | None = None


def _key(link: Link, index: int, cards: dict[uuid.UUID, Card]) -> tuple[float, float, int, int]:
    card = cards[link.source.card_id]
    row = next(
        (at for at, one in enumerate(card.rows) if one.node_id == link.source.node_id), 0
    )
    return (card.x, card.y, row, index)


def _reaching(start: uuid.UUID, edges: dict[uuid.UUID, set[uuid.UUID]]) -> set[uuid.UUID]:
    seen: set[uuid.UUID] = set()
    stack = [start]
    while stack:
        for after in edges[stack.pop()]:
            if after not in seen:
                seen.add(after)
                stack.append(after)
    return seen


def _names(links: list[Link], cards: dict[uuid.UUID, Card]) -> str:
    names = list(dict.fromkeys(cards[link.source.card_id].connector_name for link in links))
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def ordered(content: PipelineContent) -> list[Placed]:
    """Every link with its number, in the order a run carries them out."""
    cards = {card.id: card for card in content.cards}
    keys = {link.id: _key(link, index, cards) for index, link in enumerate(content.links)}
    links = {link.id: link for link in content.links}
    # What each link waits for: the links writing into the card it reads.
    waits = {
        link.id: {
            other.id
            for other in content.links
            if other.id != link.id and other.target.card_id == link.source.card_id
        }
        for link in content.links
    }
    left = set(links)
    placed: list[Placed] = []
    while left:
        ready = [one for one in left if not waits[one] & left]
        circle: str | None = None
        if ready:
            chosen = min(ready, key=keys.__getitem__)
        else:
            chosen, circle = _broken(left, waits, keys, links, cards)
        left.discard(chosen)
        placed.append(Placed(link=links[chosen], number=len(placed) + 1, circle=circle))
    return placed


def _broken(
    left: set[uuid.UUID],
    waits: dict[uuid.UUID, set[uuid.UUID]],
    keys: dict[uuid.UUID, tuple[float, float, int, int]],
    links: dict[uuid.UUID, Link],
    cards: dict[uuid.UUID, Card],
) -> tuple[uuid.UUID, str]:
    """Where to break the links left, which all wait on one another.

    Only a circle nothing outside it writes into can go: a link downstream of
    a circle waits for it however far left it is drawn.
    """
    after = {one: waits[one] & left for one in left}
    reach = {one: _reaching(one, after) for one in left}
    # Some circle waits on nothing outside it, or a link would be ready.
    circle = next(
        members
        for members in (
            {one} | {other for other in left if one in reach[other] and other in reach[one]}
            for one in sorted(left, key=keys.__getitem__)
        )
        if any(after[member] <= members for member in members)
    )
    free = sorted((one for one in circle if after[one] <= circle), key=keys.__getitem__)
    chosen = free[0]
    if len(free) > 1:
        because = next(
            reason
            for reason, mine, theirs in zip(_BECAUSE, keys[chosen], keys[free[1]], strict=True)
            if mine != theirs
        )
    else:
        because = "the others wait for links outside them as well"
    named = _names(sorted((links[one] for one in circle), key=lambda link: keys[link.id]), cards)
    return chosen, (
        f"{named} write into each other, so the arrows give no first link: "
        f"this one goes first because {because}"
    )
