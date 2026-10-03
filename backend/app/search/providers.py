"""What the search asks: one provider per kind of thing the application keeps (D197).

A provider answers words with hits for its cells. It lives with its feature and
is handed to the engine when the application is assembled, the way the job
runner is handed its handlers (D81): the engine imports no feature. Those for
what sits below the engine — connection rows, SSH keys, the guide, the source
types — live in this package.

A provider applies its feature's own access rule inside its own query (D199);
the engine passes the person and never filters afterwards, which would lose
results and leak counts.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.errors import ErrorKind
from app.adapters.search import (
    SearchBounds,
    class_of_name,
    class_rank,
    holds_every_word,
)
from app.core.access import Access
from app.search.excerpts import segments
from app.search.models import (
    BrowserPlace,
    ConnectionsPlace,
    Cost,
    Hit,
    Match,
    MatchedField,
    ObjectsPlace,
    ObjectType,
    RecentTarget,
    SearchField,
    SearchMode,
    SkipReason,
)
from app.users.models import User


@dataclass(frozen=True)
class VisibleConnection:
    """A connection the person may see, read once per answer (D199)."""

    id: uuid.UUID
    name: str
    adapter_type: str
    enabled: bool
    access: Access
    owner_id: uuid.UUID
    # Whose it is, when it is not the person's: the address the grant names.
    owner_email: str | None
    # The non-secret options, for the host and database a row is found by.
    config: dict[str, Any]
    # Encrypted as stored, from the same row: what a connection is asked with
    # (D199). Decrypted only for a connection that is asked.
    secrets: bytes = field(default=b"", repr=False)


@dataclass(frozen=True)
class Asked:
    """What one cell asks of a provider."""

    user: User
    typed: str
    words: tuple[str, ...]
    field: SearchField
    mode: SearchMode
    limit: int
    bounds: SearchBounds
    # The application cells of one answer share it and run one after another:
    # they are instant, and a session is not shared between tasks.
    session: AsyncSession
    visible: Sequence[VisibleConnection] = ()
    # What was opened from the search lately, newest first (S6).
    recent: Sequence[RecentTarget] = ()
    # Open tabs and saved tab groups, which only the browser knows (S9).
    browser: Sequence[BrowserPlace] = ()


@dataclass(frozen=True)
class Found:
    """What a provider answers for one cell."""

    hits: list[Hit] = field(default_factory=list)
    # False when it stopped before looking everywhere it was asked to.
    complete: bool = True
    notice: str | None = None
    # Whether asking this cell alone, with its full limit, would find more.
    more: bool = False
    # A source that failed, reduced to a kind and a safe sentence; what it
    # found before is still in `hits` (D201).
    error_kind: ErrorKind | None = None
    message: str | None = None
    # The person owns what failed, so a locked key may be unlocked by them.
    owned: bool = False
    # Not asked after all, though planned: what was learnt of the place while
    # the answer ran, such as its server not answering a cell before this one.
    skipped: SkipReason | None = None
    since: datetime | None = None


@dataclass(frozen=True)
class ProviderCell:
    field: SearchField
    cost: Cost


class Searches(Protocol):
    """What the engine asks of any provider once its cells are planned."""

    async def search(self, asked: Asked) -> Found: ...


@runtime_checkable
class ApplicationProvider(Protocol):
    """One kind of application object, found by asking the application."""

    @property
    def place(self) -> ConnectionsPlace | ObjectsPlace: ...

    @property
    def title(self) -> str:
        """The heading of its group, in the words a person reads."""
        ...

    def cells(self) -> Sequence[ProviderCell]:
        """Its cells and what each costs, stated without asking anybody."""
        ...

    async def search(self, asked: Asked) -> Found: ...


@runtime_checkable
class Recalls(Protocol):
    """A provider that names its objects again by id, for an empty search (S6).

    The ids come from the browser, so a provider answers only those its own
    rule lets the person see, in its own query (D199), and drops the rest
    without a word.
    """

    @property
    def recalls(self) -> frozenset[ObjectType]:
        """The object types it answers for."""
        ...

    async def recall(
        self, asked: Asked, object_type: ObjectType, ids: Sequence[str]
    ) -> list[Hit]: ...


def recalled(title: str) -> Match:
    """What a thing named again matched: nothing was typed, so nothing is marked.

    Every one of no words is in the name, which is the weakest class a name
    has, so a thing named again is never a best match.
    """
    return Match(field="name", match_class="substring", excerpt=segments(title, ()))


def uuids_of(ids: Sequence[str]) -> list[uuid.UUID]:
    """The ids that are ids at all; the browser kept them, and may be wrong."""
    found: list[uuid.UUID] = []
    for one in ids:
        try:
            found.append(uuid.UUID(one))
        except ValueError:
            continue
    return found


def name_match(words: Sequence[str], name: str) -> Match | None:
    """A match on the name, classed by the one rule (D202), or none."""
    found = class_of_name(words, name)
    if found is None:
        return None
    return Match(field="name", match_class=found, excerpt=segments(name, words))


def text_match(words: Sequence[str], where: MatchedField, text: str) -> Match | None:
    """A match in something other than the name: class `text` (D202)."""
    if not holds_every_word(words, text):
        return None
    return Match(field=where, match_class="text", excerpt=segments(text, words))


def best_of(*matches: Match | None) -> Match | None:
    """The best of several ways one thing matched, by class; the first on a tie."""
    present = [one for one in matches if one is not None]
    if not present:
        return None
    return min(present, key=lambda one: class_rank(one.match_class))


def ordered(hits: list[Hit], limit: int, *, ranked: bool = False) -> Found:
    """A cell's hits in the order a group shows them, and whether more were left.

    Class first, then the provider's own rank where it has one — the order the
    hits arrive in, `ranked` — and otherwise the name (D202).
    """
    if not ranked:
        hits.sort(key=lambda hit: hit.title.casefold())
    hits.sort(key=lambda hit: class_rank(hit.match.match_class))
    return Found(hits=hits[:limit], complete=True, more=len(hits) > limit)
