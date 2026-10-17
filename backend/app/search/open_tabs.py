"""Open tabs, windows and tab groups, which only the browser knows (S9, D94).

Their titles arrive in the request, bounded, and are classed here by the one
word rule, so a tab and a table are found alike (D202). Nothing of them is
stored.
"""

from collections.abc import Sequence

from app.core.translation import N_, say
from app.search.models import (
    BrowserPlace,
    Facts,
    Hit,
    Match,
    ObjectsPlace,
    ObjectTarget,
    ObjectType,
    target_key,
)
from app.search.providers import (
    Asked,
    Found,
    ProviderCell,
    best_of,
    name_match,
    ordered,
    recalled,
    text_match,
)

_KIND_WORDS = {"tab": N_("Open tab"), "tab_group": N_("Tab group")}


class OpenTabs:
    place = ObjectsPlace(provider="open_tabs")
    title = N_("Open tabs")
    # The browser's tabs: the agent sees a tab only when it is attached (D133).
    offered_to_agent = False
    recalls: frozenset[ObjectType] = frozenset({"tab", "tab_group"})

    def cells(self) -> tuple[ProviderCell, ...]:
        return (ProviderCell(field="names", cost="instant"),)

    async def search(self, asked: Asked) -> Found:
        hits: list[Hit] = []
        for place in asked.browser:
            match = best_of(
                name_match(asked.words, place.title),
                None
                if place.detail is None
                else text_match(asked.words, "details", place.detail),
            )
            if match is not None:
                hits.append(_hit(place, match))
        return ordered(hits, asked.limit)

    async def recall(
        self, asked: Asked, object_type: ObjectType, ids: Sequence[str]
    ) -> list[Hit]:
        # A tab opened from the search and closed since is not named again.
        wanted = set(ids)
        return [
            _hit(place, recalled(place.title))
            for place in asked.browser
            if place.object_type == object_type and place.object_id in wanted
        ]


def _hit(place: BrowserPlace, match: Match) -> Hit:
    target = ObjectTarget(object_type=place.object_type, object_id=place.object_id)
    return Hit(
        key=target_key(target),
        target=target,
        title=place.title,
        detail=place.detail or say(_KIND_WORDS[place.object_type]),
        facts=Facts(kind=place.object_type),
        match=match,
        open=place.object_type,
    )
