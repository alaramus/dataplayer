"""Source types, found by what they are called and what they say about themselves.

The type catalog's window asks this provider rather than keeping a copy of the
rule (S1). What matches is what the catalog shows: the title, the category,
the description, the guide's short lists (D183) — and the services this server
can start of a type, so that TimescaleDB finds PostgreSQL (D119). Those are
handed in by `app.services` at assembly: the engine imports no feature.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from anyio import to_thread

from app.adapters import registry
from app.guide import reader as guide
from app.search.models import Facts, Hit, ObjectsPlace, ObjectTarget, target_key
from app.search.providers import (
    Asked,
    Found,
    ProviderCell,
    best_of,
    name_match,
    ordered,
    text_match,
)


@dataclass(frozen=True)
class Startable:
    """A service this server can start, as it speaks about a source type."""

    adapter_type: str
    title: str
    description: str


@dataclass(frozen=True)
class _Described:
    name: str
    title: str
    category: str
    details: str
    body: str


class SourceTypes:
    place = ObjectsPlace(provider="source_types")
    title = "Source types"

    def __init__(self, startable: Callable[[], Sequence[Startable]]) -> None:
        self._startable = startable

    def cells(self) -> tuple[ProviderCell, ...]:
        return (ProviderCell(field="names", cost="instant"),)

    async def search(self, asked: Asked) -> Found:
        # The guide's pages are read from disk the first time.
        described = await to_thread.run_sync(self._described, limiter=asked.bounds.limiter)
        hits: list[Hit] = []
        for one in described:
            match = best_of(
                name_match(asked.words, one.title),
                name_match(asked.words, one.name),
                text_match(asked.words, "details", one.details),
                text_match(asked.words, "body", one.body),
            )
            if match is None:
                continue
            target = ObjectTarget(object_type="source_type", object_id=one.name)
            hits.append(
                Hit(
                    key=target_key(target),
                    target=target,
                    title=one.title,
                    detail=one.category,
                    facts=Facts(kind=one.name),
                    match=match,
                    open="source_type",
                )
            )
        return ordered(hits, asked.limit)

    def _described(self) -> list[_Described]:
        startable = list(self._startable())
        found: list[_Described] = []
        for adapter_type in registry.all_types():
            page = guide.page(guide.source_page_key(adapter_type.name))
            markdown = page.markdown if page is not None else ""
            services = [one for one in startable if one.adapter_type == adapter_type.name]
            category = registry.category_title(adapter_type.category)
            found.append(
                _Described(
                    name=adapter_type.name,
                    title=adapter_type.title,
                    category=category,
                    details=" · ".join([category, *(one.title for one in services)]),
                    body=" ".join(
                        [
                            adapter_type.description,
                            *guide.bullets(markdown, guide.CAN_SEE),
                            *guide.bullets(markdown, guide.CAN_CHANGE),
                            *(one.description for one in services),
                        ]
                    ),
                )
            )
        return found
