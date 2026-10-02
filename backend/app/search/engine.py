"""One engine that plans, asks, bounds and merges (D197, D200, D201).

An answer is a stream of lines: the plan first, then one line per cell as it
finishes, the best matches once the cheap cells are in, and a closing line.
One cell's failure never fails the answer, and nothing is cached in this
phase: a typed query rarely repeats, and a cache would have to refuse answers
cut by time (D200).

Process-local, like the job runner: what is in flight is a task, and a task
does not cross a process (D124).
"""

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field

from anyio import CapacityLimiter
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.search import (
    MAX_MATCHES,
    SearchBounds,
    class_rank,
    words_of,
)
from app.core.config import settings
from app.core.db import async_session_maker
from app.core.logs import record_failure, with_ref
from app.search import connections
from app.search.models import (
    BestLine,
    CellLine,
    ConnectionPlace,
    ConnectionsPlace,
    EndLine,
    Group,
    Hit,
    Lane,
    ObjectsPlace,
    Outcome,
    PlanLine,
    RecentTarget,
    SearchLine,
    SearchRequest,
    cell_key,
)
from app.search.models import Cell as SearchCell
from app.search.plan import (
    CONNECTIONS_RANK,
    PROVIDER_RANKS,
    Candidate,
    Planned,
    plan,
)
from app.search.providers import ApplicationProvider, Asked, Found, VisibleConnection
from app.users.models import User

logger = logging.getLogger(__name__)

# How many rows a group shows while typing, and a cell in the Search tab; a
# cell asked alone — "More in this connection" — gets D76's ceiling.
ROWS_TYPING = 5
ROWS_SEARCH = 50
ROWS_ALONE = MAX_MATCHES

BEST_MATCHES = 3


class ScopeNotFound(Exception):
    """A place named by the browser that the person has no standing on.

    Answered exactly as an unknown id is (D199): the id space is not an oracle.
    """


@dataclass(frozen=True)
class SearchLimits:
    """What one answer may spend, each a setting with a default and a ceiling."""

    typing_seconds: float
    cheap_seconds: float
    costly_seconds: float
    total_seconds: float
    max_connections: int
    parallel_connections: int
    threads: int

    @classmethod
    def from_settings(cls) -> SearchLimits:
        return cls(
            typing_seconds=settings.SEARCH_TYPING_SECONDS,
            cheap_seconds=settings.SEARCH_CHEAP_SECONDS,
            costly_seconds=settings.SEARCH_COSTLY_SECONDS,
            total_seconds=settings.SEARCH_TOTAL_SECONDS,
            max_connections=settings.SEARCH_MAX_CONNECTIONS,
            parallel_connections=settings.SEARCH_PARALLEL_CONNECTIONS,
            threads=settings.SEARCH_THREADS,
        )


@dataclass
class _Shared:
    task: asyncio.Task[Found]
    waiters: int = 0


class _Inflight:
    """Identical cells asked by one person while one is running share one task.

    Never between people (D200). The task is cancelled when the last answer
    waiting for it goes, so a query nobody waits for does not run on.
    """

    def __init__(self) -> None:
        self._shared: dict[tuple[object, ...], _Shared] = {}

    async def run(
        self,
        key: tuple[object, ...],
        start: Callable[[], Awaitable[Found]],
        seconds: float,
    ) -> Found:
        shared = self._shared.get(key)
        if shared is None or shared.task.done():
            shared = _Shared(task=asyncio.ensure_future(start()))
            self._shared[key] = shared
            entry = shared

            def forget(_: asyncio.Task[Found]) -> None:
                if self._shared.get(key) is entry:
                    del self._shared[key]

            shared.task.add_done_callback(forget)
        shared.waiters += 1
        try:
            async with asyncio.timeout(seconds):
                return await asyncio.shield(shared.task)
        finally:
            shared.waiters -= 1
            if shared.waiters == 0 and not shared.task.done():
                shared.task.cancel()


