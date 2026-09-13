from app.metrics.counters import CounterState
from app.metrics.packets import Sample


def _read(ts: int, value: float, label: str = "eth0") -> Sample:
    return Sample("net", "read", label, "B", ts, value)


def test_a_counter_becomes_its_increment_from_the_second_sample() -> None:
    state = CounterState()

    assert state.expand("agent", [_read(30, 100)]) == []
    assert state.expand("agent", [_read(60, 130)]) == [
        Sample("net", "read_delta", "eth0", "B", 60, 30)
    ]


def test_a_counter_that_went_down_restarted_and_says_nothing() -> None:
    state = CounterState()
    state.expand("agent", [_read(30, 100)])

    assert state.expand("agent", [_read(60, 5)]) == []
    assert state.expand("agent", [_read(90, 15)]) == [
        Sample("net", "read_delta", "eth0", "B", 90, 10)
    ]


def test_a_sample_out_of_order_says_nothing() -> None:
    state = CounterState()
    state.expand("agent", [_read(60, 100)])

    assert state.expand("agent", [_read(30, 150)]) == []


def test_sources_and_labels_keep_their_own_previous_sample() -> None:
    state = CounterState()
    state.expand("a", [_read(30, 100), _read(30, 10, label="lo")])
    state.expand("b", [_read(30, 1000)])

    assert state.expand("a", [_read(60, 110), _read(60, 11, label="lo")]) == [
        Sample("net", "read_delta", "eth0", "B", 60, 10),
        Sample("net", "read_delta", "lo", "B", 60, 1),
    ]


def test_anything_but_a_counter_passes_through() -> None:
    uptime = Sample("cpu", "uptime", "", "s", 30, 1715)

    assert CounterState().expand("agent", [uptime]) == [uptime]
