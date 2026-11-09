"""Something worth looking at, put into a RabbitMQ this server started (D332).

An empty broker shows the exchanges every virtual host is made with and
nothing else. The lab is what an application leaves: a topic exchange routing
orders to a classic queue and a quorum one, a dead-letter exchange, a headers
exchange matching alerts, and a stream of trades with a few bodies that are
bytes. Written out rather than generated, so two demonstrations look the same;
nothing consumes, so every count stays where the lab left it.
"""

import json
import struct
from datetime import UTC, datetime, timedelta

from app.adapters.rabbitmq.session import RabbitmqSession, segment
from app.adapters.rabbitmq.writes import Outgoing, publish
from app.core.translation import say

ORDERS = "lab.orders"
BILLING = "lab.billing"
SHIPPING = "lab.shipping"
DEAD_LETTER = "lab.dead-letter"
DEAD = "lab.dead"
ALERTS = "lab.alerts"
CRITICAL = "lab.alerts.critical"
TRADES = "lab.trades"

# The day the lab's trades and orders happened on.
DAY = datetime(2026, 1, 15, tzinfo=UTC)
CUSTOMERS = ("acme", "globex", "initech", "umbrella", "hooli", "stark")
PRODUCTS = (("keyboard", 49.9), ("monitor", 219.0), ("mouse", 19.5), ("dock", 129.0))
SYMBOLS = (("BTCUSDT", 65000.0), ("ETHUSDT", 3200.0), ("SOLUSDT", 140.0))

ORDER_COUNT = 60
TRADE_COUNT = 300
BYTES_COUNT = 5


def _json(value: dict[str, object], at: datetime, **headers: str) -> Outgoing:
    return Outgoing(
        body=json.dumps(value).encode("utf-8"),
        timestamp=at,
        content_type="application/json",
        headers=dict(headers),
        properties={},
    )


def orders() -> list[tuple[str, Outgoing]]:
    """Orders and the routing key each is sent with: a fifth unpaid."""
    found = []
    for index in range(ORDER_COUNT):
        product, price = PRODUCTS[index * 3 % len(PRODUCTS)]
        quantity = 1 + index % 4
        paid = index % 5 != 0
        found.append(
            (
                "orders.paid" if paid else "orders.new",
                _json(
                    {
                        "order_id": 10_000 + index,
                        "customer": CUSTOMERS[index * 7 % len(CUSTOMERS)],
                        "product": product,
                        "quantity": quantity,
                        "total": round(price * quantity, 2),
                        "paid": paid,
                    },
                    DAY + timedelta(minutes=index * 23),
                    source="shop",
                ),
            )
        )
    return found


def alerts() -> list[Outgoing]:
    levels = ("info", "warning", "critical")
    return [
        Outgoing(
            body=f"disk {80 + index}% full on node-{index % 3}".encode(),
            timestamp=DAY + timedelta(hours=index),
            content_type="text/plain",
            headers={"level": levels[index % 3], "node": f"node-{index % 3}"},
            properties={},
        )
        for index in range(12)
    ]


def trades() -> list[Outgoing]:
    found = []
    for index in range(TRADE_COUNT):
        symbol, base = SYMBOLS[index % len(SYMBOLS)]
        found.append(
            _json(
                {
                    "trade_id": 500_000 + index,
                    "symbol": symbol,
                    "price": round(base * (1 + ((index * 37) % 200 - 100) / 10_000), 2),
                    "qty": round(0.01 * (1 + index % 9), 3),
                    "side": "buy" if index % 2 else "sell",
                },
                DAY + timedelta(seconds=index * 288),
            )
        )
    # A sensor writing raw readings into the same stream: bodies that are bytes.
    for index in range(BYTES_COUNT):
        found.append(
            Outgoing(
                body=struct.pack(">HhI", index, -40 + index * 3, 1_000 + index),
                timestamp=DAY + timedelta(hours=23, minutes=index),
                content_type="application/octet-stream",
                headers={"source": "sensor"},
                properties={},
            )
        )
    return found


async def install(session: RabbitmqSession) -> int:
    # The connection's virtual host; a broker started here names none, so `/`.
    named = session.options.vhost or "/"
    vhost = segment(named)

    async def queue(name: str, arguments: dict[str, object]) -> None:
        await session.change(
            "PUT",
            f"/queues/{vhost}/{segment(name)}",
            {"durable": True, "auto_delete": False, "arguments": arguments},
        )

    async def exchange(name: str, kind: str) -> None:
        await session.change(
            "PUT",
            f"/exchanges/{vhost}/{segment(name)}",
            {"type": kind, "durable": True, "auto_delete": False, "internal": False},
        )

    async def bind(
        source: str, destination: str, key: str, arguments: dict[str, object]
    ) -> None:
        await session.change(
            "POST",
            f"/bindings/{vhost}/e/{segment(source)}/q/{segment(destination)}",
            {"routing_key": key, "arguments": arguments},
        )

    await exchange(ORDERS, "topic")
    await exchange(DEAD_LETTER, "fanout")
    await exchange(ALERTS, "headers")
    await queue(
        BILLING, {"x-queue-type": "classic", "x-dead-letter-exchange": DEAD_LETTER}
    )
    await queue(SHIPPING, {"x-queue-type": "quorum"})
    await queue(DEAD, {"x-queue-type": "classic"})
    await queue(CRITICAL, {"x-queue-type": "classic"})
    await queue(TRADES, {"x-queue-type": "stream", "x-max-age": "30D"})
    await bind(ORDERS, BILLING, "orders.#", {})
    await bind(ORDERS, SHIPPING, "orders.paid", {})
    await bind(DEAD_LETTER, DEAD, "", {})
    await bind(ALERTS, CRITICAL, "", {"x-match": "all", "level": "critical"})

    sent = 0
    async with session.channel(vhost=named) as channel:
        for key, message in orders():
            await publish(channel, ORDERS, key, [message])
            sent += 1
        # Alerts that match no binding are dropped by the exchange, as they
        # would be in a real one; the lab counts what it sent.
        for message in alerts():
            await publish(channel, ALERTS, "", [message])
            sent += 1
        made = trades()
        await publish(channel, "", TRADES, made)
        sent += len(made)
    return sent


class RabbitmqSamples:
    """Filling a RabbitMQ this server just started, never one somebody else
    runs (D80)."""

    def __init__(self, session: RabbitmqSession) -> None:
        self._session = session

    async def install_sample_data(self) -> str:
        count = await install(self._session)
        return say(
            "{count} messages in the lab's exchanges, queues and the stream {stream}",
            count=count,
            stream=TRADES,
        )