class SearchEngine:
    """The search's one engine, built once by the application."""

    def __init__(
        self, providers: Sequence[ApplicationProvider], limits: SearchLimits
    ) -> None:
        self._providers: list[ApplicationProvider] = list(providers)
        self.limits = limits
        self.limiter = CapacityLimiter(limits.threads)
        self.inflight = _Inflight()
        self._answers: dict[tuple[uuid.UUID, Lane], Answer] = {}

    @contextmanager
    def providing(self, provider: ApplicationProvider) -> Iterator[None]:
        """One more provider for as long as this lasts. For tests."""
        self._providers.append(provider)
        try:
            yield
        finally:
            self._providers.remove(provider)

    async def prepare(
        self, session: AsyncSession, user: User, request: SearchRequest
    ) -> Answer:
        """Decide everything that can be decided before anything is asked.

        Raises ScopeNotFound for a place the person cannot see, before the
        first line is written: once a stream has begun, its status is spent.
        """
        visible = await connections.visible(session, user)
        by_id = {connection.id: connection for connection in visible}
        only = request.only
        for place in only or []:
            if isinstance(place, ConnectionPlace) and place.connector_id not in by_id:
                raise ScopeNotFound()
        candidates = [
            candidate
            for provider in self._providers
            for candidate in _candidates_of(provider)
            if only is None or any(_same_place(candidate.cell, wanted) for wanted in only)
        ]
        planned = plan(
            candidates,
            mode=request.mode,
            insist=request.insist,
            max_connections=self.limits.max_connections,
        )
        alone = only is not None and len(only) == 1
        return Answer(
            engine=self,
            user=user,
            request=request,
            planned=planned,
            visible=visible,
            providers={provider.place.model_dump_json(): provider for provider in self._providers},
            rows=ROWS_ALONE if alone else ROWS_TYPING if request.mode == "typing" else ROWS_SEARCH,
        )

    def claim(self, answer: Answer) -> None:
        """One answer in flight per person and lane: a newer one ends the older."""
        key = (answer.user.id, answer.request.lane)
        previous = self._answers.get(key)
        if previous is not None and previous is not answer:
            previous.supersede()
        self._answers[key] = answer

    def release(self, answer: Answer) -> None:
        key = (answer.user.id, answer.request.lane)
        if self._answers.get(key) is answer:
            del self._answers[key]


def _candidates_of(provider: ApplicationProvider) -> list[Candidate]:
    place = provider.place
    if isinstance(place, ConnectionsPlace):
        group = Group(key="connections", title=provider.title, rank=CONNECTIONS_RANK)
    else:
        group = Group(
            key=f"objects:{place.provider}",
            title=provider.title,
            rank=PROVIDER_RANKS[place.provider],
        )
    return [
        Candidate(cell=SearchCell(place=place, field=one.field), cost=one.cost, group=group)
        for one in provider.cells()
    ]


def _same_place(cell: SearchCell, wanted: object) -> bool:
    place = cell.place
    if isinstance(wanted, ConnectionsPlace):
        return isinstance(place, ConnectionsPlace)
    if isinstance(wanted, ObjectsPlace):
        return isinstance(place, ObjectsPlace) and place.provider == wanted.provider
    if isinstance(wanted, ConnectionPlace):
        return isinstance(place, ConnectionPlace) and place.connector_id == wanted.connector_id
    return False


@dataclass(frozen=True)
class _Finished:
    key: str
    outcome: Outcome
    hits: list[Hit] = field(default_factory=list)


_SUPERSEDED = object()


