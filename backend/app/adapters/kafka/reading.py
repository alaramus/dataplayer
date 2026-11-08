"""A topic read on by a consumer group of its reader's own (D312).

The group never has members: partitions are assigned, as a page reads them
(D306), and the group's positions are read and written by the admin client.
So no rebalance runs, and Kafka's refusal to move the positions of a group
with consumers never stops a reader.
"""

import time

from confluent_kafka import (
    ConsumerGroupTopicPartitions,
    KafkaError,
    KafkaException,
    TopicPartition,
)

from app.adapters.kafka.catalog import (
    TOPIC_PREFIX,
    is_internal,
    partitions_of,
    topic_of,
    watermarks,
)
from app.adapters.kafka.groups import commit_positions
from app.adapters.kafka.messages import (
    FIELD_PREFIX,
    FILTER_CHUNK,
    Message,
    cell,
    message_of,
    moment,
)
from app.adapters.kafka.session import TIMEOUT_SECONDS, KafkaClients, KafkaSession
from app.adapters.reading_on import Bookmark, ReadBlock, ReadStart, UnreadSpan
from app.core.translation import say

# How long one block may take to read, all partitions together.
BLOCK_SECONDS = 30.0

# The columns every message has; `value.<field>` is read from its value.
_FIXED = {"partition", "offset", "timestamp", "key", "value", "headers"}

# A coordinator just started is loading its groups; asked again meanwhile.
_COMMIT_WAIT_SECONDS = 10.0


def _committed(
    clients: KafkaClients, group: str, topic: str, partitions: list[int]
) -> dict[int, int]:
    """The group's position in each partition that has one."""
    answered = (
        clients.admin()
        .list_consumer_group_offsets(
            [
                ConsumerGroupTopicPartitions(
                    group, [TopicPartition(topic, one) for one in partitions]
                )
            ],
            request_timeout=TIMEOUT_SECONDS,
        )[group]
        .result()
        .topic_partitions
        or []
    )
    return {tp.partition: int(tp.offset) for tp in answered if tp.offset >= 0}


def unread(
    clients: KafkaClients, topic: str, group: str, start: ReadStart
) -> UnreadSpan:
    partitions = partitions_of(clients, topic)[topic]
    marks = watermarks(clients, {topic: partitions})
    committed = _committed(clients, group, topic, partitions)
    fresh = not committed
    begins: dict[str, int] = {}
    line: dict[str, int] = {}
    count = lost = 0
    for partition in partitions:
        low, high = marks.get((topic, partition), (0, 0))
        position = committed.get(partition)
        if position is None:
            # A partition added since the last reading is read from its start.
            begin = high if fresh and start == "latest" else low
        elif position < low:
            # Deleted by retention or by Delete messages before it was read.
            lost += low - position
            begin = low
        elif position > high:
            # The topic was made again under the same name: read it all.
            begin = low
        else:
            begin = position
        begins[str(partition)] = begin
        line[str(partition)] = high
        count += high - begin
    return UnreadSpan(
        start=Bookmark(positions=begins),
        line=Bookmark(positions=line),
        count=count,
        lost=lost,
        fresh=fresh,
    )


def _value(message: Message, column: str) -> str | None:
    if column == "partition":
        return str(message.partition)
    if column == "offset":
        return str(message.offset)
    if column == "timestamp":
        return moment(message.timestamp)
    return cell(message, column)


def _row(message: Message, columns: list[str]) -> list[str | None]:
    return [_value(message, column) for column in columns]


def read_on(
    clients: KafkaClients,
    topic: str,
    columns: list[str],
    at: Bookmark,
    line: Bookmark,
    limit: int,
) -> ReadBlock:
    unknown = [
        one for one in columns if one not in _FIXED and not one.startswith(FIELD_PREFIX)
    ]
    if unknown:
        raise ValueError(say("Unknown column: {column}", column=unknown[0]))
    after = dict(at.positions)
    # Each partition's share of the block, the first partitions first.
    wanted: dict[int, tuple[int, int]] = {}
    room = limit
    for key, end in sorted(line.positions.items(), key=lambda one: int(one[0])):
        begin = after.get(key, end)
        if begin >= end or room <= 0:
            continue
        stop = min(end, begin + room)
        wanted[int(key)] = (begin, stop)
        room -= stop - begin
    rows: list[list[str | None]] = []
    if wanted:
        consumer = clients.consumer()
        consumer.assign(
            [
                TopicPartition(topic, partition, begin)
                for partition, (begin, _) in wanted.items()
            ]
        )
        pending = set(wanted)
        deadline = time.monotonic() + BLOCK_SECONDS
        try:
            while pending and time.monotonic() < deadline:
                for raw in consumer.consume(num_messages=FILTER_CHUNK, timeout=0.1):
                    partition = raw.partition()
                    if partition not in pending:
                        continue
                    stop = wanted[partition][1]
                    error = raw.error()
                    if error is not None:
                        if error.code() != KafkaError._PARTITION_EOF:
                            raise KafkaException(error)
                        # At the end: what lies before the stop is markers
                        # and gaps, not messages.
                        after[str(partition)] = stop
                    else:
                        offset = raw.offset()
                        if offset is None:
                            continue
                        if offset < stop:
                            rows.append(_row(message_of(raw), columns))
                        after[str(partition)] = min(offset + 1, stop)
                    if after[str(partition)] >= stop:
                        pending.discard(partition)
                        # Not paused: a paused partition stays paused when
                        # assigned again (D306).
                        consumer.incremental_unassign(
                            [TopicPartition(topic, partition)]
                        )
        finally:
            consumer.unassign()
        if pending and not rows:
            raise ValueError(
                say(
                    "Kafka sent nothing in {seconds} seconds",
                    seconds=int(BLOCK_SECONDS),
                )
            )
    done = all(after.get(key, end) >= end for key, end in line.positions.items())
    return ReadBlock(rows=rows, after=Bookmark(positions=after), done=done)


def mark_read(clients: KafkaClients, topic: str, group: str, at: Bookmark) -> None:
    commit_positions(
        clients,
        group,
        [
            TopicPartition(topic, int(key), offset)
            for key, offset in sorted(at.positions.items())
        ],
        wait_seconds=_COMMIT_WAIT_SECONDS,
    )


class KafkaReading:
    def __init__(self, session: KafkaSession) -> None:
        self._session = session

    def reads_on(self, node_id: str) -> bool:
        if not node_id.startswith(TOPIC_PREFIX):
            return False
        try:
            return not is_internal(topic_of(node_id))
        except ValueError:
            return False

    def _topic(self, node_id: str) -> str:
        topic = topic_of(node_id)
        if is_internal(topic):
            raise ValueError(say("Kafka's own topics are not read on from here"))
        return topic

    async def unread(self, node_id: str, reader: str, start: ReadStart) -> UnreadSpan:
        topic = self._topic(node_id)
        return await self._session.run(
            lambda clients: unread(clients, topic, reader, start), node_id
        )

    async def read_on(
        self, node_id: str, columns: list[str], at: Bookmark, line: Bookmark, limit: int
    ) -> ReadBlock:
        topic = self._topic(node_id)
        return await self._session.run(
            lambda clients: read_on(clients, topic, columns, at, line, limit), node_id
        )

    async def mark_read(self, node_id: str, reader: str, at: Bookmark) -> None:
        topic = self._topic(node_id)
        await self._session.run(
            lambda clients: mark_read(clients, topic, reader, at), node_id
        )
