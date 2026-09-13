"""The metrics store against a real TimescaleDB (D126)."""

import uuid
from typing import Any

import pytest
from sqlalchemy import text

from app.metrics.migrations import MIGRATIONS
from app.metrics.packets import ProcessRow, ProcessSnapshot
from app.metrics.store import (
    MetricsStore,
    PointRow,
    SeriesKey,
    Source,
    StoreUnavailable,
    store_url,
)
from tests.metrics.conftest import needs_store

pytestmark = needs_store

AGENT = Source(kind="agent", id=uuid.uuid4())
START = 1_789_000_000


async def _scalar(store: MetricsStore, sql: str) -> Any:
    async with store._engine.connect() as connection:
        return (await connection.execute(text(sql))).scalar_one()


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
        "WHERE proc_name = 'policy_retention' "
        "AND hypertable_name IN ('metric_point', 'metric_process')",
    )
    assert policies == 2


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
    assert await store.densest([series_id], START, START + 3600) == 120

    bucketed = await store.bucketed_points([series_id], START, START + 3600, 600)
    first_bucket = bucketed[series_id][0]
    assert len(first_bucket) == 4
    low, high = first_bucket[2], first_bucket[3]
    assert low <= first_bucket[1] <= high

    (series,) = await store.series([series_id])
    assert int(series.last_seen.timestamp()) == START + 119 * 30


async def test_a_process_snapshot_is_written(store: MetricsStore) -> None:
    snapshot = ProcessSnapshot(
        host="web-01",
        ts=START,
        rows=[ProcessRow(1, 0, "root", "init", 0.5, 0.1, "01:00")],
        skipped=0,
        truncated=0,
    )

    await store.write_processes(AGENT, snapshot)

    assert await _scalar(store, "SELECT count(*) FROM metric_process") == 1


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
