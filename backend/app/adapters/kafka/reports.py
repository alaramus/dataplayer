"""What the cluster says about itself, as setting-and-value rows (D310).

A Cluster section at the top, beside the three levels, as ZooKeeper's Server
section is (D301). Each report is the admin client's answer read into rows, so
the grid, its download and chart need nothing new.
"""

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

from confluent_kafka.admin import ConfigResource, ConfigSource, ResourceType

from app.adapters.catalog import ReportNode
from app.adapters.content import NodeRepresentation
from app.adapters.export import EXPORT_BATCH_SIZE, ExportBatch, ExportRequest
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.kafka.session import TIMEOUT_SECONDS, KafkaClients, KafkaSession
from app.adapters.protocol import NodeNotFound
from app.adapters.report_rows import export as export_report_rows
from app.adapters.report_rows import page as report_page
from app.core.translation import N_, say

SECTION_ID = "cluster"
REPORT_PREFIX = "report:"
SECTION_TITLE = N_("Cluster")
SECTION_DESCRIPTION = N_("What this Kafka cluster says about itself")
SETTING_COLUMN = N_("Setting")
VALUE_COLUMN = N_("Value")

_TABLE = NodeRepresentation(kind="table", title=N_("View as table"))

type Rows = list[tuple[str, str]]


@dataclass(frozen=True)
class Health:
    """The cluster's shape, read from its metadata once."""

    cluster_id: str
    controller: int | None
    brokers: list[tuple[int, str, int, str | None]]
    topics: int
    partitions: int
    # (topic, partition, leader, replicas, in-sync)
    weak: list[tuple[str, int, int, list[int], list[int]]]

    @property
    def short(self) -> int:
        return sum(1 for one in self.weak if len(one[4]) < len(one[3]))

    @property
    def offline(self) -> int:
        return sum(1 for one in self.weak if one[2] < 0)


def health(clients: KafkaClients) -> Health:
    admin = clients.admin()
    cluster = admin.describe_cluster(request_timeout=TIMEOUT_SECONDS).result()
    metadata = admin.list_topics(timeout=TIMEOUT_SECONDS)
    partitions = 0
    weak: list[tuple[str, int, int, list[int], list[int]]] = []
    for name, described in sorted(metadata.topics.items()):
        if described.error is not None:
            continue
        for one in described.partitions.values():
            partitions += 1
            if one.leader < 0 or len(one.isrs) < len(one.replicas):
                weak.append(
                    (name, one.id, one.leader, list(one.replicas), list(one.isrs))
                )
    return Health(
        cluster_id=cluster.cluster_id or "",
        controller=None if cluster.controller is None else int(cluster.controller.id),
        brokers=sorted(
            (int(node.id), node.host, int(node.port), node.rack)
            for node in cluster.nodes
        ),
        topics=len(metadata.topics),
        partitions=partitions,
        weak=weak,
    )


def _cluster(clients: KafkaClients) -> Rows:
    seen = health(clients)
    return [
        (say("Cluster id"), seen.cluster_id),
        (say("Controller"), "—" if seen.controller is None else str(seen.controller)),
        (say("Brokers"), str(len(seen.brokers))),
        (say("Topics"), str(seen.topics)),
        (say("Partitions"), str(seen.partitions)),
        (say("Partitions short of replicas"), str(seen.short)),
        (say("Partitions without a leader"), str(seen.offline)),
    ]


def _brokers(clients: KafkaClients) -> Rows:
    seen = health(clients)
    rows: Rows = []
    for broker, host, port, rack in seen.brokers:
        parts = [f"{host}:{port}"]
        if rack:
            parts.append(say("rack {rack}", rack=rack))
        if broker == seen.controller:
            parts.append(say("controller"))
        rows.append((say("Broker {n}", n=broker), ", ".join(parts)))
    return rows


