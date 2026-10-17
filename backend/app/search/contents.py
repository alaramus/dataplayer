"""Words looked for inside the files of chosen connections, as a job (S7).

Reading every file below a folder is minutes where a name is milliseconds, so
it is never a cell of an answer (D200): it is owned work, one at a time per
person, that can be watched in the footer and stopped (D81, D95).

The words, the places chosen and what was found are held in this process's
memory, keyed by the job, for a while after it ends, and never written to the
job's row: a row is read by `GET /jobs`, kept for a day on screen and never
encrypted. The row carries counts; its step and message never quote the words
(D200). A restart forgets the matches, and the job is ended as interrupted
like any other (D81, D124).
"""

import asyncio
import logging
import threading
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from anyio import CapacityLimiter
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.errors import ErrorKind
from app.adapters.protocol import AdapterError, NodeNotFound, SearchesContents
from app.adapters.resources import BorrowingStore, ResourceStore
from app.adapters.search import (
    DEFAULT_MATCHES,
    MAX_MATCHES,
    MAX_QUERY_LENGTH,
    MAX_WORDS,
    NodeSearchRequest,
    NodeSearchResult,
    SearchBounds,
    words_of,
)
from app.core.config import settings
from app.core.db import async_session_maker
from app.core.logs import record_failure, with_ref
from app.core.translation import N_, say
from app.jobs import crud as job_crud
from app.jobs.models import Job, JobKind, JobPublic, is_terminal, public
from app.jobs.runner import JobFailed, JobHandler, JobRunner, Progress
from app.realtime.topics import TopicSet
from app.search import connections
from app.search.excerpts import segments
from app.search.models import MIN_WORD_CHARACTERS, Hit, Match, NodeTarget, SkipReason
from app.search.nodes import adapter_of, node_hit, searches_contents
from app.search.providers import VisibleConnection
from app.users.models import User

logger = logging.getLogger(__name__)

KIND: JobKind = "search.contents"
SEARCHING = N_("searching inside files")

# Connections one search may be asked to look in, as the field asks at most.
MAX_CONNECTIONS = 20
# Matches kept from one connection (D76's default) and from all of them.
PER_CONNECTION = DEFAULT_MATCHES
TOTAL_MATCHES = MAX_MATCHES
# Ended searches of a person kept as jobs; older ones are removed (S7).
KEEP_FINISHED = 20

# What a grantee reads of a key that is locked (D199).
_LOCKED_BY_OWNER = N_("Locked by its owner")

# The job's sentences, by whether one connection was searched and one match
# found: English counts in the singular and the plural.
_STOPPED = {
    (True, True): N_("Stopped after {searched} of {places} connection; {found} match found"),
    (True, False): N_("Stopped after {searched} of {places} connection; {found} matches found"),
    (False, True): N_("Stopped after {searched} of {places} connections; {found} match found"),
    (False, False): N_("Stopped after {searched} of {places} connections; {found} matches found"),
}
_FOUND = {
    (True, True): N_("{found} match found in {places} connection"),
    (True, False): N_("{found} matches found in {places} connection"),
    (False, True): N_("{found} match found in {places} connections"),
    (False, False): N_("{found} matches found in {places} connections"),
}
_NOTHING_FOUND = {
    True: N_("Nothing found in {places} connection"),
    False: N_("Nothing found in {places} connections"),
}

PlaceStatus = Literal["waiting", "complete", "stopped", "failed", "skipped"]


