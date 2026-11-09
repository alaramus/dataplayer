"""A stream and a queue read on by a pipeline's link (D335), and the columns
rows have when they move in or out of a message node (D336).

A stream is read from a bookmark this application keeps, as Binance's is
(D319): the next offset, under `""`. A queue has no position: the link is its
consumer, takes a block without acknowledging it on a channel it holds, and
acknowledges the block when it is kept — after it was written. A failure in
between leaves it unacknowledged, and the broker hands it out again once the
channel closes; a channel nobody acknowledges on is closed after a while.

An exchange is read the same way through a queue of the link's own, named by
its reader, which `link_queues` makes ready first (D337); the bookmark's one
part is that queue's name.
"""

import asyncio
import contextlib
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import UTC
from typing import Any

from aio_pika.abc import AbstractChannel, AbstractIncomingMessage

from app.adapters.fetch import FetchColumn
from app.adapters.message_cells import (
    field_text,
    json_of,
    json_text,
    moment,
    text_of,
)
from app.adapters.rabbitmq import link_queues
from app.adapters.rabbitmq.catalog import Named, parse, read_exchange, read_queue
from app.adapters.rabbitmq.session import RabbitmqSession
from app.adapters.rabbitmq.streams import (
    FIELD_PREFIX,
    PREFETCH,
    StreamMessage,
    Window,
    end_of,
    plain,
    read_from,
    read_window,
)
from app.adapters.reading_on import (
    Bookmark,
    BookmarkAccess,
    ReadBlock,
    ReadingTerms,
    ReadStart,
    UnreadSpan,
)
from app.adapters.relation import ColumnType, TypeCategory
from app.core.translation import say

NEXT = ""
TAKEN = "taken"

# How long a block taken from a queue may wait for its acknowledgement before
# its channel is closed and the broker hands it out again.
HOLD_SECONDS = 120.0

# How long a queue is waited on for the rest of a block once it went quiet.
QUIET_SECONDS = 0.5

_PROPERTIES = (
    "message_id",
    "correlation_id",
    "reply_to",
    "priority",
    "expiration",
    "type",
    "app_id",
    "user_id",
    "delivery_mode",
)


def _column(name: str, category: TypeCategory, *, sent: bool) -> FetchColumn:
    return FetchColumn(
        name=name,
        type=ColumnType(sql=name, category=category),
        nullable=True,
        insertable=sent,
    )


# What a message read out of a queue is (D335): its own columns; the body's
# fields are those the target names (D338).
QUEUE_COLUMNS = [
    _column("redelivered", "boolean", sent=False),
    _column("exchange", "string", sent=False),
    _column("routing_key", "string", sent=False),
    _column("timestamp", "datetime", sent=True),
    _column("content_type", "string", sent=True),
    _column("headers", "json", sent=True),
    _column("properties", "json", sent=True),
    _column("body", "string", sent=True),
]


_OWN = frozenset(column.name for column in QUEUE_COLUMNS)


def body_fields(wanted: list[FetchColumn] | None) -> list[FetchColumn]:
    """A column for every column of the target that is not a message's own:
    the top-level field of that name in a JSON body (D338)."""
    return [
        _column(column.name, column.type.category, sent=False)
        for column in wanted or []
        if column.name not in _OWN and column.name != ""
    ]


def taking_columns(
    given: list[FetchColumn], *, routed: bool, own: list[FetchColumn] | None = None
) -> list[FetchColumn]:
    """What a message node takes from rows of the `given` columns (D336): the
    message's own a sender sets, and a body field for every given column."""
    sent = [
        *([_column("routing_key", "string", sent=True)] if routed else []),
        *(own or [column for column in QUEUE_COLUMNS if column.insertable]),
    ]
    taken = {column.name for column in sent}
    fields = [
        _column(column.name, column.type.category, sent=True)
        for column in given
        if column.name not in taken and column.name != ""
    ]
    return [*sent, *fields]


@dataclass(frozen=True)
class Taken:
    """A message out of a queue, as a link reads it."""

    redelivered: bool
    exchange: str
    routing_key: str
    timestamp: int | None
    content_type: str | None
    headers: dict[str, Any]
    properties: dict[str, Any]
    body: bytes


