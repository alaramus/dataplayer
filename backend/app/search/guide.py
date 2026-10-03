"""The user's guide, found by a page's title, its headings and its text (D183)."""

import re
from collections.abc import Sequence

from anyio import to_thread

from app.guide import reader
from app.search.models import (
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

_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MARKERS = re.compile(r"^\s*(?:#+|[-*>]|\d+\.)\s*")


def _plain(markdown: str) -> str:
    """The words of a page without the marks Markdown writes them with."""
    lines = []
    for line in markdown.splitlines():
        text = _MARKERS.sub("", _LINK.sub(r"\1", line))
        lines.append(text.replace("`", "").replace("**", ""))
    return " ".join(" ".join(lines).split())


def _headings(markdown: str) -> str:
    return " · ".join(
        line.lstrip("#").strip()
        for line in markdown.splitlines()
        if line.startswith("## ") or line.startswith("### ")
    )


class GuidePages:
    place = ObjectsPlace(provider="guide")
    title = "Guide"
    recalls: frozenset[ObjectType] = frozenset({"guide_page"})

    def cells(self) -> tuple[ProviderCell, ...]:
        return (ProviderCell(field="names", cost="instant"),)

    async def search(self, asked: Asked) -> Found:
        # Read from disk once per process, on a thread the first time.
        pages = await to_thread.run_sync(reader.pages, limiter=asked.bounds.limiter)
        hits: list[Hit] = []
        for page in pages.values():
            match = best_of(
                name_match(asked.words, page.title),
                text_match(asked.words, "details", _headings(page.markdown)),
                text_match(asked.words, "body", _plain(page.markdown)),
            )
            if match is None:
                continue
            hits.append(_hit(page.key, page.title, match))
        return ordered(hits, asked.limit)

    async def recall(
        self, asked: Asked, object_type: ObjectType, ids: Sequence[str]
    ) -> list[Hit]:
        pages = await to_thread.run_sync(reader.pages, limiter=asked.bounds.limiter)
        return [
            _hit(key, pages[key].title, recalled(pages[key].title))
            for key in ids
            if key in pages
        ]


def _hit(key: str, title: str, match: Match) -> Hit:
    target = ObjectTarget(object_type="guide_page", object_id=key)
    return Hit(
        key=target_key(target),
        target=target,
        title=title,
        detail="Guide",
        facts=Facts(kind="guide_page"),
        match=match,
        open="guide_page",
    )
