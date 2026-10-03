"""Saved queries, as the search finds them: the Favorites group (D204).

Titles are plaintext, read newest first and matched here, while typing. Bodies
are ciphertext (D63): matched only on Enter, through the library's own bound —
the newest QUERY_SEARCH_MAX_DOCUMENTS — on a worker thread under the search's
limiter, asking between documents whether to stop. Query history is not a
provider: a run is a record of what was executed (D204).

Handed to the search at assembly: the engine sits below queries and imports no
feature (D197).
"""

import asyncio
import functools
import time
import uuid
import weakref
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from anyio import CapacityLimiter, to_thread
from sqlmodel import col, select

from app.adapters.search import holds_every_word
from app.core.config import settings
from app.queries import crud
from app.queries.content import body_of, preview_of
from app.queries.models import QueryDocument
from app.search.excerpts import segments
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
    name_match,
    ordered,
    recalled,
    uuids_of,
)

UNTITLED = "Untitled query"

# Far above what one person keeps; a bound so that the query is bounded too.
MAX_TITLES = 1000

# How long one thread decrypts before it hands its token back. The search's
# limiter is shared with the instant cells, which have only the typing
# deadline; a walk holding a token for its whole costly deadline would make
# them late, and every application cell after them with them.
SLICE_SECONDS = 0.05


@dataclass(frozen=True)
class _Found:
    """What a body search keeps of a document: never the body."""

    document_id: uuid.UUID
    title: str
    connector_id: uuid.UUID | None
    changed_at: datetime | None
    match: Match


class _Turns:
    """One decryption per person at a time, given back when its thread ends.

    A cancelled task does not stop the thread it started: the thread runs on
    until it next asks whether to stop. So the turn is held by the thread, not
    by the task, and a newer search waits those few documents rather than
    decrypting beside an older one.
    """

    def __init__(self) -> None:
        self._locks: weakref.WeakValueDictionary[uuid.UUID, asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )

    async def run[T](
        self, person: uuid.UUID, work: Callable[[], T], limiter: CapacityLimiter | None
    ) -> T:
        lock = self._locks.setdefault(person, asyncio.Lock())
        await lock.acquire()
        thread = asyncio.ensure_future(to_thread.run_sync(work, limiter=limiter))

        def done(finished: asyncio.Future[T]) -> None:
            lock.release()
            # Read here, or a failure after its search was superseded would be
            # logged as never retrieved; the search that waited has its outcome.
            if not finished.cancelled():
                finished.exception()

        thread.add_done_callback(done)
        return await asyncio.shield(thread)


