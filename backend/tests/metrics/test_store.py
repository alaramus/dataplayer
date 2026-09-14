"""The metrics store against a real TimescaleDB (D126)."""

import time
import uuid
from typing import Any

import pytest
from sqlalchemy import text

from app.metrics.history import RAW, ROLLUPS
from app.metrics.migrations import MIGRATIONS
from app.metrics.protocol import HostDescription
from app.metrics.store import (
    AgentRunRow,
    MetricsStore,
    PointRow,
    ProcessPart,
    ProcessRow,
    RestartRow,
    SeriesKey,
    Source,
    StoreUnavailable,
    store_url,
)
from tests.metrics.conftest import refresh_rollups

AGENT = Source(kind="agent", id=uuid.uuid4())
START = 1_789_000_000


async def _scalar(store: MetricsStore, sql: str, parameters: dict[str, Any] | None = None) -> Any:
    async with store._engine.connect() as connection:
        if parameters is None:
            return (await connection.execute(text(sql))).scalar_one()
        return (await connection.execute(text(sql), parameters)).scalar_one()


ROLLUP_COUNTS = {
    "metric_point_5m": "SELECT count(*) FROM metric_point_5m WHERE series_id = :id",
    "metric_point_1h": "SELECT count(*) FROM metric_point_1h WHERE series_id = :id",
}


async def test_migrating_twice_changes_nothing(store: MetricsStore) -> None:
    assert await store.migrate() == MIGRATIONS[-1].version

    assert await _scalar(store, "SELECT count(*) FROM metrics_schema_version") == len(MIGRATIONS)
    hypertables = await _scalar(
        store,
        "SELECT count(*) FROM timescaledb_information.hypertables "
        "WHERE hypertable_name IN ('metric_point', 'metric_process')",
    )
    assert hypertables == 2
    policies = await _scalar(
        store,
        "SELECT count(*) FROM timescaledb_information.jobs "
        "WHERE proc_name = 'policy_retention' AND hypertable_name IN "
        "('metric_point', 'metric_process', 'metric_restart', 'metric_point_5m', 'metric_point_1h')",
    )
    assert policies == 5
    compressed = await _scalar(
        store,
        "SELECT count(*) FROM timescaledb_information.jobs "
        "WHERE proc_name = 'policy_compression'",
    )
    assert compressed == 4


async def test_the_store_keeps_each_table_as_long_as_history_reads_it(store: MetricsStore) -> None:
    tables = (RAW, "metric_point"), *zip(ROLLUPS, ("metric_point_5m", "metric_point_1h"), strict=True)
    kept = {
        tier.name: await _scalar(
            store,
            "SELECT EXTRACT(epoch FROM CAST(config->>'drop_after' AS interval)) "
            "FROM timescaledb_information.jobs WHERE proc_name = 'policy_retention' "
            "AND hypertable_name = :table",
            {"table": table},
        )
        for tier, table in tables
    }

    assert kept == {"raw": RAW.kept, **{tier.name: tier.kept for tier in ROLLUPS}}
    # A refresh reaching back past raw retention would delete what it rolled up.
    reaches = await _scalar(
        store,
        "SELECT max(EXTRACT(epoch FROM CAST(config->>'start_offset' AS interval))) "
        "FROM timescaledb_information.jobs WHERE proc_name = 'policy_refresh_continuous_aggregate'",
    )
    assert reaches < RAW.kept


async def test_a_series_is_minted_once_whoever_asks(store: MetricsStore) -> None:
    key = SeriesKey("web-01", "cpu", "cpu", "total")

    first = await store.series_ids(AGENT, [(key, "%", START)])
    again = await store.series_ids(AGENT, [(key, "%", START + 30)])
    other = await store.series_ids(
        Source(kind="agent", id=uuid.uuid4()), [(key, "%", START)]
    )

    assert first == again
    assert other[key] != first[key]
    (series,) = await store.series([first[key]])
    assert series.unit == "%"
    assert int(series.last_seen.timestamp()) == START + 30


async def test_points_come_back_raw_and_bucketed(store: MetricsStore) -> None:
    key = SeriesKey("web-01", "memory", "MemFree", "")
    series_id = (await store.series_ids(AGENT, [(key, "kB", START)]))[key]
    await store.write_points(
        [PointRow(series_id, START + offset * 30, float(offset)) for offset in range(120)]
    )

    raw = await store.raw_points([series_id], START, START + 3600)
    assert len(raw[series_id]) == 120
    assert raw[series_id][0] == [float(START), 0.0]
    assert await store.densest([series_id], START, START + 3600, cap=1000) == 120

    bucketed = await store.bucketed_points([series_id], START, START + 3600, 600)
    first_bucket = bucketed[series_id][0]
    assert len(first_bucket) == 4
    low, high = first_bucket[2], first_bucket[3]
    assert low <= first_bucket[1] <= high

    (series,) = await store.series([series_id])
    assert int(series.last_seen.timestamp()) == START + 119 * 30


