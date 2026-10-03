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
import threading
import time
import uuid
from collections.abc import (
    AsyncIterator,
    Awaitable,
    Callable,
    Iterator,
    Mapping,
    Sequence,
)
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Literal

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
    SearchMode,
    SearchRequest,
    cell_key,
    recent_target,
    target_key,
)
from app.search.models import Cell as SearchCell
from app.search.nodes import ConnectionSearch
from app.search.plan import (
    CONNECTIONS_RANK,
    PROVIDER_RANKS,
    Candidate,
    Planned,
    plan,
)
from app.search.providers import (
    ApplicationProvider,
    Asked,
    Found,
    Searches,
    VisibleConnection,
)
from app.search.recent import RecentlyOpened
from app.users.models import User

logger = logging.getLogger(__name__)

# How many rows a group shows while typing, and a cell in the Search tab; a
# cell asked alone — "More in this connection" — gets D76's ceiling.
ROWS_TYPING = 5
ROWS_SEARCH = 50
ROWS_ALONE = MAX_MATCHES

BEST_MATCHES = 3

# How much less time an answer accepts to share a task already in flight.
JOIN_SLACK_SECONDS = 0.25


# Who an answer is for. The agent is offered less (D199, S10).
Audience = Literal["person", "agent"]


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
    # What its starter asked it for; the bounds it runs under are those.
    mode: SearchMode
    deadline: float
    # Set when the last answer waiting for it went. An event, as work on a
    # worker thread reads it and outlives the cancellation of its task.
    abandoned: threading.Event
    waiters: int = 0

    def joinable(self, mode: SearchMode, deadline: float) -> bool:
        # A task told to stop is not done until its cancellation has run, and
        # an answer that joined it then would end with it. An answer asked a
        # moment later has a deadline a moment later: within the slack it
        # joins, or two lanes asking at once would never share a task.
        return (
            not self.task.done()
            and not self.task.cancelling()
            and not self.abandoned.is_set()
            and self.mode == mode
            and self.deadline >= deadline - JOIN_SLACK_SECONDS
        )


class _Inflight:
    """Identical cells asked by one person while one is running share one task.

    Never between people (D200), and only a task asked in the same mode with
    no less time, since its bounds are its starter's: an answer that comes
    later has a later deadline, so it gets a task of its own and waits its
    turn rather than inherit less time. The task is cancelled when the last
    answer waiting for it goes, so a query nobody waits for does not run on.
    """

    def __init__(self) -> None:
        self._shared: dict[tuple[object, ...], _Shared] = {}

    async def run(
        self,
        key: tuple[object, ...],
        start: Callable[[Callable[[], bool]], Awaitable[Found]],
        *,
        mode: SearchMode,
        deadline: float,
    ) -> Found:
        """The cell's answer, or TimeoutError at `deadline`.

        `start` is handed the shared task's own stop check, not the check of
        the answer that started it: that answer may go while another still
        waits. Raises TimeoutError as well when the shared task ended
        cancelled by nobody waiting here: to this answer the cell did not
        answer.
        """
        shared = self._shared.get(key)
        if shared is None or not shared.joinable(mode, deadline):
            abandoned = threading.Event()
            shared = _Shared(
                task=asyncio.ensure_future(start(abandoned.is_set)),
                mode=mode,
                deadline=deadline,
                abandoned=abandoned,
            )
            self._shared[key] = shared
            entry = shared

            def forget(_: asyncio.Task[Found]) -> None:
                if self._shared.get(key) is entry:
                    del self._shared[key]

            shared.task.add_done_callback(forget)
        shared.waiters += 1
        try:
            async with asyncio.timeout(max(0.0, deadline - time.monotonic())):
                return await asyncio.shield(shared.task)
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is None or current.cancelling():
                raise
            raise TimeoutError from None
        finally:
            shared.waiters -= 1
            if shared.waiters == 0 and not shared.task.done():
                shared.abandoned.set()
                shared.task.cancel()


