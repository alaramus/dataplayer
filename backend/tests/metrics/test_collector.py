"""From a DPMA/1 datagram to rows in the store (D127, D130)."""

import asyncio
import time
import uuid
from collections.abc import Sequence

from sqlalchemy import text

from app.metrics.collector import Collector, Counts, Receiver
from app.metrics.store import MetricsStore
from tests.metrics.datagrams import host, key_id, metrics, process, processes, signed

AGENT = uuid.uuid4()
KEY = "known-key"
# The store reads the newest process table of the last hour by its own clock.
NOW = int(time.time())


async def _agents_for(kid: str) -> Sequence[tuple[uuid.UUID, str]]:
    return [(AGENT, KEY)] if kid == key_id(KEY) else []


def _collector(store: MetricsStore, counts: Counts | None = None) -> Collector:
    return Collector(store, _agents_for, counts or Counts(), clock=lambda: NOW)


async def _count(store: MetricsStore, table: str) -> int:
    queries = {
        "metric_point": "SELECT count(*) FROM metric_point",
        "metric_series": "SELECT count(*) FROM metric_series",
        "metric_process": "SELECT count(*) FROM metric_process",
        "metric_host": "SELECT count(*) FROM metric_host",
    }
    async with store._engine.connect() as connection:
        return int((await connection.execute(text(queries[table]))).scalar_one())


async def test_samples_are_written_as_they_were_sent(store: MetricsStore) -> None:
    counts = Counts()
    collector = _collector(store, counts)
    samples: list[list[object]] = [
        ["cpu", "utilization", "total", "%", 12.5],
        ["cpu", "utilization", "cpu0", "%", 10],
        ["net", "receive", "eth0", "B/s", 1834.2],
    ]

    await collector.handle(signed(KEY, metrics(samples, time=NOW - 15, seq=1)))
    await collector.handle(signed(KEY, metrics(samples, time=NOW, seq=2)))
    await collector.flush()

    assert counts.points == 6
    catalog = {(s.metric, s.field, s.label): s for s in await store.catalog([AGENT])}
    assert set(catalog) == {("cpu", "utilization", "total"), ("cpu", "utilization", "cpu0"), ("net", "receive", "eth0")}
    receive = catalog[("net", "receive", "eth0")]
    assert (receive.host, receive.unit) == ("web-01", "B/s")
    points = await store.raw_points([receive.id], NOW - 60, NOW)
    assert points[receive.id] == [[float(NOW - 15), 1834.2], [float(NOW), 1834.2]]


async def test_a_datagram_that_does_not_pass_every_check_writes_nothing(store: MetricsStore) -> None:
    counts = Counts()
    collector = _collector(store, counts)
    sample: list[list[object]] = [["cpu", "utilization", "total", "%", 1]]

    await collector.handle(b'{"action": "monitor-cpu", "appkey": "known-key", "host": "h"}')
    await collector.handle(signed("guessed-key", metrics(sample, time=NOW)))
    await collector.handle(signed("guessed-key", metrics(sample, time=NOW), kid=key_id(KEY)))
    await collector.handle(signed(KEY, metrics([["cpu", "utilization", "total", "kB", 1]], time=NOW)))
    await collector.handle(signed(KEY, metrics(sample, time=NOW - 3600)))
    await collector.handle(signed(KEY, metrics(sample, time=NOW + 3600)))
    await collector.flush()

    assert (counts.malformed, counts.unknown_key, counts.bad_signature, counts.refused_body) == (1, 1, 1, 1)
    assert (counts.stale, counts.future) == (1, 1)
    assert await _count(store, "metric_series") == 0
    assert await _count(store, "metric_host") == 0


async def test_a_datagram_sent_again_is_written_once(store: MetricsStore) -> None:
    counts = Counts()
    collector = _collector(store, counts)
    raw = signed(KEY, metrics([["host", "uptime", "", "s", 5000]], time=NOW, seq=7))

    await collector.handle(raw)
    await collector.handle(raw)
    await collector.flush()

    assert counts.replayed == 1
    assert await _count(store, "metric_point") == 1