async def test_the_newest_process_table_is_read_sorted_with_what_the_host_had(store: MetricsStore) -> None:
    now = int(time.time())

    def row(pid: int, cpu: float, memory: float) -> ProcessRow:
        return ProcessRow(pid, 1, "root", "S", cpu, memory, 4096 * pid, now - 3600, "worker", f"worker {pid}")

    await store.write_processes(AGENT, ProcessPart("web-01", now - 60, 90, [row(1, 99.0, 99.0)]))
    await store.write_processes(AGENT, ProcessPart("web-01", now, 120, [row(2, 5.0, 1.0), row(3, 1.0, 7.5)]))
    await store.write_processes(AGENT, ProcessPart("web-01", now, 120, [row(4, 3.0, 2.0)]))

    by_memory = await store.latest_processes(AGENT.id, "web-01", "pmem", 2)

    assert by_memory is not None
    assert (by_memory.ts, by_memory.total) == (now, 120)
    assert by_memory.rows == [row(3, 1.0, 7.5), row(4, 3.0, 2.0)]
    assert await store.latest_processes(AGENT.id, "db-01", "pmem", 2) is None


async def test_the_newest_agent_process_of_a_host_and_what_the_host_is_are_kept(store: MetricsStore) -> None:
    description = HostDescription(
        os="Debian 12", kernel="6.1.0", arch="arm64", cpus=4, cpu_model="Cortex-A72",
        memory=8 * 1024**3, boot_time=START, collectors={"cpu": 15},
    )
    first = AgentRunRow(AGENT.id, "web-01", "a", "0.1.1", START, "boot-1")
    await store.write_run(first)
    await store.write_run(first, description, START + 5)
    later = AgentRunRow(AGENT.id, "web-01", "b", "0.1.2", START + 100, "boot-1")
    await store.write_run(later)

    assert await store.runs() == [later]
    (kept,) = await store.hosts([AGENT.id])
    # A new process without a description keeps the one the host already had.
    assert (kept.run, kept.info, kept.last_seen) == (later, description, None)
    assert await store.hosts([uuid.uuid4()]) == []


async def test_migration_4_takes_what_agents_wrote_and_keeps_connections(store: MetricsStore) -> None:
    connection_source = Source(kind="connector", id=uuid.uuid4())
    key = SeriesKey("", "database", "size", "")
    agent_key = SeriesKey("web-01", "cpu", "cpu", "total")
    theirs = (await store.series_ids(connection_source, [(key, "B", START)]))[key]
    old = (await store.series_ids(AGENT, [(agent_key, "%", START)]))[agent_key]
    start = _hour_days_ago(3)
    await store.write_points([PointRow(series, start + i * 60, 1.0) for series in (theirs, old) for i in range(120)])
    await refresh_rollups(store)
    await store.write_restart(RestartRow(AGENT.id, "web-01", start, "agent"))

    async with store._engine.connect() as raw:
        connection = await raw.execution_options(isolation_level="AUTOCOMMIT")
        for statement in MIGRATIONS[3].statements:
            await connection.execute(text(statement))

    assert [s.id for s in await store.catalog([connection_source.id, AGENT.id])] == [theirs]
    for count in ROLLUP_COUNTS.values():
        assert await _scalar(store, count, {"id": old}) == 0
        assert await _scalar(store, count, {"id": theirs}) > 0
    assert await store.restarts_since([AGENT.id], start - 1) == []


async def test_purging_a_source_takes_its_samples_and_leaves_the_rest(
    store: MetricsStore,
) -> None:
    other = Source(kind="agent", id=uuid.uuid4())
    key = SeriesKey("h", "cpu", "cpu", "total")
    mine = (await store.series_ids(AGENT, [(key, "%", START)]))[key]
    theirs = (await store.series_ids(other, [(key, "%", START)]))[key]
    await store.write_points([PointRow(mine, START, 1.0), PointRow(theirs, START, 2.0)])

    await store.purge(AGENT)

    assert await store.series([mine]) == []
    assert await store.raw_points([theirs], START - 60, START + 60) == {
        theirs: [[float(START), 2.0]]
    }
    assert await store.catalog([AGENT.id]) == []
    assert [s.id for s in await store.catalog([other.id])] == [theirs]


async def test_when_the_agent_was_last_heard_from(store: MetricsStore) -> None:
    key = SeriesKey("h", "cpu", "uptime", "")
    await store.series_ids(AGENT, [(key, "s", START + 90)])

    heard = await store.last_heard([AGENT.id])

    assert int(heard[AGENT.id].timestamp()) == START + 90


