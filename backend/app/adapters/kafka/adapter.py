"""A Kafka cluster as a source: its topics, their messages, and its consumer groups.

`confluent_kafka` is imported by this package and by nothing else, the rule
`psycopg` already follows: a driver upgrade has one place to change (D304).
"""

from app.adapters.catalog import CatalogNode
from app.adapters.features import SourceFeatures
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.kafka.catalog import (
    GROUP_PREFIX,
    GROUPS,
    INTERNAL,
    TOPICS,
    folder_of,
    folders,
    group_of,
    is_internal,
    read_groups,
    read_topic,
    read_topics,
    topic_of,
)
from app.adapters.kafka.console import console_program
from app.adapters.kafka.groups import KafkaGroups
from app.adapters.kafka.messages import KafkaMessages
from app.adapters.kafka.options import KafkaOptions
from app.adapters.kafka.session import KafkaSession
from app.adapters.kafka.topics import KafkaTopics
from app.adapters.protocol import ConnectionCheckResult, NodeNotFound
from app.adapters.registry import AdapterContext, register
from app.adapters.summary import NodeSummary
from app.adapters.terminal import ConsoleProgram
from app.core.schemas import get_datetime_utc
from app.core.translation import N_


class KafkaAdapter:
    """Facade over a session and the capabilities built on it (D2b)."""

    def __init__(self, options: KafkaOptions) -> None:
        self._session = KafkaSession(options)
        self._messages = KafkaMessages(self._session)
        self._groups = KafkaGroups(self._session)
        self._topics = KafkaTopics(self._session)

    async def check_connection(self) -> ConnectionCheckResult:
        return await self._session.check()

    async def source_features(self) -> SourceFeatures:
        # Kafka's protocol does not say which release a broker runs.
        return SourceFeatures(
            observed_at=get_datetime_utc(), server_version=None, features=[]
        )

    # --- the catalog (D305) ----------------------------------------------------

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        if node_id is None:
            return folders()
        if node_id in {TOPICS, INTERNAL}:
            internal = node_id == INTERNAL
            return await self._session.run(
                lambda clients: read_topics(clients, internal), node_id
            )
        if node_id == GROUPS:
            return await self._session.run(read_groups, node_id)
        # A topic and a group hold nothing; anything else is not of this
        # source, by the catalog's contract a refusal rather than a 404.
        if node_id.startswith(GROUP_PREFIX):
            group_of(node_id)
            return []
        topic_of(node_id)
        return []

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        if node_id.startswith(GROUP_PREFIX):
            group_id = group_of(node_id)
            groups = await self._session.run(read_groups, node_id)
            found = [node for node in groups if node.name == group_id]
            if not found:
                raise NodeNotFound(node_id)
            return [folder_of(GROUPS), found[0]]
        topic = topic_of(node_id)
        node = await self._session.run(
            lambda clients: read_topic(clients, topic), node_id
        )
        return [folder_of(INTERNAL if is_internal(topic) else TOPICS), node]

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if request.node_id.startswith(GROUP_PREFIX):
            return await self._groups.fetch(request)
        return await self._messages.fetch(request)

    async def node_summary(self, node_id: str) -> NodeSummary:
        if node_id.startswith(GROUP_PREFIX):
            return await self._groups.node_summary(node_id)
        return await self._topics.node_summary(node_id)

    async def console_program(self) -> ConsoleProgram:
        """Kafka's tools, set up for this connection, in a container (D307)."""
        return console_program(self._session.options)


@register(
    name="kafka",
    title=N_("Kafka"),
    # A log of messages, read and appended to; neither a database nor a
    # store of values under keys.
    category="stream",
    description=N_(
        "A Kafka cluster. List its topics and consumer groups, read a topic's "
        "messages as rows, newest first, from a time or an offset, with JSON "
        "values laid out in columns, see each partition's brokers and offsets, "
        "see how far each consumer group lags behind, and work with Kafka's "
        "own tools in a terminal."
    ),
    options_schema=KafkaOptions,
    adapter_class=KafkaAdapter,
)
def _build(options: KafkaOptions, context: AdapterContext) -> KafkaAdapter:
    del context
    return KafkaAdapter(options)
