import pytest

from app.metrics.history import RangeRefused, bucket_seconds, check_range


def test_a_range_that_fits_is_answered_raw() -> None:
    assert bucket_seconds(0, 3600, 1000, densest=120) is None
    assert bucket_seconds(0, 3600, 120, densest=120) is None


def test_a_range_that_does_not_fit_is_bucketed_to_a_readable_width() -> None:
    # A day at thirty-second samples is 2880 points; a thousand need buckets of
    # 87 seconds, and the next readable width is two minutes.
    assert bucket_seconds(0, 86400, 1000, densest=2880) == 120


def test_no_series_gets_more_points_than_asked_for() -> None:
    for span in (3601, 86_400, 7 * 86_400, 90 * 86_400, 366 * 86_400):
        width = bucket_seconds(0, span, 500, densest=10**9)
        assert width is not None
        assert span / width <= 500


def test_beyond_the_ladder_a_width_is_whole_days() -> None:
    width = bucket_seconds(0, 366 * 86_400, 100, densest=10**9)

    assert width is not None
    assert width % 86_400 == 0


def test_a_range_is_at_least_a_minute_and_at_most_a_year() -> None:
    check_range(0, 60)
    with pytest.raises(RangeRefused):
        check_range(0, 59)
    with pytest.raises(RangeRefused):
        check_range(10, 5)
    with pytest.raises(RangeRefused):
        check_range(0, 367 * 86_400)
