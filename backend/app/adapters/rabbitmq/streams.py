"""A stream's messages read as rows, newest first (D327).

A read is a consumer started at an offset in `x-stream-offset` and cancelled
once it has what it came for. On a stream an acknowledgement only grants
credit: nothing is taken from anybody, and no position is stored.

The node is checked to be a stream through the management API before any
consumer starts: the same consumer on a classic or quorum queue would take its
messages for good.

AMQP 0-9-1 says nothing of where a stream ends, so the end is learned by
reading from `last`, the start of its last chunk. Offsets and a moment are
the only things a stream serves; every other filter is applied to what was
read, inside a ceiling.
"""

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from aio_pika.abc import AbstractChannel, AbstractIncomingMessage

from app.adapters.export import EXPORT_BATCH_SIZE, ExportBatch, ExportRequest
from app.adapters.fetch import (
    FetchColumn,
    FetchRequest,
    FetchResult,
    Filter,
    FilterOp,
    ScalarFilter,
)
from app.adapters.message_cells import (
    RANGE_OPS,
    TEXT_OPS,
    body_shape,
    field_text,
    json_of,
    json_text,
    milliseconds_of,
    moment,
    predicate,
    text_of,
)
from app.adapters.rabbitmq.catalog import parse, read_queue
from app.adapters.rabbitmq.session import RabbitmqSession
from app.adapters.relation import ColumnType, TypeCategory
from app.core.translation import say

# How deep a page may reach from either end (D327), as a topic's (D306).
DEPTH_CEILING = 10_000

# Messages read for one page when a filter is applied to what was read.
SCAN_CEILING = 100_000

# Newest messages read to find the fields of JSON bodies.
SAMPLE = 200

# A chunk read at a time while a filter is looking for matches.
FILTER_CHUNK = 500

# How long one read may take, and how long it waits for a first message and
# for the next one: a stream delivers a chunk at once, so a pause is its end.
READ_SECONDS = 10.0
FIRST_SECONDS = 1.5
IDLE_SECONDS = 0.3

# Messages handed to the reader before it acknowledges any.
PREFETCH = 1000

FIELD_PREFIX = "body."

OFFSET_HEADER = "x-stream-offset"

_PROPERTIES = (
    "message_id",
    "correlation_id",
    "reply_to",
    "priority",
    "expiration",
    "type",
    "user_id",
    "app_id",
    "content_encoding",
    "delivery_mode",
)


@dataclass(frozen=True)
class StreamMessage:
    offset: int
    # Milliseconds since the epoch: the publisher's own property, or nothing.
    timestamp: int | None
    exchange: str | None
    routing_key: str | None
    content_type: str | None
    headers: dict[str, Any]
    properties: dict[str, Any]
    body: bytes


