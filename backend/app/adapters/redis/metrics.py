"""What a Redis server reports about itself (D128): one `INFO` per poll."""

import re

from app.adapters.metrics import MetricPreset, MetricRecipe, MetricSample
from app.adapters.redis.session import RedisSession
from app.core.translation import N_

_DATABASE_SECTION = re.compile(r"^db\d+$")

# (metric, field, key, unit, counter)
_FIELDS: tuple[tuple[str, str, str, str, bool], ...] = (
    ("clients", "connected", "connected_clients", "", False),
    ("clients", "blocked", "blocked_clients", "", False),
    ("memory", "used", "used_memory", "B", False),
    ("memory", "rss", "used_memory_rss", "B", False),
    ("memory", "peak", "used_memory_peak", "B", False),
    ("commands", "processed", "total_commands_processed", "", True),
    ("keyspace", "hits", "keyspace_hits", "", True),
    ("keyspace", "misses", "keyspace_misses", "", True),
    ("keyspace", "expired", "expired_keys", "", True),
    ("keyspace", "evicted", "evicted_keys", "", True),
    ("network", "input", "total_net_input_bytes", "B", True),
    ("network", "output", "total_net_output_bytes", "B", True),
)


class RedisMetrics:
    def __init__(self, session: RedisSession) -> None:
        self._session = session

    async def metric_samples(self) -> list[MetricSample]:
        async with self._session.connection() as client:
            info: dict[str, object] = await client.info()
        samples: list[MetricSample] = []
        for metric, field, key, unit, counter in _FIELDS:
            value = info.get(key)
            if isinstance(value, int | float) and not isinstance(value, bool):
                samples.append(MetricSample(metric, field, float(value), unit=unit, counter=counter))
        for name, section in info.items():
            if not _DATABASE_SECTION.match(name) or not isinstance(section, dict):
                continue
            for field in ("keys", "expires"):
                value = section.get(field)
                if isinstance(value, int):
                    samples.append(MetricSample("databases", field, float(value), label=name))
        return samples


PRESETS: tuple[MetricPreset, ...] = (
    MetricPreset(
        key="redis-server",
        name=N_("Redis server"),
        description=N_("Clients, memory, commands, cache hits and keys of one server."),
        recipes=(
            MetricRecipe("timeseries", N_("Commands per second"), (0, 0, 8, 5), "commands"),
            MetricRecipe("stat", N_("Memory used"), (8, 0, 4, 5), "memory", ("used",)),
            MetricRecipe("timeseries", N_("Memory"), (0, 5, 6, 5), "memory"),
            MetricRecipe("timeseries", N_("Clients"), (6, 5, 6, 5), "clients"),
            MetricRecipe("timeseries", N_("Hits and misses per second"), (0, 10, 6, 5), "keyspace", ("hits", "misses")),
            MetricRecipe("timeseries", N_("Keys per database"), (6, 10, 6, 5), "databases", ("keys",)),
        ),
    ),
)
