"""A stream and a queue read on by a pipeline's link (D335), and the columns
rows have when they move in or out of a message node (D336).

A stream is read from a bookmark this application keeps, as Binance's is
(D319): the next offset, under `""`. A queue has no position: the link is its
consumer, takes a block without acknowledging it on a channel it holds, and
acknowledges the block when it is kept — after it was written. A failure in
between leaves it unacknowledged, and the broker hands it out again once the
channel closes; a channel nobody acknowledges on is closed after a while.
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


# What a message read out of a queue is (D335): its own columns, no fields.
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
            return parse(node_id).prefix in {"stream", "queue"}
        except ValueError:
            return False

    def row_key(self, node_id: str) -> list[str]:
        """A stream's message is named by its offset; a queue's by nothing."""
        return (
            ["offset"]
            if self.reads_on(node_id) and parse(node_id).prefix == "stream"
            else []
        )

    async def moving_columns(
        self, node_id: str, given: list[FetchColumn] | None
    ) -> list[FetchColumn] | None:
        named = parse(node_id)
        if named.name is None:
            return None
        if given is None:
            # A queue gives messages; a stream gives its page's own rows.
            if named.prefix == "queue":
                await read_queue(self._session, named.vhost, named.name, stream=False)
                return list(QUEUE_COLUMNS)
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
        if named.name is None or named.prefix not in {"stream", "queue"}:
            raise ValueError(say("Only a stream or a queue is read on"))
        own = self._session.options.vhost
        if own and named.vhost != own:
            raise ValueError(say("Not a node of this connection"))
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
        if named.prefix == "queue":
            ready = await self._session.waiting(named.vhost, named.name, node_id)
            return UnreadSpan(
                start=Bookmark(positions={TAKEN: 0}),
                line=Bookmark(positions={TAKEN: ready}),
                count=ready,
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
            return await self._take(node_id, named, columns, at, line, limit)
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
        named: Named,
        columns: list[str],
        at: Bookmark,
        line: Bookmark,
        limit: int,
    ) -> ReadBlock:
        assert named.name is not None
        for column in columns:
            _queue_cell(Taken(False, "", "", None, None, {}, {}, b""), column)
        # A block taken before and never kept goes back first.
        await self._let_go(node_id)
        taken = at.positions.get(TAKEN, 0)
        want = min(limit, line.positions.get(TAKEN, taken) - taken)
        if want <= 0:
            return ReadBlock(rows=[], after=at, done=True)
        stack = AsyncExitStack()
        channel = await stack.enter_async_context(
            self._session.channel(node_id, vhost=named.vhost)
        )
        try:
            await channel.set_qos(prefetch_count=want)
            got = await _consume(channel, named.name, want)
        except BaseException:
            await stack.aclose()
            raise
        held = Held(stack, channel, got[-1] if got else None)
        if got:
            self._held[node_id] = held
            held.expiry = asyncio.get_running_loop().call_later(
                HOLD_SECONDS, lambda: asyncio.ensure_future(self._let_go(node_id))
            )
        else:
            await held.release(acknowledge=False)
        rows = [
            [_queue_cell(taken_of(one), column) for column in columns] for one in got
        ]
        after = taken + len(got)
        return ReadBlock(
            rows=rows,
            after=Bookmark(positions={TAKEN: after}),
            # Fewer than asked for: other consumers took the rest.
            done=len(got) < want or after >= line.positions.get(TAKEN, after),
        )

    async def _let_go(self, node_id: str) -> None:
        held = self._held.pop(node_id, None)
        if held is not None:
            await held.release(acknowledge=False)

    # --- keeping where it stands ----------------------------------------------------

    async def mark_read(self, node_id: str, reader: str, at: Bookmark) -> None:
        named = parse(node_id)
        if named.prefix == "queue":
            held = self._held.pop(node_id, None)
            if held is not None:
                await held.release(acknowledge=True)
            return
        await self._store().write(node_id, reader, at)


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
