"""What is inside the person's connections, found by asking them (D197, D200).

One provider per connection the person can see, built for each answer from the
row the visibility query read (D199). A source type is never a provider and
nothing here is written per type: a type that has `SupportsNodeSearch` is
asked, one that has `SearchesColumns` gets a columns cell too, and one without
either is said to be unable. What a cell costs is the type's to state
(`StatesSearchCost`), from what was remembered of the connection's last search.

Asking costs somebody's server a round trip or a walk, so it is bounded: the
engine asks a few connections at once per answer, and here one search runs at
a time per person and connection, a connection that did not answer is left
alone for a while, and a fan-out never makes a pool in the shared store, where
it could close one somebody else's grid is using.
"""

import asyncio
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime

from app.adapters.catalog import (
    CatalogNode,
    DirectoryNode,
    EntryNode,
    FileNode,
    NodeView,
)
from app.adapters.errors import UNANSWERED, ErrorKind
from app.adapters.protocol import (
    AdapterError,
    DataAdapter,
    NodeNotFound,
    SearchesColumns,
    StatesSearchCost,
    SupportsNodeSearch,
)
from app.adapters.registry import UnknownAdapterType
from app.adapters.registry import get as adapter_type_of
from app.adapters.resources import BorrowingStore, Pooling, ResourceStore
from app.adapters.search import (
    LastSearch,
    NodeMatch,
    NodeSearchRequest,
    NodeSearchResult,
    SearchBounds,
    SearchedField,
)
from app.connectors import service
from app.connectors.access import context_for
from app.connectors.health import delay_after
from app.core.config import settings
from app.core.schemas import get_datetime_utc
from app.search.excerpts import segments
from app.search.models import (
    Cell,
    ConnectionPlace,
    Cost,
    Facts,
    Group,
    Hit,
    Match,
    NodeTarget,
    SearchRequest,
    SkipReason,
    target_key,
)
from app.search.plan import CONNECTION_GROUPS_RANK, Candidate
from app.search.providers import Asked, Found, VisibleConnection, name_match, ordered
from app.users.models import User

# Who the health monitor last saw down, for one person, and since when (D19).
Unreachable = Callable[[uuid.UUID], Mapping[uuid.UUID, datetime]]

# How many connections the memory of last searches holds before it forgets
# the one asked longest ago.
_REMEMBERED = 1000

# What a grantee reads of a key that is locked: which key it is belongs to its
# owner (D199), and only the owner can open it (D147).
_LOCKED_BY_OWNER = "Locked by its owner"

# A source's clock stops a little before the answer gives up on its cell, so a
# walk stopped by time hands over what it found instead of being cut off with
# nothing: a share of the time left, and never more than this.
_HANDOVER_SHARE = 0.15
_HANDOVER_SECONDS = 0.25


def _nobody_watches(_: uuid.UUID) -> Mapping[uuid.UUID, datetime]:
    return {}


@dataclass
class _Miss:
    count: int
    since: datetime
    until: float
    # When the latest miss was recorded, on the monotonic clock.
    at: float


class _Backoff:
    """A connection that did not answer a person is left alone, doubling (D200).

    Per person and connection, in memory, like the health monitor's wait
    (D19): one person's slow server is not another person's, and nothing of
    it outlives the process.
    """

    def __init__(self) -> None:
        self._misses: OrderedDict[tuple[uuid.UUID, uuid.UUID], _Miss] = OrderedDict()

    def since(
        self, key: tuple[uuid.UUID, uuid.UUID], *, missed_after: float | None = None
    ) -> datetime | None:
        """Since when it has not answered, while it is still left alone.

        With `missed_after`, only when it has missed again since that moment.
        """
        miss = self._misses.get(key)
        if miss is None or time.monotonic() >= miss.until:
            return None
        if missed_after is not None and miss.at < missed_after:
            return None
        return miss.since

    def missed(self, key: tuple[uuid.UUID, uuid.UUID]) -> None:
        miss = self._misses.pop(key, None)
        count = 1 if miss is None else miss.count + 1
        wait = delay_after(
            misses=count - 1,
            base=settings.HEALTH_INTERVAL_SECONDS,
            cap=settings.HEALTH_BACKOFF_CAP_SECONDS,
        )
        now = time.monotonic()
        self._misses[key] = _Miss(
            count=count,
            since=get_datetime_utc() if miss is None else miss.since,
            until=now + wait,
            at=now,
        )
        while len(self._misses) > _REMEMBERED:
            self._misses.popitem(last=False)

    def answered(self, key: tuple[uuid.UUID, uuid.UUID]) -> None:
        self._misses.pop(key, None)


