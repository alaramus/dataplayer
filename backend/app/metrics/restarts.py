"""A restart read from what an agent sends, and when restarts need a person (D130).

Two signs in the data. A host's uptime going down is the host restarting; its
moment is the packet's time less the uptime. The agent's own row in its process
table starting later than it did is the agent restarting; its moment is the
table's time less the row's elapsed time. Measured on 2026-09-13, the crash of
sys_monitor_agent 1.14.0 on `iftop` shows only as the second: the uptime a
container reads is the Docker VM's and keeps growing, and its interface
counters are not counters to read a restart from (a value is divided by an
interval that is 30 or 31 seconds, so an idle one goes down).

Pure, so both rules can be read and tested without the collector around them.
"""

import uuid
from collections import defaultdict
from collections.abc import Hashable, Sequence
from dataclasses import dataclass

from app.metrics.packets import ProcessSnapshot, Sample, agent_process_of
from app.metrics.store import RestartCause, RestartRow

UPTIME_FIELD = ("cpu", "uptime")
# How far apart two readings of one start may be: `ps` and a packet's time
# are each rounded to a second, and taken a moment apart.
JITTER_SECONDS = 5
# One restart shows twice when a host reboots, once in its uptime and once in
# the agent's process. Under the half minute a crashing agent lives.
MERGE_SECONDS = 10
# How many restarts of one host within the window make an attention item.
WINDOW_SECONDS = 15 * 60
REPEATED = 3


@dataclass(frozen=True, slots=True)
class Restart:
    ts: int
    cause: RestartCause
    actions: tuple[str, ...] = ()


class RestartWatch:
    """The last start seen per host, by either sign, and its last restart."""

    def __init__(self) -> None:
        self._booted: dict[Hashable, tuple[int, float]] = {}
        self._agent_started: dict[Hashable, int] = {}
        self._last_restart: dict[Hashable, int] = {}

    def observe(self, source: Hashable, samples: Sequence[Sample]) -> Restart | None:
        for sample in samples:
            if (sample.metric, sample.field) != UPTIME_FIELD:
                continue
            previous = self._booted.get(source)
            if previous is not None and sample.ts <= previous[0]:
                continue
            self._booted[source] = (sample.ts, sample.value)
            if previous is not None and sample.value < previous[1]:
                return self._restarted(source, Restart(int(sample.ts - sample.value), "uptime"))
        return None

    def observe_processes(self, source: Hashable, snapshot: ProcessSnapshot) -> Restart | None:
        agent = agent_process_of(snapshot)
        if agent is None:
            return None
        previous = self._agent_started.get(source)
        if previous is not None and agent.started < previous + JITTER_SECONDS:
            return None
        self._agent_started[source] = agent.started
        if previous is None:
            return None
        return self._restarted(source, Restart(agent.started, "agent", agent.actions))

    def _restarted(self, source: Hashable, restart: Restart) -> Restart | None:
        last = self._last_restart.get(source)
        if last is not None and abs(restart.ts - last) < MERGE_SECONDS:
            return None
        self._last_restart[source] = restart.ts
        return restart


@dataclass(frozen=True, slots=True)
class Repeated:
    source_id: uuid.UUID
    host: str
    count: int
    first: int
    last: int
    cause: RestartCause
    actions: tuple[str, ...]


def repeated(restarts: Sequence[RestartRow], now: int) -> list[Repeated]:
    """Hosts that restarted at least `REPEATED` times within the window, the
    most recent first; the cause and the actions are the latest restart's."""
    by_host: dict[tuple[uuid.UUID, str], list[RestartRow]] = defaultdict(list)
    for restart in restarts:
        if restart.ts > now - WINDOW_SECONDS:
            by_host[(restart.source_id, restart.host)].append(restart)
    found: list[Repeated] = []
    for (source_id, host), rows in by_host.items():
        if len(rows) < REPEATED:
            continue
        latest = max(rows, key=lambda row: row.ts)
        found.append(
            Repeated(
                source_id=source_id,
                host=host,
                count=len(rows),
                first=min(row.ts for row in rows),
                last=latest.ts,
                cause=latest.cause,
                actions=latest.actions,
            )
        )
    return sorted(found, key=lambda one: one.last, reverse=True)
