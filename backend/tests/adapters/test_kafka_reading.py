"""A topic read on by a consumer group of its reader's own (D312)."""

import json
import uuid
from collections.abc import AsyncIterator

import pytest
from confluent_kafka import Producer, TopicPartition
from confluent_kafka.admin import NewPartitions

from app.adapters.reading_on import Bookmark
from tests.adapters.kafka_fixture import (
    ORDERS,
    PARTITIONS,
    adapter,
    admin,
    bootstrap,
    make,
    names,
    on_server,
    remove,
)

# Every message the fixture sends: the orders and one that is not JSON.
SENT = ORDERS + 1
COLUMNS = ["partition", "offset", "value.id", "key"]


@pytest.fixture
async def topic() -> AsyncIterator[str]:
    """A topic of its own per test: each moves a group and adds messages."""
    name, group = names()
    await on_server(lambda: make(name, group))
    yield name
    await on_server(lambda: remove(name, group))


@pytest.fixture
def reader() -> str:
    return f"dp-test-reader-{uuid.uuid4().hex[:12]}"


def _send(topic: str, count: int, partition: int | None = None) -> None:
    producer = Producer({"bootstrap.servers": bootstrap()})
    for index in range(count):
        value = json.dumps({"id": 1000 + index})
        if partition is None:
            producer.produce(topic, value=value, partition=index % PARTITIONS)
        else:
            producer.produce(topic, value=value, partition=partition)
    producer.flush(10)


async def _read_all(
    node: str, at: Bookmark, line: Bookmark, limit: int
) -> tuple[list[list[str | None]], Bookmark, int]:
    """Every row up to the line, a block at a time; how many blocks it took."""
    rows: list[list[str | None]] = []
    blocks = 0
    while True:
        block = await adapter().read_on(node, COLUMNS, at, line, limit)
        blocks += 1
        rows.extend(block.rows)
        at = block.after
        if block.done:
            return rows, at, blocks


async def _forget(reader: str) -> None:
    def drop() -> None:
        # Held while the future resolves: a client dropped first never answers.
        client = admin()
        for future in client.delete_consumer_groups([reader]).values():
            future.result()

    await on_server(drop)


def test_a_topic_is_read_on_and_kafka_s_own_and_a_group_are_not() -> None:
    reading = adapter()
    assert reading.reads_on("topic:orders")
    assert not reading.reads_on("topic:__consumer_offsets")
    assert not reading.reads_on("group:billing")
    assert not reading.reads_on("topics")


async def test_a_reader_with_no_bookmark_reads_everything_then_only_what_is_new(
    topic: str, reader: str
) -> None:
    node = f"topic:{topic}"
    try:
        span = await adapter().unread(node, reader, "earliest")
        assert (span.fresh, span.count, span.lost) == (True, SENT, 0)

        rows, after, blocks = await _read_all(node, span.start, span.line, 25)
        assert len(rows) == SENT
        # Blocks of 25 at most, so more than one.
        assert blocks >= 3
        ids = {row[2] for row in rows if row[2] is not None}
        assert ids == {str(index) for index in range(ORDERS)}
        await adapter().mark_read(node, reader, after)

        again = await adapter().unread(node, reader, "earliest")
        assert (again.fresh, again.count) == (False, 0)

        await on_server(lambda: _send(topic, 4))
        new = await adapter().unread(node, reader, "earliest")
        assert new.count == 4
        rows, _, _ = await _read_all(node, new.start, new.line, 1000)
        assert sorted(row[2] for row in rows) == ["1000", "1001", "1002", "1003"]
    finally:
        await _forget(reader)


async def test_a_block_read_and_not_kept_is_read_again(topic: str, reader: str) -> None:
    node = f"topic:{topic}"
    try:
        span = await adapter().unread(node, reader, "earliest")
        first = await adapter().read_on(node, COLUMNS, span.start, span.line, 10)
        await adapter().mark_read(node, reader, first.after)
        # Read, and the step failed before it was kept.
        await adapter().read_on(node, COLUMNS, first.after, span.line, 10)

        again = await adapter().unread(node, reader, "earliest")
        assert again.start == first.after
        assert again.count == SENT - 10
    finally:
        await _forget(reader)


async def test_only_new_starts_at_the_end(topic: str, reader: str) -> None:
    node = f"topic:{topic}"
    try:
        span = await adapter().unread(node, reader, "latest")
        assert (span.fresh, span.count) == (True, 0)
        assert span.start == span.line
        block = await adapter().read_on(node, COLUMNS, span.start, span.line, 100)
        assert (block.rows, block.done) == ([], True)
        await adapter().mark_read(node, reader, block.after)

        await on_server(lambda: _send(topic, 2))
        # Once kept, the choice changes nothing.
        later = await adapter().unread(node, reader, "earliest")
        assert (later.fresh, later.count) == (False, 2)
    finally:
        await _forget(reader)


async def test_messages_deleted_before_they_were_read_are_counted(
    topic: str, reader: str
) -> None:
    node = f"topic:{topic}"
    try:
        span = await adapter().unread(node, reader, "earliest")
        await adapter().mark_read(node, reader, span.start)

        def delete_five() -> None:
            client = admin()
            for future in client.delete_records([TopicPartition(topic, 0, 5)]).values():
                future.result()

        await on_server(delete_five)
        after = await adapter().unread(node, reader, "earliest")
        assert after.lost == 5
        assert after.start.positions["0"] == 5
        assert after.count == SENT - 5
    finally:
        await _forget(reader)


async def test_a_partition_added_later_is_read_from_its_start(
    topic: str, reader: str
) -> None:
    node = f"topic:{topic}"
    try:
        span = await adapter().unread(node, reader, "latest")
        await adapter().mark_read(node, reader, span.line)

        def grow() -> None:
            client = admin()
            for future in client.create_partitions(
                [NewPartitions(topic, PARTITIONS + 1)]
            ).values():
                future.result()

        await on_server(grow)
        await on_server(lambda: _send(topic, 3, partition=PARTITIONS))
        later = await adapter().unread(node, reader, "latest")
        assert later.fresh is False
        assert later.start.positions[str(PARTITIONS)] == 0
        assert later.count == 3
    finally:
        await _forget(reader)


async def test_an_unknown_column_is_refused(topic: str, reader: str) -> None:
    node = f"topic:{topic}"
    span = await adapter().unread(node, reader, "earliest")
    with pytest.raises(ValueError, match="Unknown column"):
        await adapter().read_on(node, ["price"], span.start, span.line, 10)
