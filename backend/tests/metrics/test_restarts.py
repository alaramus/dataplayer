"""A restart read from the data, and when restarts need a person (D130)."""

import uuid

from app.metrics.packets import ProcessRow, ProcessSnapshot, Sample
from app.metrics.restarts import (
    JITTER_SECONDS,
    REPEATED,
    WINDOW_SECONDS,
    RestartWatch,
    repeated,
)
from app.metrics.store import RestartRow

HOST = ("agent", "dev-agent")
T = 1_789_300_000
AGENT = "./sys_monitor_agent 192.168.65.254 9999 30 --actions=ps:30,cpu:30,iftop:30 --apikey=K"


def _uptime(ts: int, value: float) -> Sample:
    return Sample("cpu", "uptime", "", "s", ts, value)


def _table(ts: int, elapsed: str, command: str = AGENT) -> ProcessSnapshot:
    rows = [
        ProcessRow(1, 0, "root", command, 0.0, 0.0, elapsed),
        ProcessRow(12, 1, "root", "/bin/sh ./run-iftop.sh", 0.0, 0.0, "59:59"),
    ]
    return ProcessSnapshot(host="dev-agent", ts=ts, rows=rows, skipped=0, truncated=0)


def test_uptime_going_down_is_the_host_restarting_at_the_moment_it_booted() -> None:
    watch = RestartWatch()

    assert watch.observe(HOST, [_uptime(T, 5000)]) is None
    assert watch.observe(HOST, [_uptime(T + 30, 5030)]) is None
    restart = watch.observe(HOST, [_uptime(T + 60, 12)])

    assert restart is not None
    assert (restart.ts, restart.cause) == (T + 48, "uptime")


def test_the_agent_s_process_starting_later_is_the_agent_restarting() -> None:
    # Measured on 2026-09-13: every table the crashing agent sent said it had
    # run 32 seconds, 34 seconds after the one before.
    watch = RestartWatch()

    assert watch.observe_processes(HOST, _table(T, "00:32")) is None
    restart = watch.observe_processes(HOST, _table(T + 34, "00:32"))

    assert restart is not None
    assert restart.cause == "agent"
    assert restart.ts == T + 2
    assert "iftop" in restart.actions


def test_an_agent_that_keeps_running_is_not_restarting_whatever_its_rounding() -> None:
    watch = RestartWatch()
    watch.observe_processes(HOST, _table(T, "05:11"))

    for step in range(1, 6):
        # A second either way, as `ps` and the packet's clock round.
        elapsed = 311 + 30 * step + (JITTER_SECONDS - 1 if step % 2 else -1)
        assert watch.observe_processes(HOST, _table(T + 30 * step, f"{elapsed // 60:02d}:{elapsed % 60:02d}")) is None
    # A table without the agent in it says nothing.
    assert watch.observe_processes(HOST, _table(T + 200, "00:01", command="nginx: worker")) is None


def test_a_reboot_seen_in_the_uptime_and_in_the_process_is_one_restart() -> None:
    watch = RestartWatch()
    watch.observe(HOST, [_uptime(T, 5000)])
    watch.observe_processes(HOST, _table(T, "10:00"))

    first = watch.observe(HOST, [_uptime(T + 60, 20)])
    second = watch.observe_processes(HOST, _table(T + 70, "00:28"))

    assert first is not None
    assert second is None


def test_hosts_are_watched_apart_and_old_packets_change_nothing() -> None:
    watch = RestartWatch()
    other = ("agent", "db-01")
    watch.observe(HOST, [_uptime(T, 5000)])
    watch.observe(other, [_uptime(T, 10)])

    assert watch.observe(other, [_uptime(T + 30, 40)]) is None
    # Late, not lower: a packet older than the last one read is not a restart.
    assert watch.observe(HOST, [_uptime(T - 30, 4970)]) is None
    assert watch.observe(HOST, [_uptime(T + 30, 5030)]) is None


def test_a_host_needs_a_person_once_it_restarted_again_and_again_within_the_window() -> None:
    agent = uuid.uuid4()
    now = T + WINDOW_SECONDS
    crashing = [RestartRow(agent, "crash", now - 33 * i, "agent", ("ps", "iftop")) for i in range(REPEATED)]
    once = [RestartRow(agent, "rebooted", now - 60, "uptime")]
    long_ago = [RestartRow(agent, "old", now - WINDOW_SECONDS - 33 * i, "agent") for i in range(5)]

    (found,) = repeated([*crashing, *once, *long_ago], now)

    assert (found.host, found.count, found.cause) == ("crash", REPEATED, "agent")
    assert found.actions == ("ps", "iftop")
    assert found.last == now
    assert found.first == now - 33 * (REPEATED - 1)
