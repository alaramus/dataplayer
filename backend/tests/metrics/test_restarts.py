"""Restarts from what an agent says of itself, and when they need a person (D130)."""

import uuid

from app.metrics.restarts import (
    REPEATED,
    WINDOW_SECONDS,
    Restart,
    RestartWatch,
    Run,
    Seen,
    known_runs,
    repeated,
)
from app.metrics.store import AgentRunRow, RestartRow

HOST = ("agent", "web-01")


def _run(instance: str, started: int, boot: str = "boot-1") -> Run:
    return Run(instance=instance, version="0.1.1", started=started, boot=boot)


def test_the_first_process_of_a_host_is_new_and_no_restart() -> None:
    watch = RestartWatch()

    assert watch.observe(HOST, _run("a", 100)) == Seen(current=True, new=True)
    assert watch.observe(HOST, _run("a", 100)) == Seen(current=True, new=False)


def test_a_new_instance_on_the_same_boot_is_the_agent_restarting_when_it_started() -> None:
    watch = RestartWatch()
    watch.observe(HOST, _run("a", 100))

    assert watch.observe(HOST, _run("b", 134)) == Seen(current=True, new=True, restart=Restart(134, "agent"))


def test_a_new_boot_with_it_is_the_host_restarting() -> None:
    watch = RestartWatch()
    watch.observe(HOST, _run("a", 100))

    seen = watch.observe(HOST, _run("b", 5000, boot="boot-2"))

    assert seen.restart == Restart(5000, "host")


def test_an_older_process_still_sending_is_neither_current_nor_a_restart() -> None:
    watch = RestartWatch()
    watch.observe(HOST, _run("new", 200))

    assert watch.observe(HOST, _run("old", 100)) == Seen(current=False, new=False)
    # And it did not replace the newer one.
    assert watch.observe(HOST, _run("new", 200)) == Seen(current=True, new=False)


def test_hosts_are_watched_apart() -> None:
    watch = RestartWatch()
    watch.observe(("agent", "web-01"), _run("a", 100))

    assert watch.observe(("agent", "db-01"), _run("b", 150)).restart is None


def test_what_the_store_knew_is_not_taken_for_a_restart_after_this_process_starts_again() -> None:
    agent = uuid.uuid4()
    rows = [AgentRunRow(agent, "web-01", "a", "0.1.1", 100, "boot-1")]
    watch = RestartWatch(known_runs(rows))

    assert watch.observe((agent, "web-01"), _run("a", 100)) == Seen(current=True, new=False)
    assert watch.observe((agent, "web-01"), _run("b", 300)).restart == Restart(300, "agent")


def test_repeated_restarts_within_the_window_are_reported_per_host() -> None:
    agent = uuid.uuid4()
    now = 10_000
    crashing = [RestartRow(agent, "web-01", now - 34 * i, "agent") for i in range(REPEATED)]
    once = [RestartRow(agent, "db-01", now - 5, "host")]
    long_ago = [RestartRow(agent, "old-01", now - WINDOW_SECONDS - 1 - i, "agent") for i in range(REPEATED)]

    (found,) = repeated([*crashing, *once, *long_ago], now)

    assert (found.host, found.count, found.cause) == ("web-01", REPEATED, "agent")
    assert found.last == now
    assert found.first == now - 34 * (REPEATED - 1)
