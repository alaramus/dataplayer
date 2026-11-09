"""Messages sent as new rows of a stream (D329).

A row is read whole into a message before anything is sent, so a value that
will not read rejects the block with the cells named. The block is then
published through the default exchange, the stream's name as its routing key,
on a channel with publisher confirms, every message waited for. No
transaction: a block that fails half way has sent its first half.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import aio_pika
from aio_pika.abc import AbstractChannel, DeliveryMode
from aiormq.abc import DeliveredMessage
from pamqp.commands import Basic

from app.adapters import jsontext
from app.adapters.message_cells import (
    bytes_of,
    field_text,
    field_value,
    json_of,
    json_text,
    milliseconds_of,
    moment,
    text_of,
)
from app.adapters.rabbitmq.catalog import parse, read_queue
from app.adapters.rabbitmq.session import RabbitmqSession
from app.adapters.rabbitmq.streams import FIELD_PREFIX, PREFETCH, end_of, sample
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

# The columns a message is sent with; the fields of a JSON body besides.
SENT = ("timestamp", "content_type", "headers", "properties", "body")

# The properties a row may set, as AMQP names them (D329).
PROPERTIES = (
    "message_id",
    "correlation_id",
    "reply_to",
    "priority",
    "expiration",
    "type",
    "app_id",
    "delivery_mode",
)


class Unreadable(ValueError):
    def __init__(self, column: str) -> None:
        super().__init__(column)
        self.column = column


@dataclass(frozen=True)
class Outgoing:
    body: bytes
    timestamp: datetime | None
    content_type: str | None
    headers: dict[str, Any]
    properties: dict[str, Any]

    def message(self) -> aio_pika.Message:
        properties = dict(self.properties)
        mode = properties.pop("delivery_mode", None)
        priority = properties.pop("priority", None)
        expiration = properties.pop("expiration", None)
        return aio_pika.Message(
            self.body,
            headers=self.headers or None,
            content_type=self.content_type,
            timestamp=self.timestamp,
            delivery_mode=DeliveryMode(mode) if mode is not None else None,
            priority=priority,
            expiration=None if expiration is None else int(expiration) / 1000,
            **{name: str(value) for name, value in properties.items()},
        )


def _properties(text: str) -> dict[str, Any]:
    parsed = json.loads(text)
    if not isinstance(parsed, dict) or set(parsed) - set(PROPERTIES):
        raise ValueError(text)
    for name in ("priority", "delivery_mode"):
        value = parsed.get(name)
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool)
        ):
            raise ValueError(text)
    if parsed.get("delivery_mode") not in {None, 1, 2}:
        raise ValueError(text)
    if parsed.get("priority") is not None and not 0 <= parsed["priority"] <= 255:
        raise ValueError(text)
    expiration = parsed.get("expiration")
    if expiration is not None and not str(expiration).isdigit():
        raise ValueError(text)
    return {name: value for name, value in parsed.items() if value is not None}


def _headers(text: str) -> dict[str, Any]:
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError(text)
    return parsed


def outgoing(
    columns: Sequence[str],
    values: Sequence[str | None],
    fields: dict[str, TypeCategory],
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

    stamp = read("timestamp", milliseconds_of)
    body = read("body", bytes_of)
    if body is None:
        # Fields given and no body: the body is a JSON object of them.
        document = {
            name: read(
                FIELD_PREFIX + name, lambda text, c=category: field_value(text, c)
            )
            for name, category in fields.items()
            if given.get(FIELD_PREFIX + name) not in {None, ""}
        }
        body = jsontext.encode(document).encode("utf-8") if document else b""
        content_type = given.get("content_type") or (
            "application/json" if document else None
        )
    else:
        content_type = given.get("content_type") or None
    return Outgoing(
        body=body,
        timestamp=None if stamp is None else datetime.fromtimestamp(stamp / 1000, UTC),
        content_type=content_type,
        headers=read("headers", _headers) or {},
        properties=read("properties", _properties) or {},
    )


async def publish(
    channel: AbstractChannel, exchange: str, routing_key: str, messages: list[Outgoing]
) -> int:
    """Every message published and confirmed, in order; how many routed nowhere."""
    target = (
        channel.default_exchange
        if exchange == ""
        else await channel.get_exchange(exchange, ensure=False)
    )
    unroutable = 0
    for one in messages:
        confirmed = await target.publish(
            one.message(), routing_key=routing_key, mandatory=True
        )
        # A mandatory message no queue took comes back as Basic.Return.
        if isinstance(confirmed, DeliveredMessage) and isinstance(
            confirmed.delivery, Basic.Return
        ):
            unroutable += 1
    return unroutable


@dataclass(frozen=True)
class Target:
    vhost: str
    stream: str
    fields: dict[str, TypeCategory]


class RabbitmqWrites:
    def __init__(self, session: RabbitmqSession) -> None:
        self._session = session

    async def _target(self, node_id: str, channel: AbstractChannel) -> Target:
        named = parse(node_id)
        if named.prefix != "stream" or named.name is None:
            raise ValueError(
                say("A message is sent as a new row of a stream; use Publish elsewhere")
            )
        await read_queue(self._session, named.vhost, named.name, stream=True)
        await channel.set_qos(prefetch_count=PREFETCH)
        shape = await sample(channel, named.name, await end_of(channel, named.name))
        return Target(named.vhost, named.name, dict(shape.fields))

    async def insert_row(self, request: InsertRowRequest) -> InsertRowResult:
        columns = [item.column for item in request.values]
        values = [item.value for item in request.values]
        vhost = parse(request.node_id).vhost
        async with self._session.channel(request.node_id, vhost=vhost) as channel:
            aim = await self._target(request.node_id, channel)
            try:
                message = outgoing(columns, values, aim.fields)
            except Unreadable as wrong:
                raise ValueError(
                    say("That value cannot be read for {column}", column=wrong.column)
                ) from None
            await publish(channel, "", aim.stream, [message])
        # The offset is the stream's to give and is not told to a publisher:
        # the row is what was sent, and a refresh shows where it landed.
        stamp = message.timestamp
        document = json_of(message.body)
        return InsertRowResult(
            values=[
                None,
                None if stamp is None else moment(int(stamp.timestamp() * 1000)),
                "",
                aim.stream,
                message.content_type,
                json_text(message.headers),
                json_text(message.properties),
                text_of(message.body),
                *[
                    field_text(None if document is None else document.get(name))
                    for name in aim.fields
                ],
            ],
            row_handle=None,
        )

    async def insert_rows(self, request: InsertRowsRequest) -> InsertRowsResult:
        vhost = parse(request.node_id).vhost
        async with self._session.channel(request.node_id, vhost=vhost) as channel:
            aim = await self._target(request.node_id, channel)
            messages: list[Outgoing] = []
            rejected: list[RejectedValue] = []
            for index, row in enumerate(request.rows):
                try:
                    messages.append(outgoing(request.columns, row, aim.fields))
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
            await publish(channel, "", aim.stream, messages)
        return RowsInserted(inserted=len(messages))
