"""New points on the socket (D127)."""

import uuid

from app.metrics.live import Watermarks, read_round
from app.metrics.store import MetricsStore, PointRow, SeriesKey, Source

AGENT = uuid.uuid4()
START = 1_789_000_000


def test_the_first_round_only_remembers() -> None:
    marks = Watermarks(started=START)

    assert marks.changed({1: START + 30}) == {}
    assert marks.changed({1: START + 30}) == {}
    assert marks.changed({1: START + 60}) == {1: START + 30}


def test_a_series_born_after_the_subscription_is_read_from_then() -> None:
    marks = Watermarks(started=START)
    marks.changed({1: START - 10})

    assert marks.changed({1: START - 10, 2: START + 5}) == {2: START}


def test_what_was_pushed_is_not_pushed_again() -> None:
    marks = Watermarks(started=START)
    marks.changed({1: START})
    marks.advance(1, START + 30)

    assert marks.changed({1: START + 30}) == {}


async def test_a_round_carries_only_new_points_of_readable_series(store: MetricsStore) -> None:
    other = uuid.uuid4()
    key = SeriesKey("web-01", "cpu", "uptime", "")
    mine = (await store.series_ids(Source("agent", AGENT), [(key, "s", START)]))[key]
    theirs = (await store.series_ids(Source("agent", other), [(key, "s", START)]))[key]
    await store.write_points([PointRow(mine, START, 1.0), PointRow(theirs, START, 1.0)])
    marks = Watermarks(started=START)

    assert await read_round(store, [AGENT], marks, now=START + 1000) is None

    await store.series_ids(Source("agent", AGENT), [(key, "s", START + 30)])
    await store.series_ids(Source("agent", other), [(key, "s", START + 30)])
    await store.write_points([PointRow(mine, START + 30, 31.0), PointRow(theirs, START + 30, 31.0)])
    pushed = await read_round(store, [AGENT], marks, now=START + 1000)

    assert pushed is not None
    assert [(one.series_id, one.points) for one in pushed.series] == [(mine, [[START + 30.0, 31.0]])]
    assert await read_round(store, [AGENT], marks, now=START + 1000) is None


async def test_a_series_seen_before_its_points_are_written_is_asked_again(store: MetricsStore) -> None:
    key = SeriesKey("web-01", "cpu", "uptime", "")
    series_id = (await store.series_ids(Source("agent", AGENT), [(key, "s", START)]))[key]
    marks = Watermarks(started=START)
    await read_round(store, [AGENT], marks, now=START)

    # The collector has marked the series seen; its batch is not written yet.
    await store.series_ids(Source("agent", AGENT), [(key, "s", START + 30)])
    assert await read_round(store, [AGENT], marks, now=START + 31) is None

    await store.write_points([PointRow(series_id, START + 30, 30.0)])
    pushed = await read_round(store, [AGENT], marks, now=START + 32)

    assert pushed is not None
    assert pushed.series[0].points == [[START + 30.0, 30.0]]
