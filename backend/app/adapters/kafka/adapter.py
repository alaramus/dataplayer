"""A Kafka cluster as a source: its topics, their messages, and its consumer groups.

`confluent_kafka` is imported by this package and by nothing else, the rule
`psycopg` already follows: a driver upgrade has one place to change (D304).
"""

from collections.abc import AsyncIterator, Mapping
from typing import Any

from app.adapters.actions import Action, ActionSet, ActionType
from app.adapters.catalog import CatalogNode
from app.adapters.export import ExportBatch, ExportRequest
from app.adapters.features import SourceFeatures
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.kafka.actions import KAFKA_ACTION_TYPES, build_actions, offered
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
from app.adapters.kafka.metrics import PRESETS as METRIC_PRESETS
from app.adapters.kafka.metrics import KafkaMetrics
from app.adapters.kafka.options import KafkaOptions, checked_servers
from app.adapters.kafka.reading import KafkaReading
from app.adapters.kafka.reports import (
    REPORTS,
    KafkaReports,
    in_section,
    is_section,
    report_for,
    report_node,
    section_node,
)
from app.adapters.kafka.samples import KafkaSamples
from app.adapters.kafka.search import KafkaSearch
from app.adapters.kafka.session import KafkaSession
from app.adapters.kafka.topics import KafkaTopics
from app.adapters.kafka.writes import KafkaWrites
from app.adapters.metrics import MetricPreset, MetricSample
from app.adapters.protocol import ConnectionCheckResult, NodeNotFound
from app.adapters.reading_on import Bookmark, ReadBlock, ReadStart, UnreadSpan
from app.adapters.registry import AdapterContext, register
from app.adapters.search import (
    LastSearch,
    NameBatch,
    NodeSearchRequest,
    NodeSearchResult,
    SearchBounds,
    SearchedField,
    SourceCost,
)
from app.adapters.summary import NodeSummary
from app.adapters.terminal import ConsoleProgram
from app.adapters.update import (
    InsertRowRequest,
    InsertRowResult,
    InsertRowsRequest,
    InsertRowsResult,
)
from app.core.schemas import get_datetime_utc
from app.core.translation import N_, say


class KafkaAdapter:
    """Facade over a session and the capabilities built on it (D2b)."""

    def __init__(self, options: KafkaOptions) -> None:
        self._session = KafkaSession(options)
        self._messages = KafkaMessages(self._session)
        self._groups = KafkaGroups(self._session)
        self._topics = KafkaTopics(self._session)
        self._writes = KafkaWrites(self._session)
        self._actions = ActionSet(build_actions(self._session))
        self._reports = KafkaReports(self._session)
        self._metrics = KafkaMetrics(self._session)
        self._search = KafkaSearch(self._session)
        self._samples = KafkaSamples(self._session)
        self._reading = KafkaReading(self._session)

    # --- how to reach it, in one line --------------------------------------------

    def connection_string(self) -> str:
        """The brokers, as every Kafka tool takes them; never a password."""
        return self._session.options.bootstrap_servers

    @classmethod
    def options_from_url(cls, url: str) -> dict[str, Any]:
        """`host:port,host:port`, with `kafka://` before it allowed (D311)."""
        text = url.strip()
        if text.lower().startswith("kafka://"):
            text = text[len("kafka://") :]
        if "@" in text:
            raise ValueError(
                say("A Kafka address carries no user; choose a SASL method instead")
            )
        return {"bootstrap_servers": checked_servers(text.rstrip("/"))}

    @classmethod
    def draft_connection_string(cls, options: Mapping[str, Any]) -> str | None:
        servers = options.get("bootstrap_servers")
        if not isinstance(servers, str):
            return None
        try:
            return checked_servers(servers)
        except ValueError:
            return None

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
            # The cluster's own section first, as ZooKeeper puts its own (D310).
            return [section_node(), *folders()]
        if is_section(node_id):
            return [report_node(report) for report in REPORTS]
        if in_section(node_id):
            if report_for(node_id) is None:
                raise NodeNotFound(node_id)
            return []
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
        if is_section(node_id):
            return [section_node()]
        if in_section(node_id):
            report = report_for(node_id)
            if report is None:
                raise NodeNotFound(node_id)
            return [section_node(), report_node(report)]
        if node_id in {TOPICS, GROUPS, INTERNAL}:
            return [folder_of(node_id)]
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
        if in_section(request.node_id):
            return await self._reports.fetch(request)
        if request.node_id.startswith(GROUP_PREFIX):
            return await self._groups.fetch(request)
        return await self._messages.fetch(request)

    def export_rows(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        if in_section(request.node_id):
            return self._reports.export_rows(request)
        if request.node_id.startswith(GROUP_PREFIX):
            return self._groups.export_rows(request)
        return self._messages.export_rows(request)

    # --- the cluster measured, and names found (D310) ---------------------------

    async def install_sample_data(self) -> str:
        """The lab, for a broker started here (D311)."""
        return await self._samples.install_sample_data()

    async def metric_samples(self) -> list[MetricSample]:
        return await self._metrics.metric_samples()

    @classmethod
    def metric_presets(cls) -> tuple[MetricPreset, ...]:
        return METRIC_PRESETS

    async def search_nodes(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        return await self._search.search_nodes(request, bounds)

    def enumerate_names(
        self, limit: int, bounds: SearchBounds
    ) -> AsyncIterator[NameBatch]:
        return self._search.enumerate_names(limit, bounds)

    @classmethod
    def search_cost(cls, field: SearchedField, last: LastSearch | None) -> SourceCost:
        """Names are two requests, whatever the cluster holds; nothing else is searched."""
        del last
        return "cheap" if field == "names" else "costly"

    async def node_summary(self, node_id: str) -> NodeSummary:
        if node_id.startswith(GROUP_PREFIX):
            return await self._groups.node_summary(node_id)
        return await self._topics.node_summary(node_id)

    # --- topics and groups changed (D309) ---------------------------------------

    @classmethod
    def action_types(cls) -> tuple[ActionType, ...]:
        return KAFKA_ACTION_TYPES

    def action(self, name: str) -> Action[Any]:
        return self._actions.get(name)

    async def all_actions(self) -> list[Action[Any]]:
        return list(self._actions)

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        return [self._actions.get(name) for name in offered(node_id)]

    # --- messages sent as rows (D308) ------------------------------------------

    async def insert_row(self, request: InsertRowRequest) -> InsertRowResult:
        return await self._writes.insert_row(request)

    async def insert_rows(self, request: InsertRowsRequest) -> InsertRowsResult:
        return await self._writes.insert_rows(request)

    # --- read on by a pipeline's link (D312) ---------------------------------------

    def reads_on(self, node_id: str) -> bool:
        return self._reading.reads_on(node_id)

    async def unread(self, node_id: str, reader: str, start: ReadStart) -> UnreadSpan:
        return await self._reading.unread(node_id, reader, start)

    async def read_on(
        self, node_id: str, columns: list[str], at: Bookmark, line: Bookmark, limit: int
    ) -> ReadBlock:
        return await self._reading.read_on(node_id, columns, at, line, limit)

    async def mark_read(self, node_id: str, reader: str, at: Bookmark) -> None:
        await self._reading.mark_read(node_id, reader, at)

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
