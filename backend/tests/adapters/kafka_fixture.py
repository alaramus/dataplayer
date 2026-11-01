"""A topic and a consumer group of known shape on the Kafka the suite talks to.

Made with confluent-kafka directly rather than through the adapter, named
afresh per run, and deleted afterwards.
"""

import json
import uuid
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from confluent_kafka import ConsumerGroupTopicPartitions, Producer, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic
from starlette.concurrency import run_in_threadpool

from app.adapters.kafka.adapter import KafkaAdapter
from app.adapters.kafka.options import KafkaNoAuth, KafkaOptions
from tests.utils.services import KAFKA

PARTITIONS = 3
# JSON orders, one a second from T0, round the partitions in turn.
ORDERS = 60
T0 = 1_700_000_000_000
# The newest message: a key and a value that are not text.
BINARY_KEY = b"\xff\x00"
BINARY_VALUE = b"\x01\x02 not json"
BINARY_AT = T0 + 100_000
# Where the group stands: every order of partition 0 read, none of the others.
GROUP_READ = {0: ORDERS // PARTITIONS}
SASL_USER = "dataplayer"
SASL_PASSWORD = "dataplayer"


def bootstrap() -> str:
    parts = urlsplit(KAFKA.require())
    return f"{parts.hostname or '127.0.0.1'}:{parts.port or 9092}"


def sasl_bootstrap() -> str:
    """The SASL listener, the next port of the same broker."""
    parts = urlsplit(KAFKA.require())
    return f"{parts.hostname or '127.0.0.1'}:{(parts.port or 9092) + 1}"


def admin() -> AdminClient:
    return AdminClient({"bootstrap.servers": bootstrap()})


def order(index: int) -> dict[str, Any]:
    return {"id": index, "price": index * 1.5, "side": "buy" if index % 2 else "sell"}


def make(topic: str, group: str) -> None:
    client = admin()
    for future in client.create_topics(
        # Kept for ever: the times are from 2023, and a retention would let
        # the broker delete them at its next check, in the middle of a run.
        [NewTopic(topic, PARTITIONS, 1, config={"retention.ms": "-1"})]
    ).values():
        future.result()
    producer = Producer({"bootstrap.servers": bootstrap()})
    for index in range(ORDERS):
        producer.produce(
            topic,
            key=f"k{index % 7}",
            value=json.dumps(order(index)),
            partition=index % PARTITIONS,
            headers=[("source", b"fixture")],
            timestamp=T0 + index * 1000,
        )
    producer.produce(
        topic, key=BINARY_KEY, value=BINARY_VALUE, partition=0, timestamp=BINARY_AT
    )
    producer.flush(10)
    # A group with positions and no members, as one is between runs of its
    # consumers; committing through a consumer would wait for a rebalance.
    positions = [
        TopicPartition(topic, partition, offset)
        for partition, offset in GROUP_READ.items()
    ]
    for future in client.alter_consumer_group_offsets(
        [ConsumerGroupTopicPartitions(group, positions)]
    ).values():
        future.result()


def remove(topic: str, group: str) -> None:
    client = admin()
    for future in client.delete_consumer_groups([group]).values():
        future.result()
    for future in client.delete_topics([topic]).values():
        future.result()


async def on_server[T](work: Callable[[], T]) -> T:
    return await run_in_threadpool(work)


def names() -> tuple[str, str]:
    run = uuid.uuid4().hex[:12]
    return f"dp_test.{run}", f"dp-test-{run}"


def options() -> KafkaOptions:
    return KafkaNoAuth(bootstrap_servers=bootstrap())


def adapter(given: KafkaOptions | None = None) -> KafkaAdapter:
    return KafkaAdapter(given or options())


def topics() -> set[str]:
    return set(admin().list_topics(timeout=5).topics)


def groups() -> set[str]:
    listed = admin().list_consumer_groups().result()
    return {listing.group_id for listing in listed.valid}