@dataclass
class _Turn:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    waiting: int = 0


class _Turns:
    """One search at a time per person and connection (D200).

    So a person typing holds at most one of a connector's pooled connections,
    however many lanes and cells ask it.
    """

    def __init__(self) -> None:
        self._turns: dict[tuple[uuid.UUID, uuid.UUID], _Turn] = {}

    @asynccontextmanager
    async def of(self, key: tuple[uuid.UUID, uuid.UUID]) -> AsyncIterator[None]:
        turn = self._turns.setdefault(key, _Turn())
        turn.waiting += 1
        try:
            async with turn.lock:
                yield
        finally:
            turn.waiting -= 1
            if turn.waiting == 0 and self._turns.get(key) is turn:
                del self._turns[key]


@dataclass(frozen=True)
class Inside:
    """The connection cells of one answer, and who answers each place."""

    candidates: list[Candidate]
    providers: dict[str, ConnectionProvider]


class ConnectionSearch:
    """Asking connections what they hold: built once, when the application is."""

    def __init__(
        self,
        *,
        resources: ResourceStore | None,
        unreachable: Unreachable = _nobody_watches,
    ) -> None:
        self._resources = resources
        self._unreachable = unreachable
        self._turns = _Turns()
        self._backoff = _Backoff()
        self._last: OrderedDict[uuid.UUID, LastSearch] = OrderedDict()

    def prepare(
        self,
        user: User,
        request: SearchRequest,
        visible: Sequence[VisibleConnection],
    ) -> Inside:
        """The candidates of every visible connection, in the order they are asked.

        In context first, in the order the browser sent; then what was opened
        from the search lately; then by name. A connection named as a scope is
        asked from the level it names, and counts as in context.
        """
        scoped = {
            place.connector_id: place
            for place in request.only or []
            if isinstance(place, ConnectionPlace)
        }
        down = self._unreachable(user.id)
        opened = time.monotonic()
        # Only places a person named, as the engine's plan has it.
        insist = request.insist and request.only is not None
        candidates: list[Candidate] = []
        providers: dict[str, ConnectionProvider] = {}
        for position, connection in enumerate(_ordered(request, visible)):
            if request.only is not None and connection.id not in scoped:
                continue
            place = scoped.get(connection.id) or ConnectionPlace(connector_id=connection.id)
            group = Group(
                key=f"connection:{connection.id}",
                title=connection.name,
                rank=CONNECTION_GROUPS_RANK + position,
            )
            costs: dict[SearchedField, Cost] = {}
            for one, able in _fields(connection):
                blocked, since = self._blocked(user.id, connection, able, down)
                costs[one] = self._cost(connection, one)
                candidates.append(
                    Candidate(
                        cell=Cell(place=place, field=one),
                        cost=costs[one],
                        group=group,
                        connector_id=connection.id,
                        in_context=connection.id in request.context or connection.id in scoped,
                        blocked=blocked,
                        since=since,
                        owned=connection.access == "own",
                        order=position,
                    )
                )
            providers[place.model_dump_json()] = ConnectionProvider(
                self, connection, place, opened=opened, costs=costs, insist=insist
            )
        return Inside(candidates=candidates, providers=providers)

    def _blocked(
        self,
        user_id: uuid.UUID,
        connection: VisibleConnection,
        able: bool,
        down: Mapping[uuid.UUID, datetime],
    ) -> tuple[SkipReason | None, datetime | None]:
        if not connection.enabled:
            return "switched_off", None
        if not able:
            return "cannot_search", None
        if connection.id in down:
            return "unreachable", down[connection.id]
        since = self._backoff.since((user_id, connection.id))
        if since is not None:
            return "unreachable", since
        return None, None

    def _cost(self, connection: VisibleConnection, one: SearchedField) -> Cost:
        driver = _driver(connection)
        if driver is None or not issubclass(driver, StatesSearchCost):
            return "costly"
        return driver.search_cost(one, self._last.get(connection.id))

    def _remember(self, connector_id: uuid.UUID, last: LastSearch) -> None:
        self._last.pop(connector_id, None)
        self._last[connector_id] = last
        while len(self._last) > _REMEMBERED:
            self._last.popitem(last=False)

    async def ask(
        self,
        connection: VisibleConnection,
        place: ConnectionPlace,
        asked: Asked,
        *,
        opened: float,
        cost: Cost,
        insist: bool,
    ) -> Found:
        """One cell of one connection, under the owner's credentials (D33).

        The stop the walk checks is this task's own: a cell shared by two
        answers stops when the last of them goes, not when the first does.

        What it says of the server is remembered for the next answer's plan.
        A failure to reach it is a miss, and so is a deadline passed on Enter
        while the server had most of the cell's time. A late keystroke is not:
        its deadline is too short to say anything about a server. Nor is a cell
        that spent its time waiting for its turn among the answer's other
        connections, or behind this person's other search of the same one.
        Any answer ends the wait. A miss while this answer runs — its names
        cell late, say — leaves the cells after it unasked, unless the person
        insisted.
        """
        key = (asked.user.id, connection.id)
        # A costly cell's seconds are its own and start when it is asked; any
        # other's deadline is the answer's (D200).
        window = time.monotonic() if cost == "costly" else opened
        async with self._turns.of(key):
            since = None if insist else self._backoff.since(key, missed_after=opened)
            if since is not None:
                return Found(skipped="unreachable", since=since)
            began = time.monotonic()
            deadline = asked.bounds.deadline
            # Late on Enter, with most of the cell's time spent on the server.
            fairly_late = asked.mode == "search" and deadline - began >= (deadline - window) / 2
            try:
                result = await self._asked(connection, place, asked)
            except TimeoutError:
                if fairly_late:
                    self._backoff.missed(key)
                raise
            except asyncio.CancelledError:
                # Cancelled at the deadline, or by a newer answer before it.
                if fairly_late and time.monotonic() >= deadline:
                    self._backoff.missed(key)
                raise
        if result.error_kind in UNANSWERED:
            self._backoff.missed(key)
        else:
            self._backoff.answered(key)
        if asked.field == "names" and result.extent is not None:
            self._remember(connection.id, LastSearch(extent=result.extent))
        return _found(connection, result, asked, owned=connection.access == "own")

    async def _asked(
        self, connection: VisibleConnection, place: ConnectionPlace, asked: Asked
    ) -> NodeSearchResult:
        """The source asked; a failure is a result that says so (D201).

        Raises TimeoutError when a source whose clock ran out could only fail,
        as a statement the server stopped does: the source's deadline is the
        answer's, a little early, so the cell is late rather than failed.
        """
        request = NodeSearchRequest(node_id=place.node_id, query=asked.typed, limit=asked.limit)
        stop = threading.Event()
        left = asked.bounds.left()
        bounds = SearchBounds(
            deadline=asked.bounds.deadline - min(_HANDOVER_SECONDS, left * _HANDOVER_SHARE),
            stopped=stop.is_set,
            limiter=asked.bounds.limiter,
        )
        store = BorrowingStore(self._resources)
        try:
            try:
                adapter = _adapter(connection, store)
            except Exception:
                # Never the text: a validation error quotes the options it
                # refused, and a password may be among them.
                return _failed("config", "The settings of this connection cannot be read")
            return await _asked_of(adapter, asked.field, request, bounds)
        except asyncio.CancelledError:
            # Set before the store closes under a walk still running on its
            # thread, so the walk stops at its next entry.
            stop.set()
            raise
        except NodeNotFound:
            return _failed("config", "Where this search started is gone")
        except ValueError as refusal:
            # The source's own refusal of where it was asked to start.
            return _failed("config", str(refusal))
        except AdapterError as failure:
            if failure.error_kind == "timeout" and time.monotonic() >= bounds.deadline:
                raise TimeoutError from None
            return _failed(failure.error_kind, failure.message)
        finally:
            # Finished whatever happens to this task: a close cancelled half
            # way leaves a pool half shut, and closing one whose server never
            # answered waits for its connection attempt to give up.
            await asyncio.shield(_closing(store))