def taken_of(incoming: AbstractIncomingMessage) -> Taken:
    stamp = incoming.timestamp
    properties = {
        name: plain(getattr(incoming, name, None))
        for name in _PROPERTIES
        if getattr(incoming, name, None) not in (None, "")
    }
    return Taken(
        redelivered=bool(incoming.redelivered),
        exchange=incoming.exchange or "",
        routing_key=incoming.routing_key or "",
        timestamp=None
        if stamp is None
        else int(stamp.replace(tzinfo=stamp.tzinfo or UTC).timestamp() * 1000),
        content_type=incoming.content_type or None,
        headers={str(k): plain(v) for k, v in (incoming.headers or {}).items()},
        properties=properties,
        body=bytes(incoming.body),
    )


def _queue_row(one: Taken, columns: list[str]) -> list[str | None]:
    """A message as a row; its body read as JSON once, when a field is asked."""
    fields: dict[str, Any] | None = None
    if any(column not in _OWN for column in columns):
        fields = json_of(one.body) or {}
    return [
        _queue_cell(one, column)
        if column in _OWN
        # Any other name is a field of the body, null where there is none (D338).
        else field_text((fields or {}).get(column))
        for column in columns
    ]


def _queue_cell(one: Taken, column: str) -> str | None:
    if column == "redelivered":
        return "true" if one.redelivered else "false"
    if column == "exchange":
        return one.exchange
    if column == "routing_key":
        return one.routing_key
    if column == "timestamp":
        return moment(one.timestamp)
    if column == "content_type":
        return one.content_type
    if column == "headers":
        return json_text(one.headers)
    if column == "properties":
        return json_text(one.properties)
    if column == "body":
        return text_of(one.body)
    raise ValueError(say("Unknown column: {column}", column=column))


def _stream_cell(one: StreamMessage, column: str) -> str | None:
    if column == "offset":
        return str(one.offset)
    if column == "timestamp":
        return moment(one.timestamp)
    if column == "exchange":
        return one.exchange
    if column == "routing_key":
        return one.routing_key
    if column == "content_type":
        return one.content_type
    if column == "headers":
        return json_text(one.headers)
    if column == "properties":
        return json_text(one.properties)
    if column == "body":
        return text_of(one.body)
    if column.startswith(FIELD_PREFIX):
        value = json_of(one.body)
        return (
            None
            if value is None
            else field_text(value.get(column[len(FIELD_PREFIX) :]))
        )
    raise ValueError(say("Unknown column: {column}", column=column))


@dataclass
class Held:
    """A block taken from a queue and not yet acknowledged."""

    stack: AsyncExitStack
    channel: AbstractChannel
    last: AbstractIncomingMessage | None
    expiry: asyncio.TimerHandle | None = None
    closed: bool = False

    async def release(self, acknowledge: bool) -> None:
        if self.closed:
            return
        self.closed = True
        if self.expiry is not None:
            self.expiry.cancel()
        try:
            if acknowledge and self.last is not None:
                await self.last.ack(multiple=True)
        finally:
            # Closing a channel hands back whatever it did not acknowledge.
            with contextlib.suppress(Exception):
                await self.stack.aclose()


