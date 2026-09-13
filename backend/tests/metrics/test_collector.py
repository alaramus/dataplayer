"""From a datagram to rows in the store (D127, D130)."""

import asyncio
import json
import uuid

from sqlalchemy import text

from app.metrics.collector import Collector, Counts, Receiver
from app.metrics.store import MetricsStore

AGENT = uuid.uuid4()
KEY = "known-key"


async def _agent_for(key: str) -> uuid.UUID | None:
    return AGENT if key == KEY else None


def _packet(metric: str, data: object, *, ts: int, key: str = KEY) -> bytes:
    return json.dumps(
        {"action": f"monitor-{metric}", "appkey": key, "host": "dev-agent", "time": str(ts), "data": data}
    ).encode()


async def _count(store: MetricsStore, table: str) -> int:
    queries = {
        "metric_point": "SELECT count(*) FROM metric_point",
        "metric_series": "SELECT count(*) FROM metric_series",
        "metric_process": "SELECT count(*) FROM metric_process",
    }
    async with store._engine.connect() as connection:
        return int((await connection.execute(text(queries[table]))).scalar_one())


async def test_a_packet_under_a_key_no_agent_holds_writes_nothing(store: MetricsStore) -> None:
    counts = Counts()
    collector = Collector(store, _agent_for, counts)

    await collector.handle(_packet("cpu", {"uptime": 5}, ts=1_789_000_000, key="guessed"))
    await collector.flush()

    assert counts.unknown_key == 1
    assert await _count(store, "metric_series") == 0
    assert await _count(store, "metric_point") == 0


async def test_a_packet_becomes_series_and_points(store: MetricsStore) -> None:
    counts = Counts()
    collector = Collector(store, _agent_for, counts)

    await collector.handle(
        _packet("cpu", {"cpu": [1.0, 0.5, 1.5], "uptime": 10}, ts=1_789_000_000)
    )
    await collector.handle(
        _packet("cpu", {"cpu": [2.0, 1.0, 3.0], "uptime": 40}, ts=1_789_000_030)
    )
    await collector.flush()

    assert counts.points == 8
    assert await _count(store, "metric_series") == 4
    catalog = await store.catalog([AGENT])
    assert {(s.host, s.metric, s.field, s.label) for s in catalog} == {
        ("dev-agent", "cpu", "cpu", "total"),
        ("dev-agent", "cpu", "cpu", "cpu0"),
        ("dev-agent", "cpu", "cpu", "cpu1"),
        ("dev-agent", "cpu", "uptime", ""),
    }


async def test_a_counter_is_stored_as_its_increment(store: MetricsStore) -> None:
    collector = Collector(store, _agent_for, Counts())
    net = [{"name": "eth0:", "read": 100, "transfer": 1000}]
    later = [{"name": "eth0:", "read": 130, "transfer": 1500}]

    await collector.handle(_packet("net", net, ts=1_789_000_000))
    await collector.handle(_packet("net", later, ts=1_789_000_030))
    await collector.flush()

    catalog = {s.field: s for s in await store.catalog([AGENT])}
    assert set(catalog) == {"read_delta", "transfer_delta"}
    points = await store.raw_points(
        [catalog["read_delta"].id], 1_789_000_000, 1_789_000_060
    )
    assert points[catalog["read_delta"].id] == [[1_789_000_030.0, 30.0]]


async def test_an_agent_whose_process_started_again_is_written_down_as_a_restart(store: MetricsStore) -> None:
    counts = Counts()
    collector = Collector(store, _agent_for, counts)

    def table(elapsed: str) -> list[dict[str, str]]:
        return [
            {"PCPU": "%CPU", "PMEM": "%MEM", "PID": "PID", "PPID": "PPID", "USER": "USER", "ELAPSED": "ELAPSED"},
            {
                "PCPU": "0.0", "PMEM": "0.0", "PID": "1", "PPID": "0", "USER": "root", "ELAPSED": elapsed,
                "COMMAND": "./sys_monitor_agent 192.168.65.254 9999 30 --actions=ps:30,iftop:30",
            },
        ]

    await collector.handle(_packet("ps", table("00:32"), ts=1_789_000_032))
    await collector.handle(_packet("ps", table("00:32"), ts=1_789_000_066))

    assert counts.restarts == 1
    (restart,) = await store.restarts_since([AGENT], 1_789_000_000)
    assert (restart.host, restart.ts, restart.cause) == ("dev-agent", 1_789_000_034, "agent")
    assert restart.actions == ("ps", "iftop")


async def test_a_process_table_is_a_snapshot_not_series(store: MetricsStore) -> None:
    counts = Counts()
    collector = Collector(store, _agent_for, counts)
    rows = [
        {"PCPU": "%CPU", "PMEM": "%MEM", "PID": "PID", "PPID": "PPID", "USER": "USER"},
        {"PCPU": "0.5", "PMEM": "1.0", "PID": "1", "PPID": "0", "USER": "root", "COMMAND": "init"},
    ]

    await collector.handle(_packet("ps", rows, ts=1_789_000_000))

    assert counts.snapshots == 1
    assert await _count(store, "metric_process") == 1
    assert await _count(store, "metric_series") == 0


async def test_series_forgotten_by_the_collector_are_found_again(store: MetricsStore) -> None:
    collector = Collector(store, _agent_for, Counts())
    await collector.handle(_packet("cpu", {"uptime": 1}, ts=1_789_000_000))
    collector.forget_series()
    await collector.handle(_packet("cpu", {"uptime": 31}, ts=1_789_000_030))
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


async def test_a_malformed_packet_is_counted() -> None:
    counts = Counts()
    # Nothing about a malformed packet reaches the store.
    collector = Collector(None, _agent_for, counts)  # type: ignore[arg-type]  # never touched

    await collector.handle(b"{not json")

    assert counts.malformed == 1
