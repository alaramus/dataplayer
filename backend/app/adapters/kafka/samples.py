"""Something worth looking at, put into a Kafka this server started (D311).

An empty broker shows `__consumer_offsets` and nothing else. The lab is topics
the way an application leaves them, each exercising a part of the source: JSON
orders over a day in three partitions, the latest price per symbol in a
compacted topic, text lines with headers, readings that are bytes, and a
consumer group part way through the orders. Written out rather than
generated, so two demonstrations look the same; kept for ever, since its times
are fixed.
"""

import json
import struct
import time
from datetime import UTC, datetime

from confluent_kafka import TopicPartition
from confluent_kafka.admin import NewTopic

from app.adapters.kafka.catalog import partitions_of, watermarks
from app.adapters.kafka.groups import commit_positions
from app.adapters.kafka.session import TIMEOUT_SECONDS, KafkaClients, KafkaSession
from app.adapters.kafka.writes import Outgoing, send
from app.core.translation import say

ORDERS = "lab.orders"
PRICES = "lab.prices"
EVENTS = "lab.events"
SENSOR = "lab.sensor"
GROUP = "lab-billing"
TOPICS = (ORDERS, PRICES, EVENTS, SENSOR)

# The day the lab's orders were placed on.
DAY = int(datetime(2026, 1, 15, tzinfo=UTC).timestamp() * 1000)
CUSTOMERS = ("acme", "globex", "initech", "umbrella", "hooli", "stark")
PRODUCTS = (("keyboard", 49.9), ("monitor", 219.0), ("mouse", 19.5), ("dock", 129.0))
SYMBOLS = (("BTCUSDT", 65000.0), ("ETHUSDT", 3200.0), ("SOLUSDT", 140.0), ("BNBUSDT", 580.0))
# How far through the orders the billing group has read, per partition.
READ_SHARE = 0.6

FOREVER = {"retention.ms": "-1"}


def orders() -> list[Outgoing]:
    found = []
    for index in range(300):
        customer = CUSTOMERS[index * 7 % len(CUSTOMERS)]
        product, price = PRODUCTS[index * 3 % len(PRODUCTS)]
        quantity = 1 + index % 4
        value = {
            "order_id": 10_000 + index,
            "customer": customer,
            "product": product,
            "quantity": quantity,
            "total": round(price * quantity, 2),
            "paid": index % 5 != 0,
        }
        found.append(
            Outgoing(
                partition=index % 3,
                timestamp=DAY + index * 288_000,
                key=customer.encode(),
                value=json.dumps(value).encode(),
                headers=[("source", "shop")],
            )
        )
    return found


def prices() -> list[Outgoing]:
    found = []
    for step in range(25):
        for index, (symbol, base) in enumerate(SYMBOLS):
            moved = base * (1 + ((step * 7 + index * 3) % 11 - 5) / 200)
            found.append(
                Outgoing(
                    partition=None,
                    timestamp=DAY + step * 60_000,
                    key=symbol.encode(),
                    value=json.dumps({"symbol": symbol, "price": round(moved, 2)}).encode(),
                    headers=[],
                )
            )
    return found


def events() -> list[Outgoing]:
    kinds = ("signed in", "opened an invoice", "changed a password", "signed out")
    return [
        Outgoing(
            partition=None,
            timestamp=DAY + index * 600_000,
            key=None,
            value=f"user {index % 17} {kinds[index % len(kinds)]}".encode(),
            headers=[("service", "auth"), ("level", "warn" if index % 9 == 0 else "info")],
        )
        for index in range(120)
    ]


def sensor() -> list[Outgoing]:
    return [
        Outgoing(
            partition=None,
            timestamp=DAY + index * 60_000,
            key=f"probe-{index % 3}".encode(),
            # Temperature and humidity as two big-endian floats.
            value=struct.pack(">ff", 20 + (index % 13) / 2, 40 + (index % 7) * 3),
            headers=[],
        )
        for index in range(50)
    ]


def _drop(clients: KafkaClients) -> None:
    """The lab removed, so it is made again the same; waited for, since a
    topic is deleted after the request returns."""
    admin = clients.admin()
    listed = admin.list_consumer_groups(request_timeout=TIMEOUT_SECONDS).result()
    if GROUP in {listing.group_id for listing in listed.valid}:
        for future in admin.delete_consumer_groups([GROUP]).values():
            future.result()
    there = [topic for topic in TOPICS if topic in partitions_of(clients)]
    if there:
        for future in admin.delete_topics(there, request_timeout=TIMEOUT_SECONDS).values():
            future.result()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and set(TOPICS) & set(partitions_of(clients)):
        time.sleep(0.5)


def install(clients: KafkaClients) -> int:
    _drop(clients)
    admin = clients.admin()
    made = [
        NewTopic(ORDERS, 3, 1, config=FOREVER),
        NewTopic(PRICES, 1, 1, config={**FOREVER, "cleanup.policy": "compact"}),
        NewTopic(EVENTS, 2, 1, config=FOREVER),
        NewTopic(SENSOR, 1, 1, config=FOREVER),
    ]
    for future in admin.create_topics(made, request_timeout=TIMEOUT_SECONDS).values():
        future.result()
    sent = 0
    for topic, messages in (
        (ORDERS, orders()),
        (PRICES, prices()),
        (EVENTS, events()),
        (SENSOR, sensor()),
    ):
        sent += len(send(clients, topic, messages))
    known = partitions_of(clients, ORDERS)
    ends = watermarks(clients, known)
    positions = [
        TopicPartition(ORDERS, partition, int(ends[(ORDERS, partition)][1] * READ_SHARE))
        for partition in known[ORDERS]
    ]
    # A broker just started is still loading the group coordinator.
    commit_positions(clients, GROUP, positions, wait_seconds=60)
    return sent


class KafkaSamples:
    """Filling a Kafka this server just started, never one somebody else runs (D80)."""

    def __init__(self, session: KafkaSession) -> None:
        self._session = session

    async def install_sample_data(self) -> str:
        count = await self._session.run(install)
        return say(
            "{count} messages in {topics} lab topics and the group {group}",
            count=count,
            topics=len(TOPICS),
            group=GROUP,
        )