class ConnectionProvider:
    """One connection, asked for one answer: its names, and its columns if it has any."""

    def __init__(
        self,
        inside: ConnectionSearch,
        connection: VisibleConnection,
        place: ConnectionPlace,
        *,
        opened: float,
        costs: Mapping[SearchedField, Cost],
        insist: bool,
    ) -> None:
        self._inside = inside
        self._connection = connection
        self._place = place
        # When the answer that built it began, what each of its cells costs,
        # and whether the person said to ask it anyway.
        self._opened = opened
        self._costs = costs
        self._insist = insist

    async def search(self, asked: Asked) -> Found:
        return await self._inside.ask(
            self._connection,
            self._place,
            asked,
            opened=self._opened,
            cost=self._costs.get(asked.field, "costly"),
            insist=self._insist,
        )


def _ordered(
    request: SearchRequest, visible: Sequence[VisibleConnection]
) -> list[VisibleConnection]:
    by_id = {connection.id: connection for connection in visible}
    first: list[uuid.UUID] = []
    recent = [one.connector_id for one in request.recent if one.connector_id is not None]
    for connector_id in [*request.context, *recent]:
        if connector_id in by_id and connector_id not in first:
            first.append(connector_id)
    chosen = set(first)
    # `visible` is already by name.
    return [by_id[one] for one in first] + [
        connection for connection in visible if connection.id not in chosen
    ]


