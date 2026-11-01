"""Messages sent as new rows of a topic (D308).

A row is read whole into a message before anything is sent, so a value that
will not read rejects the block with the cells named. The block is then sent
by an idempotent producer and waited for.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from confluent_kafka import KafkaError, KafkaException

from app.adapters import jsontext
from app.adapters.kafka.catalog import partitions_of, topic_of
from app.adapters.kafka.messages import (
    FIELD_PREFIX,
    Message,
    message_of,
    milliseconds_of,
    row_of,
    sample,
    sending_reason,
)
from app.adapters.kafka.session import SEND_SECONDS, KafkaClients, KafkaSession
from app.adapters.relation import TypeCategory
from app.adapters.update import (
    InsertRowRequest,
    InsertRowResult,
    InsertRowsRequest,
    InsertRowsResult,
    RejectedValue,
    RowsInserted,
    ValuesRejected,
)
from app.core.translation import say

# The columns a message is sent with; the fields of a JSON value besides.
SENT = ("partition", "timestamp", "key", "value", "headers")


@dataclass(frozen=True)
class Outgoing:
    partition: int | None
    timestamp: int | None
    key: bytes | None
    value: bytes | None
    headers: list[tuple[str, str | bytes | None]]


class Unreadable(ValueError):
    def __init__(self, column: str) -> None:
        super().__init__(column)
        self.column = column


def bytes_of(text: str) -> bytes:
    """`0x` and hex digits is those bytes, as they are shown; anything else UTF-8."""
    if text.startswith("0x") and len(text) % 2 == 0 and len(text) > 2:
        try:
            return bytes.fromhex(text[2:])
        except ValueError:
            pass
    return text.encode("utf-8")


def _field_value(text: str, category: TypeCategory) -> Any:
    """A field of a JSON value, read as its column's JSON type."""
    if category in {"number", "boolean", "json"}:
        parsed = jsontext.load(text)
        if category == "number" and not isinstance(parsed, jsontext.JsonNumber):
            raise ValueError(text)
        if category == "boolean" and not isinstance(parsed, bool):
            raise ValueError(text)
        return parsed
    return text


def outgoing(
    columns: Sequence[str],
    values: Sequence[str | None],
    fields: dict[str, TypeCategory],
    partitions: set[int],
) -> Outgoing:
    """One row as a message, or `Unreadable` naming the first cell that is not."""
    given = dict(zip(columns, values, strict=True))
    for column in columns:
        if column not in SENT and not (
            column.startswith(FIELD_PREFIX) and column[len(FIELD_PREFIX) :] in fields
        ):
            raise ValueError(say("Unknown column: {column}", column=column))

    def read(column: str, reader: Any) -> Any:
        text = given.get(column)
        if text is None or text == "":
            return None
        try:
            return reader(text)
        except ValueError:
            raise Unreadable(column) from None

    partition = read("partition", int)
    if partition is not None and partition not in partitions:
        raise Unreadable("partition")
    timestamp = read("timestamp", milliseconds_of)
    key = read("key", bytes_of)
    value = read("value", bytes_of)
    raw_headers = read("headers", json.loads)
    headers: list[tuple[str, str | bytes | None]] = []
    if raw_headers is not None:
        if not isinstance(raw_headers, dict) or not all(
            item is None or isinstance(item, str) for item in raw_headers.values()
        ):
            raise Unreadable("headers")
        headers = [
            (name, None if item is None else item.encode("utf-8"))
            for name, item in raw_headers.items()
        ]
    if value is None:
        # Fields given and no value: the value is a JSON object of them.
        document = {
            name: read(
                FIELD_PREFIX + name, lambda text, c=category: _field_value(text, c)
            )
            for name, category in fields.items()
            if given.get(FIELD_PREFIX + name) not in {None, ""}
        }
        if document:
            value = jsontext.encode(document).encode("utf-8")
    return Outgoing(partition, timestamp, key, value, headers)


def send(clients: KafkaClients, topic: str, messages: list[Outgoing]) -> list[Message]:
    """Every message sent and acknowledged, in order, or the failure."""
    producer = clients.producer()
    delivered: list[Any] = []
    failed: list[KafkaError] = []

    def report(error: KafkaError | None, message: Any) -> None:
        if error is not None:
            failed.append(error)
        else:
            delivered.append(message)

    for one in messages:
        extra: dict[str, Any] = {}
        if one.partition is not None:
            extra["partition"] = one.partition
        if one.timestamp is not None:
            extra["timestamp"] = one.timestamp
        while True:
            try:
                producer.produce(
                    topic,
                    key=one.key,
                    value=one.value,
                    headers=one.headers or None,
                    on_delivery=report,
                    **extra,
                )
                break
            except BufferError:
                # The producer's queue is full: let it send, then go on.
                producer.poll(0.5)
        producer.poll(0)
    left = producer.flush(SEND_SECONDS)
    if failed:
        raise KafkaException(failed[0])
    if left > 0:
        raise KafkaException(KafkaError(KafkaError._MSG_TIMED_OUT))
    return [message_of(message) for message in delivered]


@dataclass(frozen=True)
class Target:
    topic: str
    fields: dict[str, TypeCategory]
    partitions: set[int]


def target(clients: KafkaClients, node_id: str) -> Target:
    topic = topic_of(node_id)
    reason = sending_reason(topic)
    if reason is not None:
        raise ValueError(reason)
    partitions = set(partitions_of(clients, topic)[topic])
    shape = sample(clients, topic)
    return Target(topic, dict(shape.fields), partitions)


class KafkaWrites:
    def __init__(self, session: KafkaSession) -> None:
        self._session = session

    async def insert_row(self, request: InsertRowRequest) -> InsertRowResult:
        columns = [item.column for item in request.values]
        values = [item.value for item in request.values]

        def work(clients: KafkaClients) -> InsertRowResult:
            aim = target(clients, request.node_id)
            try:
                message = outgoing(columns, values, aim.fields, aim.partitions)
            except Unreadable as wrong:
                raise ValueError(
                    say("That value cannot be read for {column}", column=wrong.column)
                ) from None
            [delivered] = send(clients, aim.topic, [message])
            # A delivery report carries no headers; they are the ones sent.
            sent = replace(
                delivered,
                headers=tuple(
                    (name, item.encode("utf-8") if isinstance(item, str) else item)
                    for name, item in message.headers
                ),
            )
            return InsertRowResult(
                values=row_of(sent, list(aim.fields)),
                row_handle=f"{sent.partition}:{sent.offset}",
            )

        return await self._session.run(work, request.node_id)

    async def insert_rows(self, request: InsertRowsRequest) -> InsertRowsResult:
        def work(clients: KafkaClients) -> InsertRowsResult:
            aim = target(clients, request.node_id)
            messages: list[Outgoing] = []
            rejected: list[RejectedValue] = []
            for index, row in enumerate(request.rows):
                try:
                    messages.append(
                        outgoing(request.columns, row, aim.fields, aim.partitions)
                    )
                except Unreadable as wrong:
                    value = row[request.columns.index(wrong.column)]
                    rejected.append(
                        RejectedValue(
                            row=index,
                            column=wrong.column,
                            value=None if value is None else value[:200],
                        )
                    )
            if rejected:
                return ValuesRejected(cells=rejected)
            send(clients, aim.topic, messages)
            return RowsInserted(inserted=len(messages))

        return await self._session.run(work, request.node_id)
