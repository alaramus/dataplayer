"""A topic's messages read as rows, newest first (D306).

Reading never joins a group and never commits: partitions are assigned to the
consumer directly, so a person looking at a topic is nobody's consumer.
Kafka keeps no index but offsets and times, so only where reading starts and
stops is asked of Kafka; every other filter is applied to what was read, inside
a ceiling.
"""

import json
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from confluent_kafka import KafkaError, KafkaException, TopicPartition

from app.adapters import jsontext
from app.adapters.export import EXPORT_BATCH_SIZE, ExportBatch, ExportRequest
from app.adapters.fetch import (
    FetchColumn,
    FetchRequest,
    FetchResult,
    Filter,
    FilterOp,
    InFilter,
    NullFilter,
    ScalarFilter,
)
from app.adapters.kafka.catalog import is_internal, partitions_of, topic_of, watermarks
from app.adapters.kafka.session import TIMEOUT_SECONDS, KafkaClients, KafkaSession
from app.adapters.relation import ColumnType, TypeCategory
from app.core.translation import say

# How deep a page may reach from either end, per partition (D306).
DEPTH_CEILING = 10_000

# Messages read for one page when a filter is applied to what was read.
SCAN_CEILING = 100_000

# Newest messages read to find the fields of JSON values.
SAMPLE = 200

# Characters of a key or a value shown in a cell.
CELL_CHARACTERS = 65_536

# How long reading one page may take, all partitions together. A consume waits
# until it has its number of messages or its time is up, so each wait is short.
READ_SECONDS = 10.0

# A chunk read back at a time while a filter is looking for matches.
FILTER_CHUNK = 500

FIELD_PREFIX = "value."


@dataclass(frozen=True)
class Message:
    partition: int
    offset: int
    # Milliseconds since the epoch, or nothing when the producer set none.
    timestamp: int | None
    key: bytes | None
    value: bytes | None
    headers: tuple[tuple[str, bytes | None], ...]


def text_of(raw: bytes | None) -> str | None:
    """UTF-8 as text, anything else as hex, as MongoDB's bytes are (D284)."""
    if raw is None:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = "0x" + raw.hex()
    if len(text) > CELL_CHARACTERS:
        return text[:CELL_CHARACTERS] + "…"
    return text


def json_of(raw: bytes | None) -> Any:
    """A value that is a JSON object, or nothing."""
    if raw is None or not raw.lstrip().startswith(b"{"):
        return None
    try:
        parsed = jsontext.load(raw.decode("utf-8"))
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def is_json(raw: bytes | None) -> bool:
    if raw is None:
        return True
    try:
        jsontext.load(raw.decode("utf-8"))
    except ValueError:
        return False
    return True


def moment(milliseconds: int | None) -> str | None:
    if milliseconds is None:
        return None
    at = datetime.fromtimestamp(milliseconds / 1000, tz=UTC)
    return at.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def headers_of(message: Message) -> str | None:
    if not message.headers:
        return None
    return json.dumps(
        {name: text_of(value) for name, value in message.headers}, ensure_ascii=False
    )