class RabbitmqReading:
    def __init__(
        self, session: RabbitmqSession, bookmarks: BookmarkAccess | None
    ) -> None:
        self._session = session
        self._bookmarks = bookmarks
        self._held: dict[str, Held] = {}

    def reads_on(self, node_id: str) -> bool:
        try:
            named = parse(node_id)
        except ValueError:
            return False
        return named.prefix in {"stream", "queue"} or link_queues.reads_through(named)

    async def reading_terms(self, node_id: str) -> ReadingTerms:
        named = await self._named(node_id)
        exchange_type = None
        if link_queues.reads_through(named):
            assert named.name is not None
            described = await read_exchange(self._session, named.vhost, named.name)
            exchange_type = str(described.get("type") or "direct")
        return link_queues.terms_for(named, exchange_type)

    async def prepare_reader(
        self, node_id: str, reader: str, binding_key: str | None
    ) -> bool:
        named = await self._named(node_id)
        if not link_queues.reads_through(named):
            return False
        return await link_queues.prepare(self._session, named, reader, binding_key)

    def row_key(self, node_id: str) -> list[str]:
        """A stream's message is named by its offset; a queue's by nothing."""
        return (
            ["offset"]
            if self.reads_on(node_id) and parse(node_id).prefix == "stream"
            else []
        )

    async def moving_columns(
        self,
        node_id: str,
        given: list[FetchColumn] | None,
        wanted: list[FetchColumn] | None = None,
    ) -> list[FetchColumn] | None:
        named = parse(node_id)
        if named.name is None:
            return None
        if given is None:
            # A queue gives messages, with the fields the target names (D338),
            # and an exchange read through the link's queue gives the same
            # (D337); a stream gives its page's own rows, fields found there.
            if named.prefix == "queue":
                await read_queue(self._session, named.vhost, named.name, stream=False)
                return [*QUEUE_COLUMNS, *body_fields(wanted)]
            if link_queues.reads_through(named):
                await read_exchange(self._session, named.vhost, named.name)
                return [*QUEUE_COLUMNS, *body_fields(wanted)]
            return None
        if named.prefix == "exchange":
            await read_exchange(self._session, named.vhost, named.name)
            return taking_columns(given, routed=True)
        if named.prefix in {"queue", "stream"}:
            await read_queue(
                self._session, named.vhost, named.name, stream=named.prefix == "stream"
            )
            return taking_columns(given, routed=False)
        return None

    async def _named(self, node_id: str) -> Named:
        named = parse(node_id)
        if named.name is None or not self.reads_on(node_id):
            raise ValueError(say("Only a stream, a queue or an exchange is read on"))
        own = self._session.options.vhost
        if own and named.vhost != own:
            raise ValueError(say("Not a node of this connection"))
        if named.prefix == "exchange":
            await read_exchange(self._session, named.vhost, named.name)
        else:
            await read_queue(
                self._session, named.vhost, named.name, stream=named.prefix == "stream"
            )
        return named

    def _store(self) -> BookmarkAccess:
        if self._bookmarks is None:
            raise ValueError(say("This connection keeps no reader's place here"))
        return self._bookmarks

    # --- what is unread -------------------------------------------------------

    async def unread(self, node_id: str, reader: str, start: ReadStart) -> UnreadSpan:
        named = await self._named(node_id)
        assert named.name is not None
        if named.prefix in {"queue", "exchange"}:
            queue, part = _taken_from(named, reader)
            ready = await self._session.waiting(named.vhost, queue, node_id)
            # An exchange's reader with nothing kept is a link's first run,
            # whose table it may make (D313), even when its queue outlived a
            # first try (D337).
            fresh = (
                named.prefix == "exchange"
                and await self._store().read(node_id, reader) is None
            )
            return UnreadSpan(
                start=Bookmark(positions={part: 0}),
                line=Bookmark(positions={part: ready}),
                count=ready,
                fresh=fresh,
            )
        kept = await self._store().read(node_id, reader)
        async with self._session.channel(node_id, vhost=named.vhost) as channel:
            await channel.set_qos(prefetch_count=PREFETCH)
            end = await end_of(channel, named.name)
            head = await read_from(channel, named.name, "first", lambda _: True, 1)
        first = head[0].offset if head else end
        lost = 0
        if kept is None or NEXT not in kept.positions:
            at = first if start == "earliest" else end
            fresh = True
        else:
            at = kept.positions[NEXT]
            fresh = False
            if at < first:
                lost, at = first - at, first
            # A stream made again under its name ends before the bookmark.
            at = min(at, end)
        return UnreadSpan(
            start=Bookmark(positions={NEXT: at}),
            line=Bookmark(positions={NEXT: end}),
            count=max(end - at, 0),
            lost=lost,
            fresh=fresh,
        )

    # --- reading a block ---------------------------------------------------------

    async def read_on(
        self, node_id: str, columns: list[str], at: Bookmark, line: Bookmark, limit: int
    ) -> ReadBlock:
        named = await self._named(node_id)
        assert named.name is not None
        if named.prefix == "queue":
            return await self._take(
                node_id, node_id, named.vhost, named.name, TAKEN, columns, at, line, limit
            )
        if named.prefix == "exchange":
            # The bookmark's one part names the link's queue (D337).
            if len(at.positions) != 1:
                raise ValueError(say("Reading stopped moving on"))
            [queue] = at.positions
            return await self._take(
                node_id,
                _held_as(node_id, queue),
                named.vhost,
                queue,
                queue,
                columns,
                at,
                line,
                limit,
            )
        start = at.positions.get(NEXT, 0)
        end = min(line.positions.get(NEXT, start), start + limit)
        if end <= start:
            return ReadBlock(
                rows=[], after=Bookmark(positions={NEXT: start}), done=True
            )
        async with self._session.channel(node_id, vhost=named.vhost) as channel:
            await channel.set_qos(prefetch_count=PREFETCH)
            got, _ = await read_window(channel, named.name, Window(start, end))
        rows = [[_stream_cell(one, column) for column in columns] for one in got]
        after = end if not got else max(end, got[-1].offset + 1)
        after = min(after, line.positions.get(NEXT, after))
        return ReadBlock(
            rows=rows,
            after=Bookmark(positions={NEXT: after}),
            done=after >= line.positions.get(NEXT, after),
        )

    async def _take(
        self,
        node_id: str,
        held_as: str,
        vhost: str,
        queue: str,
        part: str,
        columns: list[str],
        at: Bookmark,
        line: Bookmark,
        limit: int,
    ) -> ReadBlock:
        """A block of `queue`, held under `held_as` until it is kept; `part` is
        the bookmark's key."""
        # A block taken before and never kept goes back first.
        await self._let_go(held_as)
        taken = at.positions.get(part, 0)
        want = min(limit, line.positions.get(part, taken) - taken)
        if want <= 0:
            return ReadBlock(rows=[], after=at, done=True)
        stack = AsyncExitStack()
        channel = await stack.enter_async_context(self._session.channel(node_id, vhost=vhost))
        try:
            await channel.set_qos(prefetch_count=want)
            got = await _consume(channel, queue, want)
        except BaseException:
            await stack.aclose()
            raise
        held = Held(stack, channel, got[-1] if got else None)
        if got:
            self._held[held_as] = held
            held.expiry = asyncio.get_running_loop().call_later(
                HOLD_SECONDS, lambda: asyncio.ensure_future(self._let_go(held_as))
            )
        else:
            await held.release(acknowledge=False)
        rows = [_queue_row(taken_of(one), columns) for one in got]
        after = taken + len(got)
        return ReadBlock(
            rows=rows,
            after=Bookmark(positions={part: after}),
            # Fewer than asked for: other consumers took the rest.
            done=len(got) < want or after >= line.positions.get(part, after),
        )

    async def _let_go(self, node_id: str) -> None:
        held = self._held.pop(node_id, None)
        if held is not None:
            await held.release(acknowledge=False)

    # --- keeping where it stands ----------------------------------------------------

    async def mark_read(self, node_id: str, reader: str, at: Bookmark) -> None:
        named = parse(node_id)
        if named.prefix in {"queue", "exchange"}:
            held_as = (
                node_id if named.prefix == "queue" else _held_as(node_id, reader)
            )
            held = self._held.pop(held_as, None)
            if held is not None:
                await held.release(acknowledge=True)
            if named.prefix == "exchange":
                await self._store().write(node_id, reader, at)
            return
        await self._store().write(node_id, reader, at)