class Answer:
    """One answer: its plan, its tasks and the lines it writes."""

    def __init__(
        self,
        *,
        engine: SearchEngine,
        user: User,
        request: SearchRequest,
        planned: list[Planned],
        visible: list[VisibleConnection],
        providers: dict[str, ApplicationProvider],
        rows: int,
    ) -> None:
        self.engine = engine
        self.user = user
        self.request = request
        self.planned = planned
        self.visible = visible
        self._providers = providers
        self._rows = rows
        self._words = words_of(request.words)
        self._queue: asyncio.Queue[_Finished | object] = asyncio.Queue()
        self._tasks: list[asyncio.Task[None]] = []
        self._over = False
        self._started = time.monotonic()

    def supersede(self) -> None:
        self._stop()
        self._queue.put_nowait(_SUPERSEDED)

    def _stop(self) -> None:
        self._over = True
        for task in self._tasks:
            task.cancel()

    def _stopped(self) -> bool:
        return self._over

    async def lines(self) -> AsyncIterator[SearchLine]:
        self.engine.claim(self)
        try:
            async for line in self._lines():
                yield line
        finally:
            self._stop()
            self.engine.release(self)

    async def _lines(self) -> AsyncIterator[SearchLine]:
        yield PlanLine(mode=self.request.mode, cells=[one.cell for one in self.planned])
        pending: dict[str, Planned] = {}
        for one in self.planned:
            if one.skipped is not None:
                yield CellLine(key=one.cell.key, outcome=one.skipped)
            else:
                pending[one.cell.key] = one
        if not pending:
            yield BestLine(hits=[])
            yield EndLine()
            return

        self._start(list(pending.values()))
        cheap = {key for key, one in pending.items() if one.cell.cost in ("instant", "cheap")}
        best: list[tuple[int, Hit]] = []
        best_sent = False
        sent: set[str] = set()
        asked = len(pending)
        complete = True
        found_any = False
        # A guard over everything: no answer outlives its total by more than
        # this, whatever a provider does with its deadline.
        ends = self._started + self.engine.limits.total_seconds + 1.0

        while pending:
            if not best_sent and not cheap:
                yield BestLine(hits=self._best(best))
                best_sent = True
            try:
                item = await asyncio.wait_for(
                    self._queue.get(), max(0.0, ends - time.monotonic())
                )
            except TimeoutError:
                for key in list(pending):
                    yield CellLine(key=key, outcome=self._late(pending.pop(key)))
                complete = False
                break
            if item is _SUPERSEDED:
                yield EndLine(superseded=True)
                return
            assert isinstance(item, _Finished)
            planned = pending.pop(item.key, None)
            if planned is None:
                continue
            unique = [hit for hit in item.hits if hit.key not in sent]
            sent.update(hit.key for hit in unique)
            complete = complete and item.outcome.status == "complete"
            found_any = found_any or bool(unique)
            if item.key in cheap:
                cheap.discard(item.key)
                best.extend(
                    (planned.cell.group.rank, hit)
                    for hit in unique
                    if hit.match.match_class in ("exact", "prefix")
                )
            yield CellLine(key=item.key, outcome=item.outcome, hits=unique)

        if not best_sent:
            yield BestLine(hits=self._best(best))
        yield EndLine(nothing_found=complete and not found_any, asked=asked)

    def _best(self, found: list[tuple[int, Hit]]) -> list[Hit]:
        """Up to three exact or prefix hits: by class, recency, then group (D202)."""
        recency = {
            _recent_key(one): index for index, one in enumerate(self.request.recent)
        }
        ranked = sorted(
            found,
            key=lambda pair: (
                class_rank(pair[1].match.match_class),
                recency.get(pair[1].key, len(recency)),
                pair[0],
            ),
        )
        return [hit for _, hit in ranked[:BEST_MATCHES]]

    # --- asking ---------------------------------------------------------------

    def _deadline(self, planned: Planned) -> float:
        limits = self.engine.limits
        if self.request.mode == "typing":
            return self._started + limits.typing_seconds
        if planned.cell.cost in ("instant", "cheap"):
            return self._started + limits.cheap_seconds
        return min(
            time.monotonic() + limits.costly_seconds,
            self._started + limits.total_seconds,
        )

    def _late(self, planned: Planned) -> Outcome:
        limits = self.engine.limits
        seconds = (
            limits.typing_seconds
            if self.request.mode == "typing"
            else limits.cheap_seconds
            if planned.cell.cost in ("instant", "cheap")
            else limits.costly_seconds
        )
        return Outcome(way="live", status="late", deadline_seconds=seconds)

    def _start(self, cells: list[Planned]) -> None:
        together = [
            one
            for one in cells
            if one.cell.cost == "instant"
            and not isinstance(one.cell.cell.place, ConnectionPlace)
        ]
        alone = [one for one in cells if one not in together]
        if together:
            self._tasks.append(asyncio.create_task(self._application(together)))
        for one in alone:
            self._tasks.append(asyncio.create_task(self._alone(one)))

    def _asked(self, planned: Planned, session: AsyncSession) -> Asked:
        return Asked(
            user=self.user,
            typed=self.request.words,
            words=self._words,
            field=planned.cell.cell.field,
            mode=self.request.mode,
            limit=self._rows,
            bounds=SearchBounds(
                deadline=self._deadline(planned),
                stopped=self._stopped,
                limiter=self.engine.limiter,
            ),
            session=session,
            visible=self.visible,
        )

    def _provider(self, planned: Planned) -> ApplicationProvider:
        return self._providers[planned.cell.cell.place.model_dump_json()]

    async def _application(self, cells: list[Planned]) -> None:
        """The instant application cells, one after another in one session."""
        async with async_session_maker() as session:
            for planned in cells:
                asked = self._asked(planned, session)
                left = asked.bounds.left()
                if left <= 0:
                    self._finish(planned, self._late(planned))
                    continue
                try:
                    async with asyncio.timeout(left):
                        found = await self._provider(planned).search(asked)
                except TimeoutError:
                    self._finish(planned, self._late(planned))
                    # The session may hold a statement that was cancelled; the
                    # rest share its deadline and are late as well.
                    for rest in cells[cells.index(planned) + 1 :]:
                        self._finish(rest, self._late(rest))
                    return
                except Exception as failure:
                    self._finish(planned, self._failed(failure))
                    continue
                self._finish(planned, _outcome_of(found), found.hits)

    async def _alone(self, planned: Planned) -> None:
        """A cell in a task and a session of its own, shared with an identical one."""

        async def start() -> Found:
            async with async_session_maker() as session:
                return await self._provider(planned).search(self._asked(planned, session))

        key = (self.user.id, cell_key(planned.cell.cell), self._words, self._rows)
        seconds = max(0.0, self._deadline(planned) - time.monotonic())
        try:
            found = await self.engine.inflight.run(key, start, seconds)
        except TimeoutError:
            self._finish(planned, self._late(planned))
            return
        except Exception as failure:
            self._finish(planned, self._failed(failure))
            return
        self._finish(planned, _outcome_of(found), found.hits)

    def _failed(self, failure: Exception) -> Outcome:
        # Private: the words somebody typed may be in what a provider raised.
        ref = record_failure(logger, "A search provider failed", failure, private=True)
        return Outcome(
            way="live",
            status="failed",
            error_kind="unknown",
            message=with_ref("This could not be searched", ref),
        )

    def _finish(self, planned: Planned, outcome: Outcome, hits: list[Hit] | None = None) -> None:
        self._queue.put_nowait(_Finished(key=planned.cell.key, outcome=outcome, hits=hits or []))


def _outcome_of(found: Found) -> Outcome:
    return Outcome(
        way="live",
        status="complete" if found.complete else "stopped",
        notice=found.notice,
        more=found.more,
    )


def _recent_key(recent: RecentTarget) -> str:
    if recent.kind == "connection":
        return f"connection:{recent.connector_id}"
    if recent.kind == "node":
        return f"node:{recent.connector_id}:{recent.node_id}:"
    return f"object:{recent.object_type}:{recent.object_id}"