def _settings(clients: KafkaClients) -> Rows:
    seen = health(clients)
    broker = seen.controller if seen.controller is not None else seen.brokers[0][0]
    resource = ConfigResource(ResourceType.BROKER, str(broker))
    entries = clients.admin().describe_configs(
        [resource], request_timeout=TIMEOUT_SECONDS
    )
    config = next(iter(entries.values())).result()
    return [
        (
            name,
            say("hidden by the broker") if entry.is_sensitive else (entry.value or ""),
        )
        for name, entry in sorted(config.items())
        if entry.source != ConfigSource.DEFAULT_CONFIG.value
    ]


def _attention(clients: KafkaClients) -> Rows:
    rows: Rows = []
    for topic, partition, leader, replicas, in_sync in health(clients).weak:
        rows.append(
            (
                f"{topic} {partition}",
                say(
                    "leader {leader}, replicas {replicas}, in sync {in_sync}",
                    leader="—" if leader < 0 else leader,
                    replicas=", ".join(map(str, replicas)) or "—",
                    in_sync=", ".join(map(str, in_sync)) or "—",
                ),
            )
        )
    return rows


@dataclass(frozen=True)
class ClusterReport:
    key: str
    title: str
    description: str
    read: Callable[[KafkaClients], Rows]
    refresh_seconds: int | None = None

    @property
    def node_id(self) -> str:
        return REPORT_PREFIX + self.key


REPORTS: tuple[ClusterReport, ...] = (
    ClusterReport(
        "cluster",
        N_("Cluster"),
        N_("Its id, the controller, and how many brokers, topics and partitions"),
        _cluster,
        refresh_seconds=10,
    ),
    ClusterReport(
        "brokers",
        N_("Brokers"),
        N_("Every broker, its address and rack, the controller marked"),
        _brokers,
    ),
    ClusterReport(
        "broker-settings",
        N_("Broker settings"),
        N_("The controller's settings that differ from Kafka's defaults"),
        _settings,
    ),
    ClusterReport(
        "attention",
        N_("Partitions needing attention"),
        N_(
            "Partitions short of in-sync replicas or without a leader; empty when all is well"
        ),
        _attention,
        refresh_seconds=10,
    ),
)

_BY_ID = {report.node_id: report for report in REPORTS}


def is_section(node_id: str | None) -> bool:
    return node_id == SECTION_ID


def in_section(node_id: str | None) -> bool:
    return (node_id or "").startswith(REPORT_PREFIX)


def report_for(node_id: str | None) -> ClusterReport | None:
    return _BY_ID.get(node_id or "")


def section_node() -> ReportNode:
    return ReportNode(
        id=SECTION_ID,
        name=say(SECTION_TITLE),
        description=say(SECTION_DESCRIPTION),
        has_children=True,
        representations=[],
    )


def report_node(report: ClusterReport) -> ReportNode:
    return ReportNode(
        id=report.node_id,
        name=say(report.title),
        description=say(report.description),
        has_children=False,
        representations=[_TABLE.model_copy(update={"title": say(_TABLE.title)})],
    )


class KafkaReports:
    def __init__(self, session: KafkaSession) -> None:
        self._session = session

    def _report(self, node_id: str) -> ClusterReport:
        report = report_for(node_id)
        if report is None:
            raise NodeNotFound(node_id)
        return report

    async def fetch(self, request: FetchRequest) -> FetchResult:
        report = self._report(request.node_id)
        rows = await self._session.run(report.read, request.node_id)
        return report_page(
            request,
            rows,
            name_column=say(SETTING_COLUMN),
            value_column=say(VALUE_COLUMN),
            read_only_reason=say(
                '"{title}" is a report and holds no rows of its own',
                title=say(report.title),
            ),
            refresh_seconds=report.refresh_seconds,
            page_commands=["download", "chart", "share"],
        )

    async def export_rows(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        report = self._report(request.node_id)
        rows = await self._session.run(report.read, request.node_id)
        selected = export_report_rows(
            request,
            rows,
            name_column=say(SETTING_COLUMN),
            value_column=say(VALUE_COLUMN),
        )
        for start in range(0, len(selected), EXPORT_BATCH_SIZE):
            yield ExportBatch(rows=selected[start : start + EXPORT_BATCH_SIZE])