async def test_a_store_that_does_not_answer_says_so_without_its_driver_text(
    store_options: dict[str, Any],
) -> None:
    closed = MetricsStore(store_url({**store_options, "host": "127.0.0.1", "port": 1}))
    try:
        assert not await closed.ping()
        with pytest.raises(StoreUnavailable) as refusal:
            await closed.migrate()
        assert str(refusal.value) == "The metrics store could not be prepared"
        assert store_options["password"] not in str(refusal.value)
    finally:
        await closed.aclose()


def _hour_days_ago(days: int) -> int:
    return (int(time.time()) - days * 86400) // 3600 * 3600


async def test_buckets_read_from_a_rollup_are_the_buckets_read_from_samples(
    store: MetricsStore,
) -> None:
    key = SeriesKey("web-01", "cpu", "cpu", "total")
    series_id = (await store.series_ids(AGENT, [(key, "%", START)]))[key]
    start = _hour_days_ago(2)
    await store.write_points(
        [PointRow(series_id, start + i * 30, float((i * 7) % 50)) for i in range(6 * 120)]
    )
    await refresh_rollups(store)
    end = start + 6 * 3600 - 1

    raw = await store.bucketed_points([series_id], start, end, 3600, "raw")
    by_5m = await store.bucketed_points([series_id], start, end, 3600, "5m")
    by_1h = await store.bucketed_points([series_id], start, end, 3600, "1h")

    assert len(raw[series_id]) == 6
    for other in (by_5m, by_1h):
        assert len(other[series_id]) == 6
        for mine, theirs in zip(raw[series_id], other[series_id], strict=True):
            assert mine == pytest.approx(theirs)


async def test_the_densest_series_is_counted_no_further_than_the_budget(
    store: MetricsStore,
) -> None:
    key = SeriesKey("web-01", "cpu", "uptime", "")
    series_id = (await store.series_ids(AGENT, [(key, "s", START)]))[key]
    await store.write_points([PointRow(series_id, START + i, float(i)) for i in range(50)])

    assert await store.densest([series_id], START, START + 60, cap=11) == 11
    assert await store.densest([series_id], START, START + 60, cap=1000) == 50


async def test_purging_a_source_takes_its_rollups_and_restarts_too(store: MetricsStore) -> None:
    other = Source(kind="agent", id=uuid.uuid4())
    key = SeriesKey("h", "cpu", "cpu", "total")
    mine = (await store.series_ids(AGENT, [(key, "%", START)]))[key]
    theirs = (await store.series_ids(other, [(key, "%", START)]))[key]
    start = _hour_days_ago(3)
    await store.write_points(
        [PointRow(series, start + i * 60, 1.0) for series in (mine, theirs) for i in range(120)]
    )
    await refresh_rollups(store)
    await store.write_restart(RestartRow(AGENT.id, "h", start, "agent"))
    await store.write_run(AgentRunRow(AGENT.id, "h", "a", "0.1.1", start, "boot"))

    await store.purge(AGENT)

    for count in ROLLUP_COUNTS.values():
        assert await _scalar(store, count, {"id": mine}) == 0
        assert await _scalar(store, count, {"id": theirs}) > 0
    assert await store.restarts_since([AGENT.id], start - 1) == []
    assert await store.runs() == []


async def test_restarts_are_kept_and_read_back_by_source(store: MetricsStore) -> None:
    other = uuid.uuid4()
    await store.write_restart(RestartRow(AGENT.id, "web-01", START, "host"))
    await store.write_restart(RestartRow(AGENT.id, "web-01", START + 33, "agent"))
    await store.write_restart(RestartRow(AGENT.id, "web-01", START + 900, "host"))
    await store.write_restart(RestartRow(other, "db-01", START + 40, "agent"))

    found = await store.restarts_since([AGENT.id], START)

    assert found == [
        RestartRow(AGENT.id, "web-01", START + 33, "agent"),
        RestartRow(AGENT.id, "web-01", START + 900, "host"),
    ]


async def test_what_the_store_takes_is_measured(store: MetricsStore) -> None:
    key = SeriesKey("h", "cpu", "cpu", "total")
    series_id = (await store.series_ids(AGENT, [(key, "%", START)]))[key]
    await store.write_points([PointRow(series_id, START + i, 1.0) for i in range(100)])

    usage = await store.usage()

    assert usage.series == 1
    assert usage.bytes > 0


async def test_dropping_the_schema_leaves_a_database_the_migrations_prepare_again(
    store: MetricsStore,
) -> None:
    await store.drop_schema()

    assert await _scalar(store, "SELECT to_regclass('metric_point') IS NULL")
    assert await _scalar(store, "SELECT to_regclass('metric_host') IS NULL")
    assert await _scalar(store, "SELECT to_regclass('metric_point_1h') IS NULL")
    assert await _scalar(store, "SELECT count(*) FROM timescaledb_information.jobs WHERE hypertable_name IS NOT NULL") == 0

    assert await store.migrate() == MIGRATIONS[-1].version
    assert await _scalar(store, "SELECT to_regclass('metric_point_5m') IS NOT NULL")