async def test_a_process_table_in_parts_is_one_table(store: MetricsStore) -> None:
    counts = Counts()
    collector = _collector(store, counts)

    await collector.handle(signed(KEY, processes([process(1, cpu=9), process(2)], part=(1, 2), total=212, time=NOW, seq=1)))
    await collector.handle(signed(KEY, processes([process(3, cpu=5)], part=(2, 2), total=212, time=NOW, seq=2)))

    assert counts.process_parts == 2
    assert await _count(store, "metric_series") == 0
    latest = await store.latest_processes(AGENT, "web-01", "pcpu", 10)
    assert latest is not None
    assert (latest.ts, latest.total) == (NOW, 212)
    assert [row.pid for row in latest.rows] == [1, 3, 2]
    async with store._engine.connect() as connection:
        rows = (await connection.execute(text("SELECT pid, total, state, rss, name FROM metric_process ORDER BY pid"))).all()
    assert [tuple(row) for row in rows] == [
        (1, 212, "S", 1_048_576, "worker"),
        (2, 212, "S", 2_097_152, "worker"),
        (3, 212, "S", 3_145_728, "worker"),
    ]


async def test_what_the_host_is_is_kept_with_its_agent_process(store: MetricsStore) -> None:
    counts = Counts()
    collector = _collector(store, counts)

    await collector.handle(signed(KEY, metrics([["host", "uptime", "", "s", 5]], time=NOW, seq=1)))
    (described,) = await store.hosts([AGENT])
    assert described.info is None
    assert described.run.version == "0.1.1"

    await collector.handle(signed(KEY, host(time=NOW, seq=2)))
    await collector.flush()

    (described,) = await store.hosts([AGENT])
    assert counts.hosts == 1
    assert described.info is not None
    assert (described.info.os, described.info.cpus, dict(described.info.collectors)) == (
        "Ubuntu 24.04.1 LTS", 8, {"cpu": 15, "processes": 60},
    )
    assert described.last_seen is not None


async def test_a_new_agent_process_is_written_down_as_a_restart(store: MetricsStore) -> None:
    counts = Counts()
    collector = _collector(store, counts)
    sample: list[list[object]] = [["host", "uptime", "", "s", 5]]

    await collector.handle(signed(KEY, metrics(sample, time=NOW - 60, seq=1, instance="first", started=NOW - 90)))
    await collector.handle(signed(KEY, metrics(sample, time=NOW, seq=1, instance="second", started=NOW - 20)))
    # The first process, a moment late, is not the host restarting again.
    await collector.handle(signed(KEY, metrics(sample, time=NOW - 45, seq=2, instance="first", started=NOW - 90)))

    assert counts.restarts == 1
    (restart,) = await store.restarts_since([AGENT], NOW - 3600)
    assert (restart.host, restart.ts, restart.cause) == ("web-01", NOW - 20, "agent")
    (described,) = await store.hosts([AGENT])
    assert described.run.instance == "second"


async def test_a_collector_started_again_knows_the_process_it_saw_before(store: MetricsStore) -> None:
    sample: list[list[object]] = [["host", "uptime", "", "s", 5]]
    first = _collector(store)
    await first.handle(signed(KEY, metrics(sample, time=NOW - 30, seq=1)))

    counts = Counts()
    again = _collector(store, counts)
    await again.load()
    await again.handle(signed(KEY, metrics(sample, time=NOW, seq=2)))

    assert counts.restarts == 0


async def test_series_forgotten_by_the_collector_are_found_again(store: MetricsStore) -> None:
    collector = _collector(store)
    await collector.handle(signed(KEY, metrics([["host", "uptime", "", "s", 1]], time=NOW - 30, seq=1)))
    collector.forget_series()
    await collector.handle(signed(KEY, metrics([["host", "uptime", "", "s", 31]], time=NOW, seq=2)))
    await collector.flush()

    assert await _count(store, "metric_series") == 1
    assert await _count(store, "metric_point") == 2


async def test_a_full_queue_drops_and_counts_rather_than_waits() -> None:
    counts = Counts()
    queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1)
    receiver = Receiver(queue, counts)

    receiver.datagram_received(b"one", ("127.0.0.1", 1))
    receiver.datagram_received(b"two", ("127.0.0.1", 1))

    assert counts.received == 2
    assert counts.queue_full == 1
    assert queue.get_nowait() == b"one"
