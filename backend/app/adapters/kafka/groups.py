"""Where a consumer group stands, a row per partition it reads (D305).

A row per partition the group has a position in or a member holds: its topic,
the position committed, the end of the partition, the lag between them, and
the member reading it. In topic and partition order; a group's partitions are
counted in hundreds, so the page is cut here rather than asked for.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from confluent_kafka import ConsumerGroupState as KafkaGroupState
from confluent_kafka import ConsumerGroupTopicPartitions, TopicPartition
from confluent_kafka.admin import OffsetSpec

from app.adapters.export import EXPORT_BATCH_SIZE, ExportBatch, ExportRequest
from app.adapters.fetch import FetchColumn, FetchRequest, FetchResult
from app.adapters.kafka.catalog import GROUP_PREFIX, POSITIONS, group_of, state_of
from app.adapters.kafka.session import TIMEOUT_SECONDS, KafkaClients, KafkaSession
from app.adapters.protocol import NodeNotFound
from app.adapters.relation import ColumnType, TypeCategory
from app.adapters.summary import KafkaGroupContents, NodeSummary
from app.adapters.words import worded_titles
from app.core.translation import say

_SHAPE: tuple[tuple[str, str, TypeCategory], ...] = (
    ("topic", "topic", "string"),
    ("partition", "partition", "number"),
    ("committed", "offset", "number"),
    ("end", "offset", "number"),
    ("lag", "count", "number"),
    ("member", "member", "string"),
    ("client", "client", "string"),
    ("host", "host", "string"),
)

COLUMNS = [
    FetchColumn(name=name, type=ColumnType(sql=sql, category=category))
    for name, sql, category in _SHAPE
]


@dataclass(frozen=True)
class Position:
    topic: str
    partition: int
    committed: int | None
    end: int | None
    member: str | None
    client: str | None
    host: str | None

    @property
    def lag(self) -> int | None:
        if self.committed is None or self.end is None:
            return None
        return max(self.end - self.committed, 0)

    def row(self) -> list[str | None]:
        return [
            self.topic,
            str(self.partition),
            _text(self.committed),
            _text(self.end),
            _text(self.lag),
            self.member,
            self.client,
            self.host,
        ]


def _text(number: int | None) -> str | None:
    return None if number is None else str(number)


@dataclass(frozen=True)
class Standing:
    description: Any
    positions: list[Position]


def read_standing(clients: KafkaClients, group_id: str) -> Standing:
    admin = clients.admin()
    description = admin.describe_consumer_groups(
        [group_id], request_timeout=TIMEOUT_SECONDS
    )[group_id].result()
    committed_partitions = (
        admin.list_consumer_group_offsets(
            [ConsumerGroupTopicPartitions(group_id)], request_timeout=TIMEOUT_SECONDS
        )[group_id]
        .result()
        .topic_partitions
        or []
    )
    # A group nobody ever made is described as dead, with nothing in it.
    if (
        description.state == KafkaGroupState.DEAD
        and not description.members
        and not committed_partitions
    ):
        raise NodeNotFound(GROUP_PREFIX + group_id)
    held: dict[tuple[str, int], Any] = {}
    for member in description.members:
        for tp in member.assignment.topic_partitions:
            held[(tp.topic, tp.partition)] = member
    committed: dict[tuple[str, int], int | None] = {
        (tp.topic, tp.partition): (tp.offset if tp.offset >= 0 else None)
        for tp in committed_partitions
    }
    keys = sorted(set(held) | set(committed))
    ends: dict[tuple[str, int], int] = {}
    if keys:
        futures = admin.list_offsets(
            {
                TopicPartition(topic, partition): OffsetSpec.latest()
                for topic, partition in keys
            },
            request_timeout=TIMEOUT_SECONDS,
        )
        for tp, future in futures.items():
            ends[(tp.topic, tp.partition)] = int(future.result().offset)
    positions = []
    for key in keys:
        member = held.get(key)
        positions.append(
            Position(
                topic=key[0],
                partition=key[1],
                committed=committed.get(key),
                end=ends.get(key),
                member=None if member is None else member.member_id,
                client=None if member is None else member.client_id,
                host=None if member is None else member.host,
            )
        )
    return Standing(description, positions)


def summary_of(group_id: str, standing: Standing) -> NodeSummary:
    description = standing.description
    lags = [position.lag for position in standing.positions if position.lag is not None]
    coordinator = getattr(description, "coordinator", None)
    return NodeSummary(
        node_id=GROUP_PREFIX + group_id,
        name=group_id,
        kind="consumer_group",
        representations=worded_titles([POSITIONS]),
        contents=KafkaGroupContents(
            state=state_of(description.state),
            members=len(description.members),
            coordinator=None if coordinator is None else coordinator.id,
            assignor=description.partition_assignor or None,
            topics=sorted({position.topic for position in standing.positions}),
            lag=sum(lags) if lags else None,
        ),
    )


class KafkaGroups:
    def __init__(self, session: KafkaSession) -> None:
        self._session = session

    async def fetch(self, request: FetchRequest) -> FetchResult:
        group_id = group_of(request.node_id)
        standing = await self._session.run(
            lambda clients: read_standing(clients, group_id), request.node_id
        )
        page = standing.positions[request.offset : request.offset + request.limit]
        return FetchResult(
            columns=COLUMNS,
            rows=[position.row() for position in page],
            has_more=len(standing.positions) > request.offset + request.limit,
            page_commands=["download", "chart", "share"],
            # A group's lag is about what is happening now.
            refresh_seconds=10,
        )

    async def export_rows(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        """Every position, in topic and partition order; nothing filters them."""
        if request.filters or request.sort:
            raise ValueError(
                say("A group's positions are exported in topic and partition order")
            )
        names = [column.name for column in COLUMNS]
        unknown = [column for column in request.columns if column not in names]
        if unknown:
            raise ValueError(say("Unknown column: {column}", column=unknown[0]))
        picked = [names.index(column) for column in request.columns]
        group_id = group_of(request.node_id)
        standing = await self._session.run(
            lambda clients: read_standing(clients, group_id), request.node_id
        )
        rows = [position.row() for position in standing.positions]
        for start in range(0, len(rows), EXPORT_BATCH_SIZE):
            yield ExportBatch(
                rows=[
                    [row[index] for index in picked]
                    for row in rows[start : start + EXPORT_BATCH_SIZE]
                ]
            )

    async def node_summary(self, node_id: str) -> NodeSummary:
        group_id = group_of(node_id)
        standing = await self._session.run(
            lambda clients: read_standing(clients, group_id), node_id
        )
        return summary_of(group_id, standing)
