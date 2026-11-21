"""What a Docker daemon is measured by (D128, D415).

One poll is the list of containers and `stats` of at most `POLLED` running
ones by name, read concurrently. `stream=false` without `one-shot`: the
daemon waits about a second to pair two samples, which is what the CPU
percent is the difference of (*checked*, Engine 29.10: one second alone,
thirty at once in two). With `one-shot` the pair is empty.
"""

import asyncio
from typing import Any

from app.adapters.docker.inventory import name_of, read_containers
from app.adapters.docker.session import DockerSession, segment
from app.adapters.metrics import MetricPreset, MetricRecipe, MetricSample
from app.adapters.protocol import AdapterError, NodeNotFound
from app.core.translation import N_

# How many running containers one poll measures.
POLLED = 50
_STATS_SECONDS = 8.0


def _number(source: Any, name: str) -> float | None:
    found = source.get(name) if isinstance(source, dict) else None
    if isinstance(found, bool) or not isinstance(found, int | float):
        return None
    return float(found)


def cpu_percent(stats: dict[str, Any]) -> float | None:
    """The share of one CPU used between the two samples, as `docker stats`
    says it: above 100 when more than one is busy."""
    now, before = stats.get("cpu_stats"), stats.get("precpu_stats")
    used = _number((now or {}).get("cpu_usage"), "total_usage")
    used_before = _number((before or {}).get("cpu_usage"), "total_usage")
    system = _number(now, "system_cpu_usage")
    system_before = _number(before, "system_cpu_usage")
    if None in (used, used_before, system, system_before):
        return None
    assert used is not None and used_before is not None
    assert system is not None and system_before is not None
    spent, passed = used - used_before, system - system_before
    if spent < 0 or passed <= 0:
        return None
    cpus = _number(now, "online_cpus") or len(
        ((now or {}).get("cpu_usage") or {}).get("percpu_usage") or []
    )
    return spent / passed * (cpus or 1) * 100.0


def memory_used(stats: dict[str, Any]) -> float | None:
    """Memory in use less the page cache the kernel may take back, as
    `docker stats` counts it: `inactive_file` on cgroup v2, `total_inactive_file`
    on v1."""
    memory = stats.get("memory_stats")
    usage = _number(memory, "usage")
    if usage is None:
        return None
    inner = (memory or {}).get("stats")
    cache = _number(inner, "inactive_file")
    if cache is None:
        cache = _number(inner, "total_inactive_file")
    return max(usage - (cache or 0.0), 0.0)


def _network(stats: dict[str, Any], field: str) -> float | None:
    networks = stats.get("networks")
    if not isinstance(networks, dict) or not networks:
        return None
    return sum(_number(one, field) or 0.0 for one in networks.values())


def _block(stats: dict[str, Any], op: str) -> float | None:
    rows = (stats.get("blkio_stats") or {}).get("io_service_bytes_recursive")
    if not isinstance(rows, list):
        return None
    return sum(
        _number(row, "value") or 0.0
        for row in rows
        if isinstance(row, dict) and str(row.get("op", "")).lower() == op
    )


def container_samples(label: str, stats: dict[str, Any]) -> list[MetricSample]:
    found: list[MetricSample] = []

    def add(field: str, value: float | None, unit: str = "", counter: bool = False) -> None:
        if value is not None:
            found.append(
                MetricSample("container", field, value, label=label, unit=unit, counter=counter)
            )

    add("cpu", cpu_percent(stats), "%")
    add("memory", memory_used(stats), "B")
    limit = _number(stats.get("memory_stats"), "limit")
    used = memory_used(stats)
    if limit and used is not None:
        add("memory_percent", used / limit * 100.0, "%")
    add("network_in", _network(stats, "rx_bytes"), "B", counter=True)
    add("network_out", _network(stats, "tx_bytes"), "B", counter=True)
    add("disk_read", _block(stats, "read"), "B", counter=True)
    add("disk_write", _block(stats, "write"), "B", counter=True)
    add("processes", _number(stats.get("pids_stats"), "current"))
    return found


async def samples(session: DockerSession) -> list[MetricSample]:
    containers = (await read_containers(session)).items
    counts = {"running": 0, "paused": 0, "stopped": 0}
    for container in containers:
        state = str(container.get("State") or "")
        counts[state if state in ("running", "paused") else "stopped"] += 1
    running = sorted(
        (one for one in containers if one.get("State") == "running"), key=name_of
    )
    measured, skipped = running[:POLLED], running[POLLED:]
    found = [
        MetricSample("engine", "containers_" + state, float(count))
        for state, count in counts.items()
    ]
    found.append(MetricSample("engine", "skipped", float(len(skipped))))

    async def one(container: dict[str, Any]) -> list[MetricSample]:
        try:
            _, stats = await session.get(
                f"/containers/{segment(str(container.get('Id')))}/stats",
                {"stream": "false"},
                node_id="container",
                seconds=_STATS_SECONDS,
            )
        except (NodeNotFound, AdapterError):
            # Gone or stopped between the list and its stats: not a failure
            # of the poll, one container fewer in it.
            return []
        return container_samples(name_of(container), stats) if isinstance(stats, dict) else []

    for part in await asyncio.gather(*(one(container) for container in measured)):
        found.extend(part)
    return found


PRESETS: tuple[MetricPreset, ...] = (
    MetricPreset(
        key="docker-containers",
        name=N_("Docker containers"),
        description=N_(
            "CPU, memory, network and disk of each running container, and how "
            "many are running, paused and stopped; the first fifty running "
            "containers by name."
        ),
        recipes=(
            MetricRecipe("timeseries", N_("CPU by container"), (0, 0, 6, 5), "container", ("cpu",)),
            MetricRecipe(
                "timeseries", N_("Memory by container"), (6, 0, 6, 5), "container", ("memory",)
            ),
            MetricRecipe(
                "timeseries",
                N_("Network by container"),
                (0, 5, 6, 5),
                "container",
                ("network_in", "network_out"),
            ),
            MetricRecipe(
                "timeseries",
                N_("Disk by container"),
                (6, 5, 6, 5),
                "container",
                ("disk_read", "disk_write"),
            ),
            MetricRecipe(
                "stat", N_("Running containers"), (0, 10, 3, 4), "engine", ("containers_running",)
            ),
            MetricRecipe(
                "stat", N_("Stopped containers"), (3, 10, 3, 4), "engine", ("containers_stopped",)
            ),
            MetricRecipe(
                "stat", N_("Containers not measured"), (6, 10, 3, 4), "engine", ("skipped",)
            ),
        ),
    ),
)
