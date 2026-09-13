import pytest

from app.metrics.history import (
    DAY,
    RAW,
    Density,
    RangeRefused,
    check_range,
    density,
    raw_reaches,
)

NOW = 1_789_300_000


def test_a_range_that_fits_is_answered_raw() -> None:
    assert density(NOW - 3600, NOW, 1000, densest=120, now=NOW) == Density(None, "raw")
    assert density(NOW - 3600, NOW, 120, densest=120, now=NOW) == Density(None, "raw")


def test_a_range_that_does_not_fit_is_bucketed_to_a_readable_width() -> None:
    # A day at thirty-second samples is 2880 points; a thousand need buckets of
    # 87 seconds, and the next readable width is two minutes, finer than any
    # rollup holds.
    assert density(NOW - DAY, NOW, 1000, densest=2880, now=NOW) == Density(120, "raw")


def test_a_width_a_rollup_divides_is_read_from_the_coarsest_such_rollup() -> None:
    # A week in 600 points wants 1008 s: 1800, which five-minute rollups divide.
    assert density(NOW - 7 * DAY, NOW, 600, densest=20160, now=NOW) == Density(1800, "5m")
    # Thirty days in 600 points: 4320 s, read as two-hour buckets of hourly rollups.
    assert density(NOW - 30 * DAY, NOW, 600, densest=None, now=NOW) == Density(7200, "1h")


def test_samples_older_than_raw_retention_are_read_from_a_rollup_even_when_they_would_fit() -> None:
    start = NOW - RAW.kept - DAY
    assert not raw_reaches(start, NOW)

    # Two hours asked at 1000 points would be raw ten-second buckets; raw
    # samples are gone by then, so five-minute rollups are as fine as it goes.
    assert density(start, start + 7200, 1000, densest=None, now=NOW) == Density(300, "5m")


def test_a_range_older_than_the_five_minute_rollups_is_read_hourly() -> None:
    start = NOW - 60 * DAY

    assert density(start, start + DAY, 1000, densest=None, now=NOW) == Density(3600, "1h")


def test_no_series_gets_more_points_than_asked_for() -> None:
    for span in (3601, DAY, 7 * DAY, 90 * DAY, 366 * DAY):
        found = density(NOW - span, NOW, 500, densest=10**9, now=NOW)
        assert found.bucket_seconds is not None
        assert span / found.bucket_seconds <= 500


def test_beyond_the_ladder_a_width_is_whole_days() -> None:
    found = density(NOW - 366 * DAY, NOW, 100, densest=None, now=NOW)

    assert found.bucket_seconds is not None
    assert found.bucket_seconds % DAY == 0
    assert found.tier == "1h"


def test_a_range_is_at_least_a_minute_and_at_most_a_year() -> None:
    check_range(0, 60)
    with pytest.raises(RangeRefused):
        check_range(0, 59)
    with pytest.raises(RangeRefused):
        check_range(10, 5)
    with pytest.raises(RangeRefused):
        check_range(0, 367 * DAY)
