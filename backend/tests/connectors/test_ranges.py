"""One `Range` header read against a known size (D52)."""

import pytest

from app.connectors.ranges import UnsatisfiableRange, parse_range

SIZE = 1000


def test_no_header_means_the_whole_body() -> None:
    assert parse_range(None, SIZE) is None


def test_a_range_from_the_front() -> None:
    wanted = parse_range("bytes=0-99", SIZE)

    assert wanted is not None
    assert (wanted.start, wanted.end, wanted.length) == (0, 99, 100)


def test_an_open_ended_range_runs_to_the_last_byte() -> None:
    wanted = parse_range("bytes=900-", SIZE)

    assert wanted is not None
    assert (wanted.start, wanted.end) == (900, 999)


def test_a_suffix_range_is_the_last_bytes() -> None:
    """What a player asks for first: an MP4 keeps its index at the end."""
    wanted = parse_range("bytes=-100", SIZE)

    assert wanted is not None
    assert (wanted.start, wanted.end) == (900, 999)


def test_a_suffix_longer_than_the_body_starts_at_the_beginning() -> None:
    wanted = parse_range("bytes=-5000", SIZE)

    assert wanted is not None
    assert (wanted.start, wanted.end) == (0, 999)


def test_an_end_past_the_body_is_clamped() -> None:
    wanted = parse_range("bytes=990-5000", SIZE)

    assert wanted is not None
    assert (wanted.start, wanted.end) == (990, 999)


def test_the_content_range_names_the_whole_size() -> None:
    wanted = parse_range("bytes=0-9", SIZE)

    assert wanted is not None
    assert wanted.content_range(SIZE) == "bytes 0-9/1000"


def test_several_ranges_at_once_mean_the_whole_body() -> None:
    """Allowed, and no media element asks for it."""
    assert parse_range("bytes=0-9,20-29", SIZE) is None


def test_a_unit_other_than_bytes_means_the_whole_body() -> None:
    assert parse_range("items=0-9", SIZE) is None


def test_an_empty_range_means_the_whole_body() -> None:
    assert parse_range("bytes=-", SIZE) is None


@pytest.mark.parametrize("header", ["bytes=1000-", "bytes=5000-6000", "bytes=9-5"])
def test_bytes_that_are_not_there_are_unsatisfiable(header: str) -> None:
    with pytest.raises(UnsatisfiableRange):
        parse_range(header, SIZE)


def test_the_last_nothing_of_something_is_unsatisfiable() -> None:
    with pytest.raises(UnsatisfiableRange):
        parse_range("bytes=-0", SIZE)


def test_every_range_of_an_empty_body_is_unsatisfiable() -> None:
    with pytest.raises(UnsatisfiableRange):
        parse_range("bytes=0-", 0)
