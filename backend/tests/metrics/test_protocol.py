"""DPMA/1 as the metrics process reads it (D130)."""

import json

import pytest

from app.metrics import keys
from app.metrics.protocol import (
    FORGET_SECONDS,
    FUTURE_SECONDS,
    PAST_SECONDS,
    SEQ_WINDOW,
    Freshness,
    HostReport,
    MetricsReport,
    ProcessesReport,
    frame_of,
    report_of,
    signed_with,
)
from tests.metrics.datagrams import host, metrics, process, processes, signed

KEY = "an-issued-key"
NOW = 1_789_300_000


def test_the_key_id_is_where_the_fingerprint_starts() -> None:
    assert keys.key_id(KEY) == keys.fingerprint(KEY)[:16]


def test_a_signed_datagram_is_read_and_checked_over_its_bytes() -> None:
    body = metrics([["cpu", "utilization", "total", "%", 12.5]], time=NOW)
    frame = frame_of(signed(KEY, body))

    assert frame is not None
    assert frame.key_id == keys.key_id(KEY)
    assert signed_with(frame, KEY)
    assert not signed_with(frame, "another-key")


def test_a_body_changed_after_signing_is_not_signed_with_the_key() -> None:
    raw = signed(KEY, metrics([["cpu", "utilization", "total", "%", 12.5]], time=NOW))
    frame = frame_of(raw.replace(b"12.5", b"99.5"))

    assert frame is not None
    assert not signed_with(frame, KEY)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"appkey": "NEWTESTKEY", "action": "monitor-cpu"}',
        b"DPMA/2 0123456789abcdef c2lnbmF0dXJl\n{}",
        b"DPMA/1 0123456789ABCDEF " + b"A" * 43 + b"\n{}",
        b"DPMA/1 0123456789abcdef not*base64\n{}",
        b"DPMA/1 0123456789abcdef " + b"A" * 20 + b"\n{}",
        b"DPMA/1 0123456789abcdef " + b"A" * 43 + b" extra\n{}",
        b"DPMA/1 0123456789abcdef " + b"A" * 200 + b"\n{}",
        b"DPMA/1 0123456789abcdef " + b"A" * 43,
        b"x" * 65508,
    ],
    ids=[
        "the old format",
        "another version",
        "an upper-case key id",
        "a signature not in base64url",
        "a short signature",
        "a fourth field",
        "a first line too long",
        "no body",
        "larger than a datagram",
    ],
)
def test_what_is_not_a_dpma_1_datagram_is_refused(raw: bytes) -> None:
    assert frame_of(raw) is None


def test_the_three_kinds_are_read() -> None:
    sample = metrics([["net", "receive", "eth0", "B/s", 1834], ["cpu", "load1", "", "", 0.5]], time=NOW)
    table = processes([process(1), process(2)], part=(2, 3), time=NOW)

    read = report_of(json.dumps(sample).encode())
    assert isinstance(read, MetricsReport)
    # A whole number a Go encoder wrote for a float is still a number.
    assert read.samples[0] == ("net", "receive", "eth0", "B/s", 1834.0)
    rows = report_of(json.dumps(table).encode())
    assert isinstance(rows, ProcessesReport)
    assert rows.part == (2, 3) and len(rows.rows) == 2
    described = report_of(json.dumps(host(time=NOW)).encode())
    assert isinstance(described, HostReport)
    assert described.info.cpus == 8


@pytest.mark.parametrize(
    "sample",
    [
        ["CPU", "utilization", "total", "%", 1],
        ["cpu", "utilization-total", "", "%", 1],
        ["cpu", "utilization", "x" * 129, "%", 1],
        ["cpu", "utilization", "total", "kB", 1],
        ["cpu", "utilization", "total", "%", "12.5"],
        ["cpu", "utilization", "total", "%"],
    ],
)
def test_one_bad_sample_refuses_the_whole_body(sample: list[object]) -> None:
    body = metrics([["cpu", "utilization", "cpu0", "%", 3], sample], time=NOW)

    assert report_of(json.dumps(body).encode()) is None


def test_a_value_that_is_not_finite_is_refused() -> None:
    body = json.dumps(metrics([["cpu", "utilization", "total", "%", 1]], time=NOW)).replace("1]]", "NaN]]")

    assert report_of(body.encode()) is None


def test_a_body_of_another_version_or_kind_or_with_a_text_number_is_refused() -> None:
    good = metrics([], time=NOW)

    assert report_of(json.dumps({**good, "v": 2}).encode()) is None
    assert report_of(json.dumps({**good, "kind": "logs"}).encode()) is None
    assert report_of(json.dumps({**good, "seq": "1"}).encode()) is None
    assert report_of(json.dumps({**good, "seq": 0}).encode()) is None
    assert report_of(json.dumps(processes([], part=(3, 2), time=NOW)).encode()) is None
    assert report_of(b"not json") is None


def test_a_field_added_to_version_1_later_is_ignored() -> None:
    body = {**metrics([], time=NOW), "region": "eu"}

    assert isinstance(report_of(json.dumps(body).encode()), MetricsReport)


def test_a_body_too_old_or_too_far_ahead_is_refused() -> None:
    fresh = Freshness()

    assert fresh.check("i", 1, NOW - PAST_SECONDS - 1, NOW) == "stale"
    assert fresh.check("i", 2, NOW + FUTURE_SECONDS + 1, NOW) == "future"
    assert fresh.check("i", 3, NOW - PAST_SECONDS, NOW) is None
    assert fresh.check("i", 4, NOW + FUTURE_SECONDS, NOW) is None


def test_a_sequence_number_is_accepted_once_per_instance_in_any_order() -> None:
    fresh = Freshness()

    assert fresh.check("a", 5, NOW, NOW) is None
    assert fresh.check("a", 3, NOW, NOW) is None
    assert fresh.check("a", 5, NOW, NOW) == "replayed"
    assert fresh.check("a", 3, NOW, NOW) == "replayed"
    assert fresh.check("a", 4, NOW, NOW) is None
    # Another instance counts from one again.
    assert fresh.check("b", 5, NOW, NOW) is None


def test_a_number_below_the_window_is_refused_as_if_it_had_been_seen() -> None:
    fresh = Freshness()
    for seq in range(1, 3 * SEQ_WINDOW):
        assert fresh.check("a", seq, NOW, NOW) is None

    highest = 3 * SEQ_WINDOW - 1
    assert fresh.check("a", highest - SEQ_WINDOW, NOW, NOW) == "replayed"
    assert fresh.check("a", highest + 5, NOW, NOW) is None


def test_a_quiet_instance_is_forgotten() -> None:
    fresh = Freshness()
    fresh.check("a", 7, NOW, NOW)

    fresh.forget_quiet(NOW + FORGET_SECONDS - 1)
    assert fresh.check("a", 7, NOW, NOW) == "replayed"
    fresh.forget_quiet(NOW + FORGET_SECONDS + 1)
    assert fresh.check("a", 7, NOW, NOW) is None
