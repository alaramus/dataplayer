"""Finding a node by its name, below a level of the catalog.

A search is a read of the catalog rather than a query: what comes back is
`CatalogNode`s, the same ones a listing gives, so everything that draws a row,
opens a node or acts on one works unchanged (D76).

The text a person types is matched, never compiled: it is a case-insensitive
substring of a name, and there is no pattern language for a client to reach
into. That is D2c's rule about queries, said for the one input this capability
takes.
"""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from anyio import CapacityLimiter
from pydantic import BaseModel, ConfigDict, Field

from app.adapters.catalog import CatalogNode
from app.adapters.errors import ErrorKind

# How well a name matched the words, best first (D202). One rule for every
# place the words are looked for — a catalog, the application's own objects,
# what a later phase keeps — so a name is classed the same wherever it is
# found, and no numeric score is ever compared across places.
#
# `text` is a match in a body or in contents rather than in the name; `meaning`
# is reserved for a later phase, found by a model and not by the words.
MatchClass = Literal["exact", "prefix", "word", "substring", "text", "meaning"]
CLASS_ORDER: tuple[MatchClass, ...] = (
    "exact",
    "prefix",
    "word",
    "substring",
    "text",
    "meaning",
)

# More words than this are not a name somebody remembers.
MAX_WORDS = 8

# What separates the words of a name: `orders_2024.csv` is three of them.
_SEPARATORS = frozenset("_-./:")


def words_of(typed: str) -> tuple[str, ...]:
    """The words of what was typed: split on white space, case-folded, each once.

    Nothing is compiled — a `*` or a `%` is a character like any other (D2c).
    """
    found: list[str] = []
    for word in typed.split():
        folded = word.casefold()
        if folded not in found:
            found.append(folded)
    return tuple(found)


def holds_every_word(words: Sequence[str], text: str) -> bool:
    """Whether every word occurs in the text, case-folded, in any order."""
    folded = text.casefold()
    return bool(words) and all(word in folded for word in words)


def class_of_name(words: Sequence[str], name: str) -> MatchClass | None:
    """How well a name matches the words, or None when one of them is missing.

    `exact` is the name being the words; `prefix` the name beginning with the
    first of them; `word` every word beginning a word of the name; `substring`
    every word somewhere in it.
    """
    if not holds_every_word(words, name):
        return None
    folded = name.casefold()
    if folded == " ".join(words):
        return "exact"
    if folded.startswith(words[0]):
        return "prefix"
    starts = [
        index
        for index, character in enumerate(folded)
        if index == 0
        or folded[index - 1] in _SEPARATORS
        or folded[index - 1].isspace()
    ]
    if all(any(folded.startswith(word, start) for start in starts) for word in words):
        return "word"
    return "substring"


def class_rank(match_class: MatchClass) -> int:
    """The place of a class in the order, for sorting: lower is better."""
    return CLASS_ORDER.index(match_class)


def _never() -> bool:
    return False


@dataclass(frozen=True)
class SearchBounds:
    """When a search must stop, apart from what it looks for (D200).

    An argument of its own rather than a field of the request: a deadline is a
    moment in this process and a cancellation check is a callable, and neither
    is something a client sends. A walk asks `over()` between entries and stops
    with what it has; work on a worker thread runs under `limiter`, so searches
    cannot take the threads every other route uses.
    """

    # A `time.monotonic()` reading.
    deadline: float
    stopped: Callable[[], bool] = _never
    limiter: CapacityLimiter | None = None

    def over(self) -> bool:
        return self.stopped() or time.monotonic() >= self.deadline

    def left(self) -> float:
        """Seconds until the deadline, never below zero."""
        return max(0.0, self.deadline - time.monotonic())

    @classmethod
    def within(cls, seconds: float) -> SearchBounds:
        return cls(deadline=time.monotonic() + seconds)


# What a search may be asked for at most, and what it costs when nothing says.
# Named here and used by both the model and the route that fills it, so a
# ceiling is one number rather than two that agree today.
DEFAULT_MATCHES = 100
MAX_MATCHES = 500

# An empty needle would match everything, and a thousand characters is not a
# name.
MAX_QUERY_LENGTH = 200

# How much of the line a match was found on is shown. A log line or a minified
# document is one line and can be enormous; what a reader needs is enough of it
# to recognise the hit.
MAX_EXCERPT_CHARACTERS = 200


class NodeSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Where the search starts: the level being looked at, or the root.
    node_id: str | None = None
    query: str = Field(min_length=1, max_length=MAX_QUERY_LENGTH)
    limit: int = Field(default=DEFAULT_MATCHES, ge=1, le=MAX_MATCHES)


class NodeMatch(BaseModel):
    """One node that matched, and where it was found.

    `parent_id` is the source's own opaque id and is what the client sends back
    to stand there; `location` is the source's own wording for the same place,
    because a client that composed one would be reading an id apart (D21). The
    root of a connector has no name of its own, so it is the empty string —
    what the catalog draws there is the name of the connection.
    """

    model_config = ConfigDict(extra="forbid")

    node: CatalogNode
    parent_id: str | None = None
    location: str = ""
    # The line the words were found on, for a search that looked inside. A name
    # search leaves it empty: what matched is the name, and it is already the
    # row. Bounded by the source, because a log line can be a megabyte long.
    excerpt: str | None = None


class NodeSearchResult(BaseModel):
    """What was found, and whether that is all there was.

    A search that stopped at a ceiling says so rather than looking complete:
    "nothing else matched" and "I stopped looking" are different answers, and
    the difference is the only thing that tells somebody to narrow the words.
    """

    model_config = ConfigDict(extra="forbid")

    matches: list[NodeMatch] = Field(default_factory=list)
    complete: bool = True
    # Why it stopped, in the source's own words. Absent when it did not.
    notice: str | None = None
    # Set when the source failed part way: what was found before is still the
    # answer, and the kind is what lets a screen offer the way on — `locked`
    # asks for the key's passphrase (D147).
    error_kind: ErrorKind | None = None
