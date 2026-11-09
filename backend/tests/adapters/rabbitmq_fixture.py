"""A virtual host of known shape on the RabbitMQ the suite talks to.

Made with aio-pika and the management API directly rather than through the
adapter, named afresh per run — with a slash and a space, so ids and paths
are proved to carry them — and deleted afterwards, everything in it with it.
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import aio_pika
import httpx

from app.adapters.rabbitmq.adapter import RabbitmqAdapter
from app.adapters.rabbitmq.options import RabbitmqOptions
from tests.utils.services import RABBITMQ

# JSON orders in the stream, offsets 0 to ORDERS - 1, then one body that is
# not text at offset ORDERS.
ORDERS = 60
T0 = 1_700_000_000
BINARY_BODY = b"\xff\x00 not json"

EXCHANGE = "dp.orders"
QUEUE = "billing"
QUORUM = "audit"
STREAM = "orders.log"
ROUTING_KEY = "orders.#"
WAITING = 3


def _parts() -> Any:
    return urlsplit(RABBITMQ.require())


def amqp_host() -> str:
    return _parts().hostname or "127.0.0.1"


def amqp_port() -> int:
    return int(_parts().port or 5672)


def user() -> str:
    return unquote(_parts().username or "guest")


def password() -> str:
    return unquote(_parts().password or "guest")


def management() -> str:
    """10000 ports above AMQP, by RabbitMQ's own defaults (tests/utils/services.py)."""
    return f"http://{amqp_host()}:{amqp_port() + 10000}"


def options(vhost: str = "", **changes: Any) -> RabbitmqOptions:
    values: dict[str, Any] = {
        "host": amqp_host(),
        "port": amqp_port(),
        "management_url": management(),
        "user": user(),
        "password": password(),
        "vhost": vhost,
    }
    values.update(changes)
    return RabbitmqOptions(**values)


def adapter(made: RabbitmqOptions | None = None) -> RabbitmqAdapter:
    return RabbitmqAdapter(made or options())


def order(index: int) -> dict[str, Any]:
    return {"id": index, "price": index * 1.5, "side": "buy" if index % 2 else "sell"}


def names() -> str:
    return f"dp test/{uuid.uuid4().hex[:12]}"


def _api() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=management() + "/api", auth=(user(), password()), timeout=10
    )


async def make(vhost: str) -> None:
    segment = quote(vhost, safe="")
    async with _api() as api:
        (await api.put(f"/vhosts/{segment}")).raise_for_status()
        (
            await api.put(
                f"/permissions/{segment}/{quote(user(), safe='')}",
                json={"configure": ".*", "write": ".*", "read": ".*"},
            )
        ).raise_for_status()
    connection = await aio_pika.connect(
        host=amqp_host(),
        port=amqp_port(),
        login=user(),
        password=password(),
        virtualhost=vhost,
    )
    async with connection:
        channel = await connection.channel()
        exchange = await channel.declare_exchange(
            EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
        )
        billing = await channel.declare_queue(QUEUE, durable=True)
        await billing.bind(exchange, ROUTING_KEY)
        await channel.declare_queue(
            QUORUM, durable=True, arguments={"x-queue-type": "quorum"}
        )
        await channel.declare_queue(
            STREAM, durable=True, arguments={"x-queue-type": "stream"}
        )
        for index in range(ORDERS):
            await channel.default_exchange.publish(
                aio_pika.Message(
                    json.dumps(order(index)).encode(),
                    content_type="application/json",
                    headers={"source": "fixture"},
                    timestamp=datetime.fromtimestamp(T0 + index, tz=UTC),
                    message_id=f"m{index}",
                ),
                routing_key=STREAM,
            )
        await channel.default_exchange.publish(
            aio_pika.Message(BINARY_BODY), routing_key=STREAM
        )
        # Messages nobody takes, waiting in the classic queue.
        for index in range(WAITING):
            await exchange.publish(
                aio_pika.Message(json.dumps(order(index)).encode()),
                routing_key="orders.new",
            )


async def remove(vhost: str) -> None:
    async with _api() as api:
        response = await api.delete(f"/vhosts/{quote(vhost, safe='')}")
        if response.status_code != 404:
            response.raise_for_status()