class SearchEngine:
    """The search's one engine, built once by the application."""

    def __init__(
        self,
        providers: Sequence[ApplicationProvider],
        limits: SearchLimits,
        *,
        inside: ConnectionSearch | None = None,
    ) -> None:
        self._providers: list[ApplicationProvider] = list(providers)
        # An empty search asks this alone, and it asks the providers above
        # to name their own objects again (S6).
        self._recent = RecentlyOpened(self._providers)
        self.limits = limits
        # What is inside the connections, asked per answer (S4).
        self.inside = inside
        self.limiter = CapacityLimiter(limits.threads)
        self.inflight = _Inflight()
        self._answers: dict[tuple[uuid.UUID, Lane], Answer] = {}

    @contextmanager
    def providing(self, provider: ApplicationProvider) -> Iterator[None]:
        """This provider in place of the one asking its place, for as long as
        this lasts. For tests."""
        at = next(
            (index for index, one in enumerate(self._providers) if one.place == provider.place),
            None,
        )
        replaced = None if at is None else self._providers.pop(at)
        self._providers.append(provider)
        try:
            yield
        finally:
            self._providers.remove(provider)
            if at is not None and replaced is not None:
                self._providers.insert(at, replaced)

    async def prepare(
        self,
        session: AsyncSession,
        user: User,
        request: SearchRequest,
        *,
        audience: Audience = "person",
    ) -> Answer:
        """Decide everything that can be decided before anything is asked.

        Raises ScopeNotFound for a place the person cannot see, before the
        first line is written: once a stream has begun, its status is spent.

        For the agent (S10) only the providers offered to it are asked, only
        connections whose owner allows transfer are seen at all (D135), and
        only those in `request.context` are asked what they hold.
        """
        visible = await connections.visible(session, user)
        if audience == "agent":
            visible = [connection for connection in visible if connection.allows_transfer]
        by_id = {connection.id: connection for connection in visible}
        only = request.only
        for place in only or []:
            if isinstance(place, ConnectionPlace) and place.connector_id not in by_id:
                raise ScopeNotFound()
        # An empty search asks what was opened lately, and nothing else (S6).
        asking: list[ApplicationProvider] = (
            self._providers if request.words else [self._recent]
        )
        inside_of = visible
        if audience == "agent":
            asking = [provider for provider in asking if provider.offered_to_agent]
            inside_of = [one for one in visible if one.id in request.context]
        inside = (
            None
            if self.inside is None or not request.words
            else self.inside.prepare(user, request, inside_of)
        )
        candidates = [
            candidate
            for candidate in [
                *(one for provider in asking for one in _candidates_of(provider)),
                *(inside.candidates if inside is not None else ()),
            ]
            if only is None or any(_same_place(candidate.cell, wanted) for wanted in only)
        ]
        providers: dict[str, Searches] = {
            provider.place.model_dump_json(): provider for provider in asking
        }
        if inside is not None:
            providers.update(inside.providers)
        planned = plan(
            candidates,
            mode=request.mode,
            # Only places a person named: insisting on everything would ask
            # every connection they hold, past the ceiling and the backoff.
            insist=request.insist and only is not None,
            max_connections=self.limits.max_connections,
        )
        alone = only is not None and len(only) == 1
        return Answer(
            engine=self,
            user=user,
            request=request,
            planned=planned,
            visible=visible,
            providers=providers,
            rows=ROWS_ALONE if alone else ROWS_TYPING if request.mode == "typing" else ROWS_SEARCH,
            # The agent's answers neither end the person's nor each other's:
            # two chats may search at once.
            claims=audience == "person",
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
        providers: Mapping[str, Searches],
        rows: int,
        claims: bool = True,
    ) -> None:
        self.engine = engine
        self._claims = claims
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
        # At most this many connections asked at once, a connection's cells
        # one after another (D200). Taken before a cell's clock starts, so a
        # costly cell queued behind slow ones keeps its own seconds.
        self._slots = asyncio.Semaphore(engine.limits.parallel_connections)
        self._connections: dict[uuid.UUID, asyncio.Lock] = {}

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
        if self._claims:
            self.engine.claim(self)
        try:
            async for line in self._lines():
                yield line
        finally:
            self._stop()
            if self._claims:
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
        recency: dict[str, int] = {}
        for index, one in enumerate(self.request.recent):
            key = _recent_key(one)
            if key is not None:
                recency.setdefault(key, index)
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

    def _asked(
        self,
        planned: Planned,
        session: AsyncSession,
        deadline: float,
        stopped: Callable[[], bool] | None = None,
    ) -> Asked:
        return Asked(
            user=self.user,
            typed=self.request.words,
            words=self._words,
            field=planned.cell.cell.field,
            mode=self.request.mode,
            limit=self._rows,
            bounds=SearchBounds(
                deadline=deadline,
                stopped=self._stopped if stopped is None else stopped,
                limiter=self.engine.limiter,
            ),
            session=session,
            visible=self.visible,
            recent=self.request.recent,
            browser=self.request.browser,
        )

    def _provider(self, planned: Planned) -> Searches:
        return self._providers[planned.cell.cell.place.model_dump_json()]

    async def _application(self, cells: list[Planned]) -> None:
        """The instant application cells, one after another in one session."""
        async with async_session_maker() as session:
            for planned in cells:
                asked = self._asked(planned, session, self._deadline(planned))
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
        connector_id = planned.cell.connector_id
        if connector_id is None:
            await self._shared(planned)
            return
        turn = self._connections.setdefault(connector_id, asyncio.Lock())
        async with turn, self._slots:
            await self._shared(planned)

    async def _shared(self, planned: Planned) -> None:
        """A cell in a task and a session of its own, shared with an identical one."""
        # One reading of the clock for the cell and for the provider, so a
        # provider at its deadline knows the engine has given up on it too.
        deadline = self._deadline(planned)

        async def start(abandoned: Callable[[], bool]) -> Found:
            # The shared task's own stop, not this answer's: an answer that
            # joined it still waits when the one that started it has gone.
            async with async_session_maker() as session:
                asked = self._asked(planned, session, deadline, abandoned)
                return await self._provider(planned).search(asked)

        key = (self.user.id, cell_key(planned.cell.cell), self._words, self._rows)
        try:
            found = await self.engine.inflight.run(
                key, start, mode=self.request.mode, deadline=deadline
            )
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
    if found.skipped is not None:
        return Outcome(way="none", status="skipped", reason=found.skipped, since=found.since)
    if found.error_kind is not None:
        return Outcome(
            way="live",
            status="failed",
            error_kind=found.error_kind,
            message=found.message,
            owned=found.owned,
        )
    return Outcome(
        way="live",
        status="complete" if found.complete else "stopped",
        notice=found.notice,
        more=found.more,
    )


def _recent_key(recent: RecentTarget) -> str | None:
    target = recent_target(recent)
    return None if target is None else target_key(target)