def field_text(value: Any) -> str | None:
    """A field of a JSON value as a cell: a string as itself, the rest as JSON."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return jsontext.encode(value)


def _category(value: Any) -> TypeCategory:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, jsontext.JsonNumber):
        return "number"
    if isinstance(value, str):
        return "string"
    return "json"


# --- the columns ----------------------------------------------------------

_TEXT_OPS: list[FilterOp] = [
    "eq",
    "ne",
    "contains",
    "starts_with",
    "is_null",
    "is_not_null",
]
_RANGE_OPS: list[FilterOp] = ["gte", "gt", "lte", "lt"]


def _column(
    name: str,
    sql: str,
    category: TypeCategory,
    ops: list[FilterOp],
    *,
    sortable: bool = False,
    insertable: bool = True,
) -> FetchColumn:
    # Every column a message is sent with may be left empty (D308).
    return FetchColumn(
        name=name,
        type=ColumnType(sql=sql, category=category),
        sortable=sortable,
        filter_operators=ops,
        insertable=insertable,
        nullable=True,
    )


def fixed_columns(value_category: TypeCategory) -> list[FetchColumn]:
    return [
        _column("partition", "partition", "number", ["eq", "in"]),
        _column("offset", "offset", "number", _RANGE_OPS, insertable=False),
        _column("timestamp", "timestamp", "datetime", _RANGE_OPS, sortable=True),
        _column("key", "bytes", "string", _TEXT_OPS),
        _column("value", "bytes", value_category, _TEXT_OPS),
        _column("headers", "headers", "json", ["contains", "is_null", "is_not_null"]),
    ]


@dataclass(frozen=True)
class Shape:
    """What the newest messages say the columns are."""

    value_category: TypeCategory
    # Each field of the JSON values, in the order met, and its category.
    fields: tuple[tuple[str, TypeCategory], ...]

    def columns(self) -> list[FetchColumn]:
        columns = fixed_columns(self.value_category)
        for name, category in self.fields:
            ops = [*_TEXT_OPS, *(_RANGE_OPS if category == "number" else [])]
            columns.append(_column(FIELD_PREFIX + name, "field", category, ops))
        return columns


def shape_of(messages: list[Message]) -> Shape:
    all_json = all(is_json(message.value) for message in messages)
    found: dict[str, TypeCategory] = {}
    for message in messages:
        value = json_of(message.value)
        if value is None:
            continue
        for name, item in value.items():
            if item is None:
                found.setdefault(name, "string")
                continue
            category = _category(item)
            known = found.get(name)
            if known is None:
                found[name] = category
            elif known != category:
                found[name] = "string"
    return Shape(
        value_category="json" if all_json and messages else "string",
        fields=tuple(found.items()),
    )


def row_of(message: Message, fields: list[str]) -> list[str | None]:
    value = json_of(message.value) if fields else None
    return [
        str(message.partition),
        str(message.offset),
        moment(message.timestamp),
        text_of(message.key),
        text_of(message.value),
        headers_of(message),
        *[field_text(None if value is None else value.get(name)) for name in fields],
    ]


# --- where reading starts and stops ---------------------------------------


def _number(column: str, text: str) -> int:
    try:
        return int(text)
    except ValueError:
        raise ValueError(say("{column} takes a whole number", column=column)) from None


def milliseconds_of(text: str) -> int:
    try:
        at = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(say("timestamp takes a date and time")) from None
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    return int(at.timestamp() * 1000)


@dataclass
class Window:
    """Offsets to read in one partition, the end not included."""

    start: int
    end: int


def _offset_at(
    clients: KafkaClients, topic: str, partition: int, milliseconds: int, end: int
) -> int:
    """The first offset whose time is at or after the moment, or the end."""
    found = clients.consumer().offsets_for_times(
        [TopicPartition(topic, partition, milliseconds)], timeout=TIMEOUT_SECONDS
    )
    offset = found[0].offset if found else -1
    return end if offset < 0 else int(offset)


def windows(
    clients: KafkaClients, topic: str, filters: list[Filter]
) -> dict[int, Window]:
    """Each partition's offsets to read, narrowed by what Kafka can serve."""
    partitions = partitions_of(clients, topic)[topic]
    picked = set(partitions)
    for one in filters:
        if one.column != "partition":
            continue
        if isinstance(one, InFilter):
            picked &= {_number("partition", value) for value in one.values}
        elif isinstance(one, ScalarFilter):
            picked &= {_number("partition", one.value)}
    marks = watermarks(clients, {topic: sorted(picked)})
    found: dict[int, Window] = {}
    for partition in sorted(picked):
        low, high = marks.get((topic, partition), (0, 0))
        window = Window(low, high)
        for one in filters:
            if not isinstance(one, ScalarFilter) or one.column not in {
                "offset",
                "timestamp",
            }:
                continue
            if one.column == "offset":
                bound = _number("offset", one.value)
            else:
                moment_ms = milliseconds_of(one.value)
                # A time bound is the first offset at or after a moment.
                after = moment_ms + 1 if one.op in {"gt", "lte"} else moment_ms
                bound = _offset_at(clients, topic, partition, after, high)
            if one.column == "offset":
                if one.op == "gte":
                    window.start = max(window.start, bound)
                elif one.op == "gt":
                    window.start = max(window.start, bound + 1)
                elif one.op == "lte":
                    window.end = min(window.end, bound + 1)
                elif one.op == "lt":
                    window.end = min(window.end, bound)
            elif one.op in {"gte", "gt"}:
                window.start = max(window.start, bound)
            else:
                window.end = min(window.end, bound)
        found[partition] = window
    return found


# --- what is applied to what was read ---------------------------------------


def _cell(message: Message, column: str) -> str | None:
    if column == "key":
        return text_of(message.key)
    if column == "value":
        return text_of(message.value)
    if column == "headers":
        return headers_of(message)
    value = json_of(message.value)
    return None if value is None else field_text(value.get(column[len(FIELD_PREFIX) :]))


