"""How long to wait before probing a connection again.

A pure function, tested without a socket or a database: a dead host answers by
timing out, so probing it as often as a live one makes every round as slow as
the worst member of it.
"""

from app.connectors.health import delay_after

BASE = 10.0
CAP = 120.0


def test_a_healthy_connection_is_probed_at_the_plain_interval() -> None:
    assert delay_after(misses=0, base=BASE, cap=CAP) == BASE


def test_each_failure_doubles_the_wait() -> None:
    assert delay_after(misses=1, base=BASE, cap=CAP) == 20.0
    assert delay_after(misses=2, base=BASE, cap=CAP) == 40.0
    assert delay_after(misses=3, base=BASE, cap=CAP) == 80.0


def test_the_wait_stops_growing_at_the_cap() -> None:
    assert delay_after(misses=4, base=BASE, cap=CAP) == CAP
    assert delay_after(misses=400, base=BASE, cap=CAP) == CAP


def test_a_cap_below_the_interval_still_wins() -> None:
    """Nonsense settings must not produce a negative or shrinking wait."""
    assert delay_after(misses=0, base=BASE, cap=1.0) == 1.0