def plain(value: Any) -> Any:
    """A header's value as JSON can hold it: bytes as text or hex."""
    if isinstance(value, bytes | bytearray):
        return text_of(bytes(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(name): plain(item) for name, item in value.items()}
    if isinstance(value, list | tuple):
        return [plain(item) for item in value]
    return value


def message_of(incoming: AbstractIncomingMessage) -> StreamMessage | None:
    headers = dict(incoming.headers or {})
    offset = headers.pop(OFFSET_HEADER, None)
    if not isinstance(offset, int):
        return None
    stamp = incoming.timestamp
    properties: dict[str, Any] = {}
    for name in _PROPERTIES:
        value = getattr(incoming, name, None)
        if value is not None and value != "":
            properties[name] = plain(value)
    return StreamMessage(
        offset=offset,
        timestamp=None
        if stamp is None
        else int(stamp.replace(tzinfo=stamp.tzinfo or UTC).timestamp() * 1000),
        exchange=incoming.exchange,
        routing_key=incoming.routing_key,
        content_type=incoming.content_type or None,
        headers={str(name): plain(value) for name, value in headers.items()},
        properties=properties,
        body=bytes(incoming.body),
    )


# --- reading --------------------------------------------------------------------

Start = int | datetime | str


async def read_from(
    channel: AbstractChannel,
    queue: str,
    start: Start,
    stop: Callable[[StreamMessage], bool],
    most: int,
) -> list[StreamMessage]:
    """Messages from `start` on, until `stop` says so, `most` are read, the
    stream pauses or the time is up."""
    target = await channel.get_queue(queue, ensure=False)
    got: list[StreamMessage] = []
    done = asyncio.Event()
    last = time.monotonic()

    async def on_message(incoming: AbstractIncomingMessage) -> None:
        nonlocal last
        last = time.monotonic()
        await incoming.ack()
        if done.is_set():
            return
        message = message_of(incoming)
        if message is None:
            return
        got.append(message)
        if stop(message) or len(got) >= most:
            done.set()

    tag = await target.consume(on_message, arguments={OFFSET_HEADER: start})
    began = time.monotonic()
    try:
        while not done.is_set():
            now = time.monotonic()
            waited = now - (last if got else began)
            if now - began >= READ_SECONDS or waited >= (
                IDLE_SECONDS if got else FIRST_SECONDS
            ):
                break
            try:
                await asyncio.wait_for(done.wait(), 0.05)
            except TimeoutError:
                pass
    finally:
        done.set()
        await target.cancel(tag)
    return got


async def end_of(channel: AbstractChannel, queue: str) -> int:
    """One past the newest offset, or 0 for a stream with nothing in it."""
    last = await read_from(channel, queue, "last", lambda _: False, PREFETCH * 10)
    return max((message.offset for message in last), default=-1) + 1


async def offset_at(
    channel: AbstractChannel, queue: str, at: datetime, end: int
) -> int:
    """The first offset of the chunk holding the moment, or the end."""
    first = await read_from(channel, queue, at, lambda _: True, 1)
    return first[0].offset if first else end


@dataclass
class Window:
    """Offsets to read, the end not included."""

    start: int
    end: int


async def read_window(
    channel: AbstractChannel, queue: str, window: Window
) -> tuple[list[StreamMessage], int | None]:
    """The messages of a window, and the first offset the stream still has
    when it is past the window's start — what retention has dropped."""
    if window.end <= window.start:
        return [], None
    got = await read_from(
        channel,
        queue,
        window.start,
        lambda message: message.offset >= window.end - 1,
        window.end - window.start + PREFETCH,
    )
    first = got[0].offset if got else None
    kept = [one for one in got if window.start <= one.offset < window.end]
    return kept, (first if first is not None and first > window.start else None)


# --- the columns ----------------------------------------------------------------

_JSON_OPS: list[FilterOp] = ["contains", "is_null", "is_not_null"]
# A moment is served by the stream as where reading starts, so only a lower
# bound is offered; an upper one would need every message's own time.
_FROM_OPS: list[FilterOp] = ["gte", "gt"]


def _column(
    name: str,
    sql: str,
    category: TypeCategory,
    ops: list[FilterOp],
    *,
    sortable: bool = False,
) -> FetchColumn:
    return FetchColumn(
        name=name,
        type=ColumnType(sql=sql, category=category),
        sortable=sortable,
        filter_operators=ops,
        nullable=True,
    )


@dataclass(frozen=True)
class Shape:
    body_category: TypeCategory
    fields: tuple[tuple[str, TypeCategory], ...]

    def columns(self) -> list[FetchColumn]:
        columns = [
            _column("offset", "offset", "number", RANGE_OPS, sortable=True),
            _column("timestamp", "timestamp", "datetime", _FROM_OPS),
            _column("exchange", "exchange", "string", TEXT_OPS),
            _column("routing_key", "routing_key", "string", TEXT_OPS),
            _column("content_type", "content_type", "string", TEXT_OPS),
            _column("headers", "headers", "json", _JSON_OPS),
            _column("properties", "properties", "json", _JSON_OPS),
            _column("body", "bytes", self.body_category, TEXT_OPS),
        ]
        for name, category in self.fields:
            ops = [*TEXT_OPS, *(RANGE_OPS if category == "number" else [])]
            columns.append(_column(FIELD_PREFIX + name, "field", category, ops))
        return columns


def shape_of(messages: list[StreamMessage]) -> Shape:
    category, fields = body_shape([message.body for message in messages])
    return Shape(body_category=category, fields=fields)


def cell(message: StreamMessage, column: str) -> str | None:
    if column == "exchange":
        return message.exchange
    if column == "routing_key":
        return message.routing_key
    if column == "content_type":
        return message.content_type
    if column == "headers":
        return json_text(message.headers)
    if column == "properties":
        return json_text(message.properties)
    if column == "body":
        return text_of(message.body)
    value = json_of(message.body)
    return None if value is None else field_text(value.get(column[len(FIELD_PREFIX) :]))


def row_of(message: StreamMessage, fields: list[str]) -> list[str | None]:
    value = json_of(message.body) if fields else None
    return [
        str(message.offset),
        moment(message.timestamp),
        message.exchange,
        message.routing_key,
        message.content_type,
        json_text(message.headers),
        json_text(message.properties),
        text_of(message.body),
        *[field_text(None if value is None else value.get(name)) for name in fields],
    ]


def predicates(
    filters: list[Filter], columns: list[FetchColumn]
) -> list[Callable[[StreamMessage], bool]]:
    offered = {column.name: column.filter_operators for column in columns}
    found: list[Callable[[StreamMessage], bool]] = []
    for one in filters:
        ops = offered.get(one.column)
        if ops is None:
            raise ValueError(say("Unknown column: {column}", column=one.column))
        if one.op not in ops:
            raise ValueError(
                say("{column} cannot be filtered that way", column=one.column)
            )
        if one.column in {"offset", "timestamp"}:
            continue
        found.append(predicate(one, cell))
    return found


def _number(text: str) -> int:
    try:
        return int(text)
    except ValueError:
        raise ValueError(
            say("{column} takes a whole number", column="offset")
        ) from None


async def limits(
    channel: AbstractChannel, queue: str, filters: list[Filter], end: int
) -> Window:
    """The offsets to read, narrowed by what the stream can serve."""
    window = Window(0, end)
    for one in filters:
        if not isinstance(one, ScalarFilter):
            continue
        if one.column == "offset":
            bound = _number(one.value)
            if one.op == "gte":
                window.start = max(window.start, bound)
            elif one.op == "gt":
                window.start = max(window.start, bound + 1)
            elif one.op == "lte":
                window.end = min(window.end, bound + 1)
            elif one.op == "lt":
                window.end = min(window.end, bound)
        elif one.column == "timestamp":
            at = datetime.fromtimestamp(milliseconds_of(one.value) / 1000, tz=UTC)
            window.start = max(window.start, await offset_at(channel, queue, at, end))
    return window


@dataclass
class Collected:
    messages: list[StreamMessage]
    # Messages were left unread in the window when reading stopped.
    unread: bool


async def collect(
    channel: AbstractChannel,
    queue: str,
    window: Window,
    need: int,
    newest: bool,
    matches: list[Callable[[StreamMessage], bool]],
) -> Collected:
    """Up to `need` matching messages from the chosen end of the window.

    Without a filter one read is enough; with one, chunks are read back (or
    on) until enough match, the window is done or the ceiling is reached.
    """
    chunk = need if not matches else max(need, FILTER_CHUNK)
    cursor = Window(window.start, window.end)
    kept: list[StreamMessage] = []
    scanned = 0
    while cursor.end > cursor.start and len(kept) < need and scanned < SCAN_CEILING:
        if newest:
            part = Window(max(cursor.start, cursor.end - chunk), cursor.end)
        else:
            part = Window(cursor.start, min(cursor.end, cursor.start + chunk))
        got, first = await read_window(channel, queue, part)
        scanned += part.end - part.start
        hits = [one for one in got if all(match(one) for match in matches)]
        if newest:
            kept = hits + kept
            cursor.end = part.start
            if first is not None:
                # Retention dropped what lies before: nothing older is left.
                cursor.end = cursor.start
        else:
            kept = kept + hits
            cursor.start = part.end
        if not matches:
            break
    messages = kept[-need:] if newest else kept[:need]
    return Collected(messages, cursor.end > cursor.start and len(kept) < need)


def newest_first(request: FetchRequest) -> bool:
    if not request.sort:
        return True
    if len(request.sort) > 1 or request.sort[0].column != "offset":
        raise ValueError(say("A stream's messages are ordered by their offset only"))
    return request.sort[0].descending


async def sample(channel: AbstractChannel, queue: str, end: int) -> Shape:
    got, _ = await read_window(channel, queue, Window(max(0, end - SAMPLE), end))
    return shape_of(got)


def _ordered(messages: list[StreamMessage], newest: bool) -> list[StreamMessage]:
    return sorted(messages, key=lambda one: one.offset, reverse=newest)


class RabbitmqStreams:
    def __init__(self, session: RabbitmqSession) -> None:
        self._session = session

    async def _stream(self, node_id: str) -> str:
        """The stream a node id names, checked to be one before any consumer."""
        named = parse(node_id)
        if named.prefix != "stream" or named.name is None:
            raise ValueError(say("Not a stream of this connection"))
        if (self._session.options.vhost or named.vhost) != named.vhost:
            raise ValueError(say("Not a stream of this connection"))
        await read_queue(self._session, named.vhost, named.name, stream=True)
        return named.name

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if request.offset + request.limit > DEPTH_CEILING:
            raise ValueError(
                say(
                    "A page reaches at most {n} messages deep; narrow it by time or offset",
                    n=DEPTH_CEILING,
                )
            )
        newest = newest_first(request)
        queue = await self._stream(request.node_id)
        vhost = parse(request.node_id).vhost
        async with self._session.channel(request.node_id, vhost=vhost) as channel:
            await channel.set_qos(prefetch_count=PREFETCH)
            end = await end_of(channel, queue)
            shape = await sample(channel, queue, end)
            columns = shape.columns()
            matches = predicates(request.filters, columns)
            window = await limits(channel, queue, request.filters, end)
            need = request.offset + request.limit + 1
            collected = await collect(channel, queue, window, need, newest, matches)
        merged = _ordered(collected.messages, newest)
        page = merged[request.offset : request.offset + request.limit]
        fields = [name for name, _ in shape.fields]
        # A field met on the page but not in the sample is shown, offered for
        # nothing, as a topic's is (D306).
        for message in page:
            for name in json_of(message.body) or {}:
                if name not in fields:
                    fields.append(name)
                    columns.append(
                        FetchColumn(
                            name=FIELD_PREFIX + name,
                            type=ColumnType(sql="field", category="string"),
                        )
                    )
        return FetchResult(
            columns=columns,
            rows=[row_of(message, fields) for message in page],
            row_handles=[str(message.offset) for message in page],
            has_more=len(merged) > request.offset + request.limit or collected.unread,
            page_commands=["download", "chart", "share"],
        )

    async def export_rows(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        """Every message the page's filters and order would show, to its depth."""
        newest = newest_first(FetchRequest(node_id=request.node_id, sort=request.sort))
        queue = await self._stream(request.node_id)
        vhost = parse(request.node_id).vhost
        async with self._session.channel(request.node_id, vhost=vhost) as channel:
            await channel.set_qos(prefetch_count=PREFETCH)
            end = await end_of(channel, queue)
            shape = await sample(channel, queue, end)
            columns = shape.columns()
            names = [column.name for column in columns]
            unknown = [column for column in request.columns if column not in names]
            if unknown:
                raise ValueError(say("Unknown column: {column}", column=unknown[0]))
            matches = predicates(request.filters, columns)
            window = await limits(channel, queue, request.filters, end)
            collected = await collect(
                channel, queue, window, DEPTH_CEILING, newest, matches
            )
        merged = _ordered(collected.messages, newest)[:DEPTH_CEILING]
        fields = [name for name, _ in shape.fields]
        picked = [names.index(column) for column in request.columns]
        rows = [
            [row[index] for index in picked]
            for row in (row_of(one, fields) for one in merged)
        ]
        for start in range(0, len(rows), EXPORT_BATCH_SIZE):
            yield ExportBatch(rows=rows[start : start + EXPORT_BATCH_SIZE])
