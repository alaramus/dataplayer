"""What a topic is: its partitions, who holds them, and its own settings (D305)."""

from dataclasses import dataclass
from typing import Any

from confluent_kafka import TopicCollection
from confluent_kafka.admin import ConfigResource, ConfigSource, ResourceType

from app.adapters.kafka.catalog import (
    MESSAGES,
    TOPIC_PREFIX,
    partitions_of,
    topic_of,
    watermarks,
)
from app.adapters.kafka.session import TIMEOUT_SECONDS, KafkaClients, KafkaSession
from app.adapters.summary import (
    KafkaPartition,
    KafkaSetting,
    KafkaTopicContents,
    NodeSummary,
)
from app.adapters.words import worded_titles


@dataclass(frozen=True)
class Described:
    partitions: list[KafkaPartition]
    settings: list[KafkaSetting]


def _broker(node: Any) -> int | None:
    return None if node is None else int(node.id)


def describe(clients: KafkaClients, topic: str) -> Described:
    # Asked first so that a topic that is not there is a 404, as a page's is.
    known = partitions_of(clients, topic)
    admin = clients.admin()
    description = admin.describe_topics(
        TopicCollection([topic]), request_timeout=TIMEOUT_SECONDS
    )[topic].result()
    marks = watermarks(clients, known)
    partitions = [
        KafkaPartition(
            partition=info.id,
            leader=_broker(info.leader),
            replicas=[int(node.id) for node in info.replicas],
            in_sync=[int(node.id) for node in info.isr],
            first_offset=marks.get((topic, info.id), (None, None))[0],
            end_offset=marks.get((topic, info.id), (None, None))[1],
        )
        for info in sorted(description.partitions, key=lambda info: info.id)
    ]
    resource = ConfigResource(ResourceType.TOPIC, topic)
    entries = admin.describe_configs([resource], request_timeout=TIMEOUT_SECONDS)
    config = next(iter(entries.values())).result()
    # Set on the topic itself; what it inherits is the broker's, and is the
    # same on every topic. The source arrives as the enum's number.
    settings = [
        KafkaSetting(name=name, value=None if entry.is_sensitive else entry.value)
        for name, entry in sorted(config.items())
        if entry.source == ConfigSource.DYNAMIC_TOPIC_CONFIG.value
    ]
    return Described(partitions, settings)


class KafkaTopics:
    def __init__(self, session: KafkaSession) -> None:
        self._session = session

    async def node_summary(self, node_id: str) -> NodeSummary:
        topic = topic_of(node_id)
        described = await self._session.run(
            lambda clients: describe(clients, topic), node_id
        )
        spans = [(one.first_offset, one.end_offset) for one in described.partitions]
        messages = (
            None
            if any(low is None or high is None for low, high in spans)
            else sum((high or 0) - (low or 0) for low, high in spans)
        )
        return NodeSummary(
            node_id=TOPIC_PREFIX + topic,
            name=topic,
            kind="topic",
            representations=worded_titles([MESSAGES]),
            contents=KafkaTopicContents(
                messages=messages,
                partitions=described.partitions,
                settings=described.settings,
            ),
        )
