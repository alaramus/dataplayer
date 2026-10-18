"""Titles declared once in English and worded where they are handed out (D226).

A vocabulary — the types a column may take, the ways a node opens — is a
module-level list, read by more than one screen and by the agent. It keeps its
English, marked `N_` where it is written; what leaves the source is a copy in
the language of the request.
"""

from collections.abc import Iterable, Mapping
from typing import Any, Protocol, Self

from app.core.translation import say


class Titled(Protocol):
    """A Pydantic model with a `title`."""

    @property
    def title(self) -> str: ...

    def model_copy(
        self, *, update: Mapping[str, Any] | None = None, deep: bool = False
    ) -> Self: ...


def worded_titles[M: Titled](items: Iterable[M]) -> list[M]:
    return [item.model_copy(update={"title": say(item.title)}) for item in items]