def _as_number(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


def _predicate(one: Filter) -> Callable[[Message], bool]:
    column = one.column
    if isinstance(one, NullFilter):
        wanted_null = one.op == "is_null"
        return lambda message: (_cell(message, column) is None) == wanted_null
    if isinstance(one, InFilter):
        values = set(one.values)
        return lambda message: _cell(message, column) in values
    needle = one.value
    folded = needle.casefold()
    if one.op in {"gt", "gte", "lt", "lte"}:
        limit = _as_number(needle)
        if limit is None:
            raise ValueError(say("{column} takes a number", column=column))

        def compares(message: Message) -> bool:
            cell = _cell(message, column)
            number = None if cell is None else _as_number(cell)
            if number is None:
                return False
            return {
                "gt": number > limit,
                "gte": number >= limit,
                "lt": number < limit,
                "lte": number <= limit,
            }[one.op]

        return compares
    if one.op == "contains":
        return lambda message: folded in (_cell(message, column) or "").casefold()
    if one.op == "starts_with":
        return lambda message: (
            (_cell(message, column) or "").casefold().startswith(folded)
        )
    if one.op == "ne":
        return lambda message: _cell(message, column) != needle
    return lambda message: _cell(message, column) == needle


def predicates(
    filters: list[Filter], columns: list[FetchColumn]
) -> list[Callable[[Message], bool]]:
    offered = {column.name: column.filter_operators for column in columns}
    found: list[Callable[[Message], bool]] = []
    for one in filters:
        ops = offered.get(one.column)
        if ops is None:
            raise ValueError(say("Unknown column: {column}", column=one.column))
        if one.op not in ops:
            raise ValueError(
                say("{column} cannot be filtered that way", column=one.column)
            )
        if one.column in {"partition", "offset", "timestamp"}:
            continue
        found.append(_predicate(one))
    return found


# --- reading -------------------------------------------------------------------


def read_ranges(
    clients: KafkaClients, topic: str, ranges: dict[int, Window]
) -> dict[int, list[Message]]:
    """The messages in each partition's window, read together."""
    wanted = {
        partition: window
        for partition, window in ranges.items()
        if window.end > window.start
    }
    found: dict[int, list[Message]] = {partition: [] for partition in ranges}
    if not wanted:
        return found
    consumer = clients.consumer()
    consumer.assign(
        [
            TopicPartition(topic, partition, window.start)
            for partition, window in wanted.items()
        ]
    )
    pending = set(wanted)
    deadline = time.monotonic() + READ_SECONDS
    try:
        while pending and time.monotonic() < deadline:
            for raw in consumer.consume(num_messages=FILTER_CHUNK, timeout=0.1):
                error = raw.error()
                partition = raw.partition()
                if error is not None:
                    if error.code() == KafkaError._PARTITION_EOF:
                        if partition in pending:
                            pending.discard(partition)
                            consumer.incremental_unassign(
                                [TopicPartition(topic, partition)]
                            )
                        continue
                    raise KafkaException(error)
                if partition not in pending:
                    continue
                offset = raw.offset()
                if offset is None:
                    continue
                window = wanted[partition]
                if offset < window.end:
                    found[partition].append(message_of(raw))
                if offset >= window.end - 1:
                    pending.discard(partition)
                    # Not paused: a paused partition stays paused when it is
                    # assigned again, and the next read gets nothing from it.
                    consumer.incremental_unassign([TopicPartition(topic, partition)])
    finally:
        consumer.unassign()
    return found


def message_of(raw: Any) -> Message:
    kind, milliseconds = raw.timestamp()
    return Message(
        partition=raw.partition(),
        offset=raw.offset(),
        # 0 is "no timestamp" in librdkafka's types.
        timestamp=None if kind == 0 or milliseconds < 0 else milliseconds,
        key=raw.key(),
        value=raw.value(),
        headers=tuple(raw.headers() or ()),
    )


@dataclass
class Collected:
    messages: list[Message]
    # A partition still had unread messages in its window when reading stopped.
    unread: bool


def collect(
    clients: KafkaClients,
    topic: str,
    limits: dict[int, Window],
    need: int,
    newest: bool,
    matches: list[Callable[[Message], bool]],
) -> Collected:
    """Up to `need` matching messages from each partition, from the chosen end.

    Without a filter one read each is enough; with one, chunks are read back
    (or on) until enough match, the window is done or the ceiling is reached.
    """
    chunk = need if not matches else max(need, FILTER_CHUNK)
    cursors = {
        partition: Window(window.start, window.end)
        for partition, window in limits.items()
    }
    kept: dict[int, list[Message]] = {partition: [] for partition in limits}
    scanned = 0
    while True:
        ranges: dict[int, Window] = {}
        for partition, cursor in cursors.items():
            if cursor.end <= cursor.start or len(kept[partition]) >= need:
                continue
            if newest:
                ranges[partition] = Window(
                    max(cursor.start, cursor.end - chunk), cursor.end
                )
            else:
                ranges[partition] = Window(
                    cursor.start, min(cursor.end, cursor.start + chunk)
                )
        if not ranges or scanned >= SCAN_CEILING:
            break
        read = read_ranges(clients, topic, ranges)
        for partition, window in ranges.items():
            got = read[partition]
            scanned += window.end - window.start
            hits = [
                message for message in got if all(match(message) for match in matches)
            ]
            if newest:
                kept[partition] = hits + kept[partition]
                cursors[partition].end = window.start
            else:
                kept[partition] = kept[partition] + hits
                cursors[partition].start = window.end
        if not matches:
            break
    messages: list[Message] = []
    for hits in kept.values():
        messages.extend(hits[-need:] if newest else hits[:need])
    unread = any(
        cursor.end > cursor.start and len(kept[partition]) < need
        for partition, cursor in cursors.items()
    )
    return Collected(messages, unread)


def ordered(messages: list[Message], newest: bool) -> list[Message]:
    def key(message: Message) -> tuple[int, int, int]:
        return (
            message.timestamp if message.timestamp is not None else -1,
            message.partition,
            message.offset,
        )

    return sorted(messages, key=key, reverse=newest)


def newest_first(request: FetchRequest) -> bool:
    if not request.sort:
        return True
    if len(request.sort) > 1 or request.sort[0].column != "timestamp":
        raise ValueError(say("Messages are ordered by their time only"))
    return request.sort[0].descending


def sample(clients: KafkaClients, topic: str) -> Shape:
    limits = windows(clients, topic, [])
    collected = collect(clients, topic, limits, SAMPLE, True, [])
    return shape_of(ordered(collected.messages, True)[:SAMPLE])


def read_page(clients: KafkaClients, topic: str, request: FetchRequest) -> FetchResult:
    if request.offset + request.limit > DEPTH_CEILING:
        raise ValueError(
            say(
                "A page reaches at most {n} messages deep; narrow it by time or partition",
                n=DEPTH_CEILING,
            )
        )
    newest = newest_first(request)
    shape = sample(clients, topic)
    columns = shape.columns()
    matches = predicates(request.filters, columns)
    limits = windows(clients, topic, request.filters)
    need = request.offset + request.limit + 1
    collected = collect(clients, topic, limits, need, newest, matches)
    merged = ordered(collected.messages, newest)
    page = merged[request.offset : request.offset + request.limit]
    fields = [name for name, _ in shape.fields]
    # A field met on the page but not in the sample is shown, offered for
    # nothing, as a MongoDB page's is (D284).
    for message in page:
        value = json_of(message.value)
        for name in value or {}:
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
        row_handles=[f"{message.partition}:{message.offset}" for message in page],
        has_more=len(merged) > request.offset + request.limit or collected.unread,
        page_commands=["download", "chart", "share"],
        insert_supported=not is_internal(topic),
        insert_reason=sending_reason(topic),
    )


