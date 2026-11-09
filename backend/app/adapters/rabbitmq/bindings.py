"""A queue's and an exchange's bindings as rows (D326).

A queue's: which exchange routes to it, with which key and arguments. An
exchange's: where it routes, a queue or another exchange. The default
exchange's are its implicit binding of every queue by name, which the API
lists under `amq.default`. Counted in tens, so the page is cut here.
"""

import json
from collections.abc import AsyncIterator
from typing import Any

from app.adapters.export import EXPORT_BATCH_SIZE, ExportBatch, ExportRequest
from app.adapters.fetch import FetchColumn, FetchRequest, FetchResult
from app.adapters.rabbitmq.catalog import (
    exchange_path,
    parse,
    read_exchange,
    read_queue,
)
from app.adapters.rabbitmq.session import RabbitmqSession, segment
from app.adapters.relation import ColumnType, TypeCategory
from app.core.translation import say

_QUEUE_SHAPE: tuple[tuple[str, TypeCategory], ...] = (
    ("exchange", "string"),
    ("routing_key", "string"),
    ("arguments", "json"),
)
_EXCHANGE_SHAPE: tuple[tuple[str, TypeCategory], ...] = (
    ("destination", "string"),
    ("destination_type", "string"),
    ("routing_key", "string"),
    ("arguments", "json"),
)


def _columns(shape: tuple[tuple[str, TypeCategory], ...]) -> list[FetchColumn]:
    return [
        FetchColumn(name=name, type=ColumnType(sql=name, category=category))
        for name, category in shape
    ]


def _arguments(value: Any) -> str | None:
    if not isinstance(value, dict) or not value:
        return None
    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)


def _row(binding: dict[str, Any], of_queue: bool) -> list[str | None]:
    key = binding.get("routing_key")
    routing_key = str(key) if key is not None else None
    if of_queue:
        return [
            str(binding.get("source", "")),
            routing_key,
            _arguments(binding.get("arguments")),
        ]
    return [
        str(binding.get("destination", "")),
        str(binding.get("destination_type", "")),
        routing_key,
        _arguments(binding.get("arguments")),
    ]


class RabbitmqBindings:
    def __init__(self, session: RabbitmqSession) -> None:
        self._session = session

    async def _read(
        self, node_id: str
    ) -> tuple[list[FetchColumn], list[list[str | None]]]:
        named = parse(node_id)
        if named.name is None or named.prefix not in {"queue", "exchange"}:
            raise ValueError(say("Not a node of this connection"))
        vhost = segment(named.vhost)
        # Asked first: the API answers a missing queue's bindings with none
        # rather than a 404.
        if named.prefix == "queue":
            await read_queue(self._session, named.vhost, named.name, stream=False)
            path = f"/queues/{vhost}/{segment(named.name)}/bindings"
        else:
            await read_exchange(self._session, named.vhost, named.name)
            path = f"/exchanges/{vhost}/{exchange_path(named.name)}/bindings/source"
        answer = await self._session.api(path, node_id=node_id)
        of_queue = named.prefix == "queue"
        bindings = sorted(
            (one for one in answer if isinstance(one, dict)),
            key=lambda one: (
                str(one.get("source" if of_queue else "destination", "")),
                str(one.get("routing_key", "")),
            ),
        )
        columns = _columns(_QUEUE_SHAPE if of_queue else _EXCHANGE_SHAPE)
        return columns, [_row(one, of_queue) for one in bindings]

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if request.filters or request.sort:
            raise ValueError(say("Bindings are listed in their own order"))
        columns, rows = await self._read(request.node_id)
        page = rows[request.offset : request.offset + request.limit]
        return FetchResult(
            columns=columns,
            rows=page,
            has_more=len(rows) > request.offset + request.limit,
            page_commands=["download", "share"],
        )

    async def export_rows(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        if request.filters or request.sort:
            raise ValueError(say("Bindings are listed in their own order"))
        columns, rows = await self._read(request.node_id)
        names = [column.name for column in columns]
        unknown = [column for column in request.columns if column not in names]
        if unknown:
            raise ValueError(say("Unknown column: {column}", column=unknown[0]))
        picked = [names.index(column) for column in request.columns]
        for start in range(0, len(rows), EXPORT_BATCH_SIZE):
            yield ExportBatch(
                rows=[
                    [row[index] for index in picked]
                    for row in rows[start : start + EXPORT_BATCH_SIZE]
                ]
            )