class ContentsRequest(BaseModel):
    """What to look for, and in which of the person's connections."""

    model_config = ConfigDict(extra="forbid")

    words: str = Field(max_length=MAX_QUERY_LENGTH)
    connector_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_CONNECTIONS)

    @field_validator("words")
    @classmethod
    def _words(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < MIN_WORD_CHARACTERS:
            raise ValueError(f"A search needs at least {MIN_WORD_CHARACTERS} characters")
        if len(words_of(stripped)) > MAX_WORDS:
            raise ValueError(f"A search takes at most {MAX_WORDS} words")
        return stripped


class ContentsPlace(BaseModel):
    """One chosen connection, and what became of looking inside it."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    connector_id: uuid.UUID
    name: str
    status: PlaceStatus = "waiting"
    reason: SkipReason | None = None
    # The source's own words about where it stopped (D76).
    notice: str | None = None
    error_kind: ErrorKind | None = None
    message: str | None = None
    found: int = 0


class ContentsAnswer(BaseModel):
    """What a search inside files found, while it is held (S7)."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    job_id: uuid.UUID
    # False once the matches have expired or the server has restarted.
    held: bool
    finished: bool
    # The owner's own words, so the tab can say what it shows.
    words: str | None = None
    places: list[ContentsPlace] = Field(default_factory=list)
    hits: list[Hit] = Field(default_factory=list)


class ContentsBusy(Exception):
    """The person already has a search inside files running."""


class PlaceNotFound(Exception):
    """A connection the person has no standing on, answered as an unknown id."""


@dataclass
class _Held:
    owner_id: uuid.UUID
    typed: str
    words: tuple[str, ...]
    places: dict[uuid.UUID, ContentsPlace]
    hits: list[Hit] = field(default_factory=list)
    # When it ended, on the monotonic clock; None while it runs.
    ended: float | None = None


class ContentsMemory:
    """The words and matches of searches inside files, in this process only.

    Keyed by job id and dropped a while after the job ends; one more thing a
    second process would not share (D124).
    """

    def __init__(self, held_seconds: float) -> None:
        self._held_seconds = held_seconds
        self._held: dict[uuid.UUID, _Held] = {}

    @property
    def held_seconds(self) -> float:
        return self._held_seconds

    def hold(
        self, job_id: uuid.UUID, owner_id: uuid.UUID, typed: str,
        chosen: Iterable[VisibleConnection],
    ) -> None:
        self._expire()
        self._held[job_id] = _Held(
            owner_id=owner_id,
            typed=typed,
            words=words_of(typed),
            places={
                one.id: ContentsPlace(connector_id=one.id, name=one.name) for one in chosen
            },
        )

    def get(self, job_id: uuid.UUID) -> _Held | None:
        self._expire()
        return self._held.get(job_id)

    def ended(self, job_id: uuid.UUID) -> None:
        held = self._held.get(job_id)
        if held is not None and held.ended is None:
            held.ended = time.monotonic()

    def forget(self, job_ids: Iterable[uuid.UUID]) -> None:
        for job_id in job_ids:
            self._held.pop(job_id, None)

    def _expire(self) -> None:
        now = time.monotonic()
        gone = [
            job_id
            for job_id, held in self._held.items()
            if held.ended is not None and now - held.ended >= self._held_seconds
        ]
        self.forget(gone)


def _counts(held: _Held | None, connections_count: int, held_seconds: float) -> dict[str, Any]:
    """What the job's row carries: counts, never the words or the places."""
    places = list(held.places.values()) if held is not None else []
    return {
        "connections": connections_count,
        "searched": sum(1 for place in places if place.status != "waiting"),
        "found": len(held.hits) if held is not None else 0,
        "held_seconds": held_seconds,
    }


def _number(count: int) -> str:
    return f"{count:,}"


def _failed(kind: ErrorKind, message: str) -> NodeSearchResult:
    return NodeSearchResult(complete=False, notice=message, error_kind=kind)


class SearchContents:
    """The job's handler: each chosen connection in turn, under one deadline."""

    kind: ClassVar[JobKind] = KIND
    steps: ClassVar[tuple[str, ...]] = (SEARCHING,)

    def __init__(self, memory: ContentsMemory, resources: ResourceStore | None) -> None:
        self._memory = memory
        self._resources = resources
        # Made on first use, by the loop that runs the jobs.
        self._threads: CapacityLimiter | None = None

    async def carry_out(self, job: Job, progress: Progress) -> str:
        held = self._memory.get(job.id)
        if held is None:
            raise JobFailed(say("Its words are no longer held; search again"))
        try:
            return await self._search(job, held, progress)
        except JobFailed:
            raise
        except Exception as failure:
            # Private: a failure's own text may quote the words (D200, D184).
            ref = record_failure(
                logger, f"Search inside files {job.id} failed", failure, private=True
            )
            raise JobFailed(with_ref(say("The search could not be completed"), ref)) from None
        finally:
            self._memory.ended(job.id)

    def stopped_message(self, job: Job) -> str | None:
        held = self._memory.get(job.id)
        if held is None:
            return None
        places = list(held.places.values())
        searched = sum(1 for place in places if place.status != "waiting")
        return say(
            _STOPPED[(len(places) == 1, len(held.hits) == 1)],
            searched=_number(searched),
            places=_number(len(places)),
            found=_number(len(held.hits)),
        )

    async def _search(self, job: Job, held: _Held, progress: Progress) -> str:
        await progress.reached(SEARCHING)
        deadline = time.monotonic() + settings.SEARCH_CONTENTS_SECONDS
        async with async_session_maker() as session:
            owner = await session.get(User, job.owner_id)
            if owner is None:
                raise JobFailed(say("Its owner is no longer here"))
            # Read again: a grant may have gone since the search was started.
            visible = {one.id: one for one in await connections.visible(session, owner)}
        total = len(held.places)
        for connector_id, place in held.places.items():
            connection = visible.get(connector_id)
            room = TOTAL_MATCHES - len(held.hits)
            if connection is None:
                place.status, place.message = "failed", say("No longer yours to read")
            elif not connection.enabled:
                place.status, place.reason = "skipped", "switched_off"
            elif not searches_contents(connection):
                place.status, place.reason = "skipped", "cannot_search"
            elif room <= 0 or time.monotonic() >= deadline:
                place.status, place.reason = "skipped", "not_asked"
                place.notice = (
                    say("Not searched: {count} matches were already found", count=_number(TOTAL_MATCHES))
                    if room <= 0 else say("Not searched: the search ran out of time")
                )
            else:
                result = await self._asked(connection, held, min(PER_CONNECTION, room), deadline)
                _record(held, connection, result)
            job.parameters = _counts(held, total, self._memory.held_seconds)
            await progress.reached(SEARCHING)
        return _told(held)

    async def _asked(
        self, connection: VisibleConnection, held: _Held, limit: int, deadline: float
    ) -> NodeSearchResult:
        """One connection's files, under the owner's credentials (D33).

        Stop ends the walk at its next entry and keeps what it found: the walk
        runs on a thread the cancellation cannot reach, so it is shielded and
        told to stop through its bounds instead.
        """
        stop = threading.Event()
        bounds = SearchBounds(deadline=deadline, stopped=stop.is_set, limiter=self._limiter())
        store = BorrowingStore(self._resources)
        try:
            try:
                adapter = adapter_of(connection, store)
            except Exception:
                # Never the text: a validation error quotes the options.
                return _failed("config", say("The settings of this connection cannot be read"))
            if not isinstance(adapter, SearchesContents):
                return _failed("config", say("This connection cannot be searched inside its files"))
            walk = asyncio.ensure_future(
                adapter.search_contents(NodeSearchRequest(query=held.typed, limit=limit), bounds)
            )
            try:
                return await asyncio.shield(walk)
            except asyncio.CancelledError:
                stop.set()
                try:
                    _record(held, connection, await walk, stopped=True)
                except Exception:  # noqa: BLE001 - stopping; what failed is not news
                    pass
                raise
        except NodeNotFound:
            return _failed("config", say("Where this search started is gone"))
        except ValueError as refusal:
            return _failed("config", str(refusal))
        except AdapterError as failure:
            return _failed(failure.error_kind, failure.message)
        finally:
            await asyncio.shield(store.aclose())

    def _limiter(self) -> CapacityLimiter:
        if self._threads is None:
            self._threads = CapacityLimiter(settings.SEARCH_THREADS)
        return self._threads


def _record(
    held: _Held, connection: VisibleConnection, result: NodeSearchResult, *, stopped: bool = False
) -> None:
    place = held.places[connection.id]
    room = TOTAL_MATCHES - len(held.hits)
    hits = [
        node_hit(
            connection,
            match,
            Match(
                field="contents",
                match_class="text",
                line=match.line,
                excerpt=segments(match.excerpt or match.node.name, held.words),
            ),
        )
        for match in result.matches[: max(room, 0)]
    ]
    held.hits.extend(hits)
    place.found = len(hits)
    if result.error_kind is not None:
        place.status = "failed"
        place.error_kind = result.error_kind
        place.message = (
            say(_LOCKED_BY_OWNER)
            if result.error_kind == "locked" and connection.access != "own"
            else result.notice
        )
    else:
        place.status = "stopped" if stopped or not result.complete else "complete"
        place.notice = say("Stopped on request") if stopped else result.notice


def _told(held: _Held) -> str:
    """The job's message: counts only, never the words."""
    places = list(held.places.values())
    found = len(held.hits)
    one = len(places) == 1
    said = (
        say(_FOUND[(one, found == 1)], found=_number(found), places=_number(len(places)))
        if found else say(_NOTHING_FOUND[one], places=_number(len(places)))
    )
    missed = sum(1 for place in places if place.status in ("failed", "skipped"))
    if missed:
        said = say("{said}; {missed} could not be searched", said=said, missed=missed)
    return said


def handlers(memory: ContentsMemory, resources: ResourceStore | None) -> dict[str, JobHandler]:
    handler: JobHandler = SearchContents(memory, resources)
    return {handler.kind: handler}


async def start(
    session: AsyncSession,
    user: User,
    body: ContentsRequest,
    *,
    memory: ContentsMemory,
    runner: JobRunner,
    topics: TopicSet | None,
) -> JobPublic:
    """Admit a search inside files, hold its words, and start it.

    Raises `PlaceNotFound` for a connection without standing (D199) and
    `ContentsBusy` while another of the person's is unfinished.
    """
    visible = {one.id: one for one in await connections.visible(session, user)}
    chosen = list(dict.fromkeys(body.connector_ids))
    if any(one not in visible for one in chosen):
        raise PlaceNotFound
    try:
        job = await job_crud.admit_within(
            session,
            owner_id=user.id,
            kind=KIND,
            limit=1,
            subject_id=None,
            step_count=len(SearchContents.steps),
            parameters=_counts(None, len(chosen), memory.held_seconds),
        )
    except job_crud.TooManyActive:
        raise ContentsBusy from None
    started = public(job)
    memory.hold(job.id, user.id, body.words, [visible[one] for one in chosen])
    gone = await job_crud.forget_finished_of_owner(
        session, kind=KIND, owner_id=user.id, keep=KEEP_FINISHED
    )
    await session.commit()
    memory.forget(gone)
    await runner.launch(job, topics)
    return started


async def answer(
    session: AsyncSession, user: User, job_id: uuid.UUID, memory: ContentsMemory
) -> ContentsAnswer | None:
    """What one of the person's searches found; None when it is not theirs.

    Matches from a connection the person can no longer read are dropped.
    """
    job = await job_crud.get_for_owner(session, job_id, user.id)
    if job is None or job.kind != KIND:
        return None
    finished = is_terminal(job.state)
    held = memory.get(job_id)
    if held is None or held.owner_id != user.id:
        return ContentsAnswer(job_id=job_id, held=False, finished=finished)
    readable = {
        one.id for one in await connections.visible(session, user) if one.enabled
    }
    return ContentsAnswer(
        job_id=job_id,
        held=True,
        finished=finished,
        words=held.typed,
        places=[
            place.model_copy() for place in held.places.values()
            if place.connector_id in readable
        ],
        hits=[
            hit for hit in held.hits
            if isinstance(hit.target, NodeTarget) and hit.target.connector_id in readable
        ],
    )