def sending_reason(topic: str) -> str | None:
    """Why no message is sent to this topic from here, or nothing."""
    if is_internal(topic):
        return say("Kafka's own topics are not written to from here")
    return None


def read_export(
    clients: KafkaClients, topic: str, request: ExportRequest
) -> list[list[str | None]]:
    """Every message the page's filters and order would show, to its depth (D310)."""
    newest = newest_first(FetchRequest(node_id=request.node_id, sort=request.sort))
    shape = sample(clients, topic)
    columns = shape.columns()
    names = [column.name for column in columns]
    unknown = [column for column in request.columns if column not in names]
    if unknown:
        raise ValueError(say("Unknown column: {column}", column=unknown[0]))
    matches = predicates(request.filters, columns)
    limits = windows(clients, topic, request.filters)
    collected = collect(clients, topic, limits, DEPTH_CEILING, newest, matches)
    merged = ordered(collected.messages, newest)[:DEPTH_CEILING]
    fields = [name for name, _ in shape.fields]
    picked = [names.index(column) for column in request.columns]
    return [
        [row[index] for index in picked]
        for row in (row_of(one, fields) for one in merged)
    ]


class KafkaMessages:
    def __init__(self, session: KafkaSession) -> None:
        self._session = session

    async def fetch(self, request: FetchRequest) -> FetchResult:
        topic = topic_of(request.node_id)
        return await self._session.run(
            lambda clients: read_page(clients, topic, request), request.node_id
        )

    async def export_rows(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        topic = topic_of(request.node_id)
        rows = await self._session.run(
            lambda clients: read_export(clients, topic, request), request.node_id
        )
        for start in range(0, len(rows), EXPORT_BATCH_SIZE):
            yield ExportBatch(rows=rows[start : start + EXPORT_BATCH_SIZE])
