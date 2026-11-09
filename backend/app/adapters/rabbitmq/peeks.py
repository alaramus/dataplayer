"""A look inside a queue, taken once and kept (D330).

The management API's `get` with `ack_requeue_true` takes messages and puts
them back: a delivery, which marks them redelivered and counts towards a
quorum queue's delivery limit. So a look is taken by an action, never by
opening a node, and what it read is kept in the resource store as a snapshot
the client opens. Paging a snapshot reads the snapshot, never the queue.
"""

import base64
import binascii
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.adapters.catalog import ReportNode
from app.adapters.content import NodeRepresentation
from app.adapters.fetch import FetchColumn, FetchRequest, FetchResult
from app.adapters.message_cells import (
    body_shape,
    field_text,
    json_of,
    json_text,
    moment,
    text_of,
)
from app.adapters.protocol import NodeNotFound
from app.adapters.rabbitmq.catalog import parse, peek_id
from app.adapters.rabbitmq.session import RabbitmqSession, segment
from app.adapters.relation import ColumnType, TypeCategory
from app.adapters.resources import Pooling
from app.adapters.words import worded_titles
from app.core.translation import N_, say

# Messages one look may take; each is a delivery, so the ceiling is low.
PEEK_CEILING = 100

# Snapshots kept for a connection; the oldest goes first.
SHELF_SIZE = 20

# Characters of a body the API hands back; a longer one is cut by the broker.
TRUNCATE = 65_536

LOOK = NodeRepresentation(kind="table", title=N_("View the messages"))

FIELD_PREFIX = "body."


@dataclass(frozen=True)
class Peeked:
    """One message as the management API's `get` answers it."""

    redelivered: bool
    exchange: str
    routing_key: str
    properties: dict[str, Any]
    body: bytes


@dataclass(frozen=True)
class Snapshot:
    vhost: str
    queue: str
    taken_at: datetime
    messages: list[Peeked]
    # Messages left in the queue when the look was taken, as the broker said.
    left: int | None


@dataclass
class PeekShelf:
    """A connection's snapshots, the newest last; kept in the resource store."""

    snapshots: OrderedDict[int, Snapshot] = field(default_factory=OrderedDict)
    counter: int = 0

    def put(self, snapshot: Snapshot) -> int:
        self.counter += 1
        self.snapshots[self.counter] = snapshot
        while len(self.snapshots) > SHELF_SIZE:
            self.snapshots.popitem(last=False)
        return self.counter

    async def close(self) -> None:
        self.snapshots.clear()


def _key(connector_id: uuid.UUID) -> str:
    return f"rabbitmq-peek:{connector_id}"


def peeked_of(raw: dict[str, Any]) -> Peeked:
    payload = raw.get("payload")
    text = payload if isinstance(payload, str) else ""
    if raw.get("payload_encoding") == "base64":
        try:
            body = base64.b64decode(text, validate=True)
        except binascii.Error, ValueError:
            body = text.encode("utf-8")
    else:
        body = text.encode("utf-8")
    properties = raw.get("properties")
    return Peeked(
        redelivered=bool(raw.get("redelivered", False)),
        exchange=str(raw.get("exchange", "")),
        routing_key=str(raw.get("routing_key", "")),
        properties=properties if isinstance(properties, dict) else {},
        body=body,
    )


def _columns(
    fields: tuple[tuple[str, TypeCategory], ...], body: TypeCategory
) -> list[FetchColumn]:
    shape: list[tuple[str, TypeCategory]] = [
        ("position", "number"),
        ("redelivered", "boolean"),
        ("exchange", "string"),
        ("routing_key", "string"),
        ("timestamp", "datetime"),
        ("content_type", "string"),
        ("headers", "json"),
        ("properties", "json"),
        ("body", body),
        *[(FIELD_PREFIX + name, category) for name, category in fields],
    ]
    return [
        FetchColumn(
            name=name, type=ColumnType(sql=name, category=category), nullable=True
        )
        for name, category in shape
    ]


def _row(position: int, one: Peeked, fields: list[str]) -> list[str | None]:
    properties = dict(one.properties)
    headers = properties.pop("headers", None)
    stamp = properties.pop("timestamp", None)
    content_type = properties.pop("content_type", None)
    value = json_of(one.body) if fields else None
    return [
        str(position),
        "true" if one.redelivered else "false",
        one.exchange,
        one.routing_key,
        moment(stamp * 1000) if isinstance(stamp, int) else None,
        str(content_type) if content_type else None,
        json_text(headers) if isinstance(headers, dict) else None,
        json_text(properties),
        text_of(one.body),
        *[field_text(None if value is None else value.get(name)) for name in fields],
    ]


class RabbitmqPeeks:
    def __init__(self, session: RabbitmqSession, pooling: Pooling | None) -> None:
        self._session = session
        self._pooling = pooling

    async def _shelf(self, create: bool) -> PeekShelf | None:
        pooling = self._pooling
        if pooling is None or not pooling.store.keeps:
            return None
        key = _key(pooling.connector_id)
        if not create:
            return await pooling.store.existing(key, PeekShelf)

        async def made() -> PeekShelf:
            return PeekShelf()

        return await pooling.store.get_or_create(key, PeekShelf, made)

    async def take(self, vhost: str, queue: str, count: int) -> str:
        """Up to `count` messages taken and put back; the snapshot's node id."""
        shelf = await self._shelf(create=True)
        if shelf is None:
            raise ValueError(say("A look is kept for a saved connection only"))
        answer = await self._session.change(
            "POST",
            f"/queues/{segment(vhost)}/{segment(queue)}/get",
            {
                "count": count,
                "ackmode": "ack_requeue_true",
                "encoding": "auto",
                "truncate": TRUNCATE,
            },
        )
        raw = [one for one in answer or [] if isinstance(one, dict)]
        left = raw[-1].get("message_count") if raw else None
        snapshot = Snapshot(
            vhost=vhost,
            queue=queue,
            taken_at=datetime.now(UTC),
            messages=[peeked_of(one) for one in raw],
            left=left if isinstance(left, int) else None,
        )
        return peek_id(vhost, queue, shelf.put(snapshot))

    async def snapshot(self, node_id: str) -> Snapshot:
        named = parse(node_id)
        shelf = await self._shelf(create=False)
        found = (
            None
            if shelf is None or named.snapshot is None
            else shelf.snapshots.get(named.snapshot)
        )
        if found is None or found.queue != named.name or found.vhost != named.vhost:
            raise NodeNotFound(node_id)
        return found

    def node(self, node_id: str, snapshot: Snapshot) -> ReportNode:
        # The server does not know the reader's zone, so it says its own.
        at = snapshot.taken_at.strftime("%H:%M:%S UTC")
        return ReportNode(
            id=node_id,
            name=say(
                "{queue}: {count} messages at {time}",
                queue=snapshot.queue,
                count=len(snapshot.messages),
                time=at,
            ),
            has_children=False,
            representations=worded_titles([LOOK]),
            description=say("Looked at once; the queue is not read again from here"),
        )

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if request.filters or request.sort:
            raise ValueError(say("A look is shown as it was taken"))
        snapshot = await self.snapshot(request.node_id)
        body, fields = body_shape([one.body for one in snapshot.messages])
        names = [name for name, _ in fields]
        page = snapshot.messages[request.offset : request.offset + request.limit]
        return FetchResult(
            columns=_columns(fields, body),
            rows=[
                _row(request.offset + index + 1, one, names)
                for index, one in enumerate(page)
            ],
            has_more=len(snapshot.messages) > request.offset + request.limit,
            page_commands=["download", "share"],
        )