def _driver(connection: VisibleConnection) -> type[DataAdapter] | None:
    try:
        return adapter_type_of(connection.adapter_type).adapter_class
    except UnknownAdapterType:
        return None


def _fields(connection: VisibleConnection) -> list[tuple[SearchedField, bool]]:
    """Its cells, and whether its type can answer each.

    A names cell always, so a type that cannot search says so; a columns cell
    only for a type that can answer one (S8).
    """
    driver = _driver(connection)
    fields: list[tuple[SearchedField, bool]] = [
        ("names", driver is not None and issubclass(driver, SupportsNodeSearch))
    ]
    if driver is not None and issubclass(driver, SearchesColumns):
        fields.append(("columns", True))
    return fields


def _adapter(connection: VisibleConnection, store: BorrowingStore) -> DataAdapter:
    """The connection's source, built from the row the visibility query read.

    The funnel's rule without its round trip (D199): the owner's context, and
    a store that lends a pool already open and makes none in the shared store.
    """
    adapter_type = adapter_type_of(connection.adapter_type)
    options = service.merge_options(connection.config, connection.secrets)
    return service.build_adapter(
        adapter_type,
        options,
        context_for(
            connection.owner_id,
            pooling=Pooling(store=store, connector_id=connection.id),
        ),
    )


async def _asked_of(
    adapter: DataAdapter,
    searched: SearchedField,
    request: NodeSearchRequest,
    bounds: SearchBounds,
) -> NodeSearchResult:
    if searched == "columns" and isinstance(adapter, SearchesColumns):
        return await adapter.search_columns(request, bounds)
    if searched == "names" and isinstance(adapter, SupportsNodeSearch):
        return await adapter.search_nodes(request, bounds)
    raise ValueError("This connection cannot be searched this way")


# Closes still running for answers that have gone. Held here because the loop
# keeps only a weak reference to a task.
_CLOSING: set[asyncio.Task[None]] = set()


def _closing(store: BorrowingStore) -> asyncio.Task[None]:
    task = asyncio.ensure_future(store.aclose())
    _CLOSING.add(task)
    task.add_done_callback(_CLOSING.discard)
    return task


def _failed(kind: ErrorKind, message: str) -> NodeSearchResult:
    return NodeSearchResult(complete=False, notice=message, error_kind=kind)


def _found(
    connection: VisibleConnection, result: NodeSearchResult, asked: Asked, *, owned: bool
) -> Found:
    hits = [
        hit
        for match in result.matches
        if (hit := _hit(connection, match, asked)) is not None
    ]
    # The source's order within a class: a tree's nearness, the query's order.
    found = ordered(hits, asked.limit, ranked=True)
    failed = result.error_kind is not None
    message = result.notice if failed else None
    if result.error_kind == "locked" and not owned:
        # The source's sentence names the owner's key.
        message = _LOCKED_BY_OWNER
    return Found(
        hits=found.hits,
        complete=result.complete and not failed,
        notice=None if failed else result.notice,
        more=found.more or (not result.complete and not failed),
        error_kind=result.error_kind,
        message=message,
        owned=owned,
    )


def _hit(connection: VisibleConnection, match: NodeMatch, asked: Asked) -> Hit | None:
    node = match.node
    if asked.field == "columns":
        found: Match | None = Match(
            field="columns",
            match_class="text",
            excerpt=segments(match.excerpt or node.name, asked.words),
        )
    else:
        # Classed again by the one rule, against what the source matched.
        found = name_match(asked.words, match.full_name or node.name)
    if found is None:
        return None
    target = NodeTarget(
        connector_id=connection.id,
        node_id=node.id,
        parent_id=match.parent_id,
        location=match.location,
        name=node.name,
        node_kind=node.kind,
        ancestors=match.ancestors,
        node=node,
    )
    return Hit(
        key=target_key(target),
        target=target,
        title=node.name,
        detail=" · ".join(part for part in (connection.name, match.location) if part),
        facts=Facts(kind=node.kind, changed_at=_changed_at(node), owner=connection.owner_email),
        match=found,
        access=connection.access,
        open=_view(node),
    )


def _view(node: CatalogNode) -> NodeView:
    """What it opens as: what it prefers to be read as, or the catalog at it."""
    return "preferred" if node.representations else "catalog"


def _changed_at(node: CatalogNode) -> datetime | None:
    if isinstance(node, DirectoryNode | FileNode | EntryNode):
        return node.modified_at
    return None
