"""A restart read from what an agent says of itself, and when restarts need a person (D130).

Every DPMA/1 datagram names the agent process that sent it, `agent.instance`,
when that process started, and the host's boot id. A new instance is a
restart at its start; a new boot with it is the host restarting.

Pure, so the rules can be read and tested without the collector around them.
"""

import uuid
from collections import defaultdict
from collections.abc import Hashable, Iterable, Sequence
from dataclasses import dataclass

from app.metrics.store import AgentRunRow, RestartCause, RestartRow

# How many restarts of one host within the window make an attention item.
WINDOW_SECONDS = 15 * 60
REPEATED = 3


@dataclass(frozen=True, slots=True)
class Run:
    instance: str
    version: str
    started: int
    boot: str


@dataclass(frozen=True, slots=True)
class Restart:
    ts: int
    cause: RestartCause


@dataclass(frozen=True, slots=True)
class Seen:
    # The datagram came from the newest agent process known for its host.
    current: bool
    # That process was not known before: whoever keeps the newest one writes it.
    new: bool
    restart: Restart | None = None


class RestartWatch:
    """The newest agent process of every host."""

    def __init__(self, known: Iterable[tuple[Hashable, Run]] = ()) -> None:
        self._runs: dict[Hashable, Run] = dict(known)

    def observe(self, host: Hashable, run: Run) -> Seen:
        previous = self._runs.get(host)
        if previous is not None and previous.instance == run.instance:
            return Seen(current=True, new=False)
        # An older process still sending, or a second agent reporting under the
        # same host name: neither is this host restarting.
        if previous is not None and run.started < previous.started:
            return Seen(current=False, new=False)
        self._runs[host] = run
        if previous is None:
            return Seen(current=True, new=True)
        cause: RestartCause = "host" if run.boot != previous.boot else "agent"
        return Seen(current=True, new=True, restart=Restart(run.started, cause))


def known_runs(rows: Iterable[AgentRunRow]) -> list[tuple[tuple[uuid.UUID, str], Run]]:
    return [
        ((row.source_id, row.host), Run(row.instance, row.version, row.started, row.boot))
        for row in rows
    ]


@dataclass(frozen=True, slots=True)
class Repeated:
    source_id: uuid.UUID
    host: str
    count: int
    first: int
    last: int
    cause: RestartCause


def repeated(restarts: Sequence[RestartRow], now: int) -> list[Repeated]:
    """Hosts that restarted at least `REPEATED` times within the window, the
    most recent first; the cause is the latest restart's."""
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
            )
        )
    return sorted(found, key=lambda one: one.last, reverse=True)