class SavedQueries:
    place = ObjectsPlace(provider="saved_queries")
    title = "Favorites"
    # The query library never travels (D133).
    offered_to_agent = False
    recalls: frozenset[ObjectType] = frozenset({"saved_query"})

    def __init__(self) -> None:
        self._turns = _Turns()

    def cells(self) -> tuple[ProviderCell, ...]:
        return (
            ProviderCell(field="names", cost="instant"),
            # Never while typing: a keystroke would decrypt up to 500 MiB.
            ProviderCell(field="contents", cost="costly"),
        )

    async def search(self, asked: Asked) -> Found:
        if asked.field == "contents":
            return await self._bodies(asked)
        return await self._titles(asked)

    async def _titles(self, asked: Asked) -> Found:
        # Matched here, not in SQL: `lower` is not case folding — `ß`, a final
        # `ς`, and nothing past ASCII under the C locale — so a filter there
        # would drop titles the one rule finds (D202).
        statement = (
            select(
                QueryDocument.id,
                QueryDocument.title,
                QueryDocument.connector_id,
                QueryDocument.updated_at,
            )
            .where(
                QueryDocument.owner_id == asked.user.id,
                col(QueryDocument.title).is_not(None),
            )
            .order_by(col(QueryDocument.updated_at).desc(), col(QueryDocument.id))
            .limit(MAX_TITLES + 1)
        )
        rows = (await asked.session.exec(statement)).all()
        names = _connection_names(asked)
        hits: list[Hit] = []
        for document_id, title, connector_id, changed_at in rows[:MAX_TITLES]:
            if title is None:
                continue
            match = name_match(asked.words, title)
            if match is not None:
                hits.append(
                    _hit(document_id, title, connector_id, changed_at, names, match)
                )
        cut = ordered(hits, asked.limit)
        if len(rows) > MAX_TITLES:
            return Found(
                hits=cut.hits,
                complete=False,
                notice=(
                    f"Only the newest {MAX_TITLES} saved queries are searched"
                    " by their title"
                ),
                more=cut.more,
            )
        return cut

    async def _bodies(self, asked: Asked) -> Found:
        documents, left_out = await crud.newest(asked.session, owner=asked.user)
        words = asked.words
        over = asked.bounds.over
        found: list[_Found] = []
        start = 0
        # A slice at a time, each its own turn and its own token, so the
        # instant cells queued on the limiter go between two slices.
        while start < len(documents) and not over():
            part, read = await self._turns.run(
                asked.user.id,
                functools.partial(_holding, documents[start:], words, over),
                asked.bounds.limiter,
            )
            found.extend(part)
            start += read
        read_all = start >= len(documents)
        names = _connection_names(asked)
        hits = [
            _hit(one.document_id, one.title, one.connector_id, one.changed_at, names, one.match)
            for one in found
        ]
        # Newest first, the library's own order, among matches of one class.
        cut = ordered(hits, asked.limit, ranked=True)
        if not read_all:
            return Found(
                hits=cut.hits,
                complete=False,
                notice="Stopped before every saved query was read",
                more=cut.more,
            )
        if left_out:
            return Found(
                hits=cut.hits,
                complete=False,
                notice=(
                    f"Only the newest {settings.QUERY_SEARCH_MAX_DOCUMENTS} saved"
                    " queries are searched by their text"
                ),
                more=cut.more,
            )
        return cut

    async def recall(
        self, asked: Asked, object_type: ObjectType, ids: Sequence[str]
    ) -> list[Hit]:
        wanted = uuids_of(ids)
        if not wanted:
            return []
        documents = list(
            (
                await asked.session.exec(
                    select(QueryDocument).where(
                        QueryDocument.owner_id == asked.user.id,
                        col(QueryDocument.id).in_(wanted),
                    )
                )
            ).all()
        )
        # A draft is named by its first line, which is ciphertext.
        titles = await to_thread.run_sync(
            lambda: [_title_of(document) for document in documents],
            limiter=asked.bounds.limiter,
        )
        names = _connection_names(asked)
        return [
            _hit(
                document.id,
                title,
                document.connector_id,
                document.updated_at,
                names,
                recalled(title),
            )
            for document, title in zip(documents, titles, strict=True)
        ]


def _holding(
    documents: Sequence[QueryDocument],
    words: Sequence[str],
    over: Callable[[], bool],
) -> tuple[list[_Found], int]:
    """The documents whose body holds every word, and how many were read.

    Blocking: decrypts, and asks between documents whether to stop; reads at
    least one unless told to stop, and no more once its slice is spent. What is
    kept of a match is its title and one line, never the body.
    """
    found: list[_Found] = []
    ends = time.monotonic() + SLICE_SECONDS
    for read, document in enumerate(documents):
        if over() or (read > 0 and time.monotonic() >= ends):
            return found, read
        body = body_of(document)
        if not holds_every_word(words, body):
            continue
        number, line = _line_of(body, words)
        found.append(
            _Found(
                document_id=document.id,
                title=document.title or preview_of(body) or UNTITLED,
                connector_id=document.connector_id,
                changed_at=document.updated_at,
                match=Match(
                    field="body",
                    match_class="text",
                    line=number,
                    excerpt=segments(line, words),
                ),
            )
        )
    return found, len(documents)


def _line_of(body: str, words: Sequence[str]) -> tuple[int, str]:
    """The first line holding every word, else the first holding one of them."""
    first: tuple[int, str] | None = None
    for number, line in enumerate(body.splitlines(), start=1):
        folded = line.casefold()
        if all(word in folded for word in words):
            return number, line
        if first is None and any(word in folded for word in words):
            first = (number, line)
    return first or (1, "")


def _title_of(document: QueryDocument) -> str:
    """Blocking for a draft: its first line is read from the body."""
    return document.title or preview_of(body_of(document)) or UNTITLED


def _connection_names(asked: Asked) -> Mapping[uuid.UUID, str]:
    """The connections the person may see. One they no longer may is never
    named, the library's own rule for a document's connection (D63)."""
    return {connection.id: connection.name for connection in asked.visible}


def _hit(
    document_id: uuid.UUID,
    title: str,
    connector_id: uuid.UUID | None,
    changed_at: datetime | None,
    names: Mapping[uuid.UUID, str],
    match: Match,
) -> Hit:
    target = ObjectTarget(object_type="saved_query", object_id=str(document_id))
    connection = None if connector_id is None else names.get(connector_id)
    return Hit(
        key=target_key(target),
        target=target,
        title=title,
        detail="Saved query" if connection is None else f"Saved query · {connection}",
        facts=Facts(kind="saved_query", changed_at=changed_at),
        match=match,
        open="saved_query",
    )
