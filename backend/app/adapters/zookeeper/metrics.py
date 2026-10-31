"""What a ZooKeeper server reports about itself (D128, D301): one `mntr` per poll."""

from app.adapters.metrics import MetricPreset, MetricRecipe, MetricSample
from app.adapters.zookeeper.reports import ask, refused
from app.adapters.zookeeper.session import ZookeeperSession
from app.core.translation import N_

# (metric, field, key, unit, counter)
_FIELDS: tuple[tuple[str, str, str, str, bool], ...] = (
    ("connections", "alive", "zk_num_alive_connections", "", False),
    ("requests", "outstanding", "zk_outstanding_requests", "", False),
    ("latency", "min", "zk_min_latency", "ms", False),
    ("latency", "avg", "zk_avg_latency", "ms", False),
    ("latency", "max", "zk_max_latency", "ms", False),
    ("packets", "received", "zk_packets_received", "", True),
    ("packets", "sent", "zk_packets_sent", "", True),
    ("znodes", "count", "zk_znode_count", "", False),
    ("znodes", "ephemeral", "zk_ephemerals_count", "", False),
    ("watches", "count", "zk_watch_count", "", False),
    ("data", "size", "zk_approximate_data_size", "B", False),
    ("files", "open", "zk_open_file_descriptor_count", "", False),
)


def samples_of(answer: str) -> list[MetricSample]:
    values: dict[str, str] = {}
    for line in answer.splitlines():
        name, sign, value = line.partition("\t")
        if sign:
            values[name.strip()] = value.strip()
    samples: list[MetricSample] = []
    for metric, field, key, unit, counter in _FIELDS:
        try:
            number = float(values[key])
        except (KeyError, ValueError):
            continue
        samples.append(MetricSample(metric, field, number, unit=unit, counter=counter))
    return samples


class ZookeeperMetrics:
    def __init__(self, session: ZookeeperSession) -> None:
        self._session = session

    async def metric_samples(self) -> list[MetricSample]:
        """Nothing at all from a server whose whitelist leaves `mntr` out."""
        answer = await self._session.run(lambda client: ask(client, "mntr"))
        return [] if refused(answer) else samples_of(answer)


PRESETS: tuple[MetricPreset, ...] = (
    MetricPreset(
        key="zookeeper-server",
        name=N_("ZooKeeper server"),
        description=N_("Connections, latency, requests, znodes and watches of one server."),
        recipes=(
            MetricRecipe("timeseries", N_("Packets per second"), (0, 0, 8, 5), "packets"),
            MetricRecipe("stat", N_("Znodes"), (8, 0, 4, 5), "znodes", ("count",)),
            MetricRecipe("timeseries", N_("Latency"), (0, 5, 6, 5), "latency"),
            MetricRecipe("timeseries", N_("Connections"), (6, 5, 6, 5), "connections"),
            MetricRecipe("timeseries", N_("Outstanding requests"), (0, 10, 6, 5), "requests"),
            MetricRecipe("timeseries", N_("Watches"), (6, 10, 6, 5), "watches"),
        ),
    ),
)