def _taken_from(named: Named, reader: str) -> tuple[str, str]:
    """The queue a block is taken from, and the bookmark's key for it: the
    queue itself, or the link's own queue for an exchange (D337)."""
    assert named.name is not None
    if named.prefix == "exchange":
        return reader, reader
    return named.name, TAKEN


def _held_as(node_id: str, queue: str) -> str:
    """Where a block of an exchange is held: one per link's queue."""
    return f"{node_id} {queue}"


async def _consume(
    channel: AbstractChannel, queue: str, want: int
) -> list[AbstractIncomingMessage]:
    """Up to `want` messages taken without acknowledgement, or fewer when the
    queue goes quiet."""
    target = await channel.get_queue(queue, ensure=False)
    got: list[AbstractIncomingMessage] = []
    done = asyncio.Event()
    last = time.monotonic()

    async def on_message(incoming: AbstractIncomingMessage) -> None:
        nonlocal last
        last = time.monotonic()
        got.append(incoming)
        if len(got) >= want:
            done.set()

    tag = await target.consume(on_message, no_ack=False)
    began = time.monotonic()
    try:
        while not done.is_set():
            now = time.monotonic()
            if now - (last if got else began) >= (QUIET_SECONDS if got else 2.0):
                break
            try:
                await asyncio.wait_for(done.wait(), 0.05)
            except TimeoutError:
                pass
    finally:
        # Cancelling stops the deliveries; what was taken stays unacknowledged.
        await target.cancel(tag)
    return got[:want]
