"""Topics and consumer groups as a catalog (D305).

Node ids: the three levels by name, `topic:<name>` and `group:<id>`. A topic's
name is Kafka's own set of characters, so the prefix cannot be part of one.
"""

import re
from typing import Any

from confluent_kafka import ConsumerGroupState as KafkaGroupState
from confluent_kafka import TopicPartition
from confluent_kafka.admin import OffsetSpec

from app.adapters.catalog import (
    CatalogNode,
    ConsumerGroupNode,
    ConsumerGroupState,
    DirectoryNode,
    TopicNode,
)
from app.adapters.content import NodeRepresentation
from app.adapters.kafka.session import TIMEOUT_SECONDS, KafkaClients
from app.adapters.protocol import NodeNotFound
from app.adapters.words import worded_titles
from app.core.translation import N_, say

TOPICS = "topics"
GROUPS = "groups"
INTERNAL = "internal"

TOPIC_PREFIX = "topic:"
GROUP_PREFIX = "group:"

# Past this many, a level lists the first ones by name.
LIST_CEILING = 1000

MESSAGES = NodeRepresentation(kind="table", title=N_("View the messages"))
POSITIONS = NodeRepresentation(kind="table", title=N_("View the positions"))

# Kafka's rule for a topic's name.
_TOPIC_NAME = re.compile(r"[A-Za-z0-9._-]{1,249}")


def is_internal(topic: str) -> bool:
    """Kafka's own topics and its tools': `__consumer_offsets`, `_schemas`."""
    return topic.startswith("_")


def topic_of(node_id: str) -> str:
    """The topic a node id names, or a refusal when it names none."""
    if not node_id.startswith(TOPIC_PREFIX):
        raise ValueError(say("Not a topic of this connection"))
    name = node_id[len(TOPIC_PREFIX) :]
    if _TOPIC_NAME.fullmatch(name) is None:
        raise ValueError(say("Not a topic of this connection"))
    return name


def group_of(node_id: str) -> str:
    if not node_id.startswith(GROUP_PREFIX) or node_id == GROUP_PREFIX:
        raise ValueError(say("Not a consumer group of this connection"))
    return node_id[len(GROUP_PREFIX) :]


def folders() -> list[CatalogNode]:
    return [
        DirectoryNode(
            id=TOPICS, name=say("Topics"), has_children=True, representations=[]
        ),
        DirectoryNode(
            id=GROUPS,
            name=say("Consumer groups"),
            has_children=True,
            representations=[],
        ),
        DirectoryNode(
            id=INTERNAL,
            name=say("Internal topics"),
            has_children=True,
            representations=[],
        ),
    ]


def folder_of(node_id: str) -> CatalogNode:
    for folder in folders():
        if folder.id == node_id:
            return folder
    raise NodeNotFound(node_id)


def partitions_of(
    clients: KafkaClients, topic: str | None = None
) -> dict[str, list[int]]:
    """Every topic's partitions, or one topic's, from the cluster's metadata.

    Always the whole cluster's: asking for one topic by name creates it on a
    broker that creates topics it is asked about, which is Kafka's default.
    """
    metadata = clients.admin().list_topics(timeout=TIMEOUT_SECONDS)
    found: dict[str, list[int]] = {}
    for name, described in metadata.topics.items():
        if described.error is None and (topic is None or name == topic):
            found[name] = sorted(described.partitions)
    if topic is not None and topic not in found:
        raise NodeNotFound(TOPIC_PREFIX + topic)
    return found


def watermarks(
    clients: KafkaClients, topics: dict[str, list[int]]
) -> dict[tuple[str, int], tuple[int, int]]:
    """Each partition's first and end offset, two requests for all of them."""
    partitions = [
        TopicPartition(name, one) for name, ids in topics.items() for one in ids
    ]
    if not partitions:
        return {}
    admin = clients.admin()
    first = admin.list_offsets(
        {tp: OffsetSpec.earliest() for tp in partitions},
        request_timeout=TIMEOUT_SECONDS,
    )
    end = admin.list_offsets(
        {tp: OffsetSpec.latest() for tp in partitions}, request_timeout=TIMEOUT_SECONDS
    )
    found: dict[tuple[str, int], tuple[int, int]] = {}
    for tp in partitions:
        low = _offset(first, tp)
        high = _offset(end, tp)
        if low is not None and high is not None:
            found[(tp.topic, tp.partition)] = (low, high)
    return found


def _offset(futures: dict[Any, Any], wanted: TopicPartition) -> int | None:
    for tp, future in futures.items():
        if tp.topic == wanted.topic and tp.partition == wanted.partition:
            return int(future.result().offset)
    return None


def topic_node(
    name: str, partitions: list[int], marks: dict[tuple[str, int], tuple[int, int]]
) -> TopicNode:
    spans = [marks.get((name, one)) for one in partitions]
    messages = (
        None
        if any(span is None for span in spans)
        else sum(
            high - low for low, high in (span for span in spans if span is not None)
        )
    )
    return TopicNode(
        id=TOPIC_PREFIX + name,
        name=name,
        representations=worded_titles([MESSAGES]),
        summarizable=True,
        partitions=len(partitions),
        messages=messages,
        is_system=is_internal(name),
    )


def read_topics(clients: KafkaClients, internal: bool) -> list[CatalogNode]:
    topics = partitions_of(clients)
    names = sorted(name for name in topics if is_internal(name) == internal)[
        :LIST_CEILING
    ]
    listed = {name: topics[name] for name in names}
    marks = watermarks(clients, listed)
    return [topic_node(name, listed[name], marks) for name in names]


def read_topic(clients: KafkaClients, name: str) -> TopicNode:
    topics = partitions_of(clients, name)
    return topic_node(name, topics[name], watermarks(clients, topics))


def state_of(state: Any) -> ConsumerGroupState:
    if state == KafkaGroupState.STABLE:
        return "stable"
    if state == KafkaGroupState.EMPTY:
        return "empty"
    if state == KafkaGroupState.DEAD:
        return "dead"
    if state in {
        KafkaGroupState.PREPARING_REBALANCING,
        KafkaGroupState.COMPLETING_REBALANCING,
    }:
        return "rebalancing"
    return "unknown"


def group_node(
    group_id: str, state: ConsumerGroupState, members: int | None
) -> ConsumerGroupNode:
    return ConsumerGroupNode(
        id=GROUP_PREFIX + group_id,
        name=group_id,
        representations=worded_titles([POSITIONS]),
        summarizable=True,
        state=state,
        members=members,
    )


def read_groups(clients: KafkaClients) -> list[CatalogNode]:
    admin = clients.admin()
    listed = admin.list_consumer_groups(request_timeout=TIMEOUT_SECONDS).result()
    ids = sorted(listing.group_id for listing in listed.valid)[:LIST_CEILING]
    if not ids:
        return []
    described = admin.describe_consumer_groups(ids, request_timeout=TIMEOUT_SECONDS)
    nodes: list[CatalogNode] = []
    for group_id in ids:
        try:
            description = described[group_id].result()
        except Exception:  # noqa: BLE001 - one group not described is listed by name
            nodes.append(group_node(group_id, "unknown", None))
            continue
        nodes.append(
            group_node(group_id, state_of(description.state), len(description.members))
        )
    return nodes
