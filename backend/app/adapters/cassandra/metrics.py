"""What a Cassandra or ScyllaDB node reports about itself, for dashboards (D128, D353).

Only what CQL answers on the node asked, which every role that can sign in may
read: its clients, and the partitions and bytes it estimates for the
connection's keyspace — or every keyspace not the server's own when it names
none. Cassandra adds its thread pools from `system_views`: requests, reads,
writes and compactions done, as rates, and the work waiting. ScyllaDB keeps
those in its Prometheus endpoint, a port of its own this source does not
reach. Nothing is written.
"""

from typing import Any

from app.adapters.cassandra.inspection import is_system_keyspace
from app.adapters.cassandra.session import CassandraSession
from app.adapters.metrics import MetricPreset, MetricRecipe, MetricSample
from app.core.translation import N_

_SIZES = "SELECT keyspace_name, partitions_count, mean_partition_size FROM system.size_estimates"
_CASSANDRA_CLIENTS = "SELECT address FROM system_views.clients"
_SCYLLA_CLIENTS = "SELECT address FROM system.clients"
_POOLS = "SELECT name, active_tasks, pending_tasks, completed_tasks FROM system_views.thread_pools"

# (pool, field of `statements`) — a pool's completed tasks as a rate.
_DONE = (
    ("Native-Transport-Requests", "requests"),
    ("ReadStage", "reads"),
    ("MutationStage", "writes"),
    ("CompactionExecutor", "compactions"),
)


class CassandraMetrics:
    def __init__(self, session: CassandraSession) -> None:
        self._session = session

    async def _rows(self, statement: str) -> list[dict[str, Any]]:
        return (await self._session.rows(statement, limit=100_000)).dicts()

    async def metric_samples(self) -> list[MetricSample]:
        async with self._session.held():
            return await self._samples()

    async def _samples(self) -> list[MetricSample]:
        profile = await self._session.profile()
        samples: list[MetricSample] = []
        clients = await self._rows(
            _SCYLLA_CLIENTS if profile.scylla else _CASSANDRA_CLIENTS
        )
        samples.append(MetricSample("sessions", "clients", float(len(clients))))

        own = self._session.keyspace()
        partitions = 0
        size = 0
        for row in await self._rows(_SIZES):
            keyspace = str(row["keyspace_name"])
            counted = (
                keyspace == own
                if own
                else not is_system_keyspace(keyspace, scylla=profile.scylla)
            )
            if counted:
                count = int(row["partitions_count"] or 0)
                partitions += count
                size += count * int(row["mean_partition_size"] or 0)
        samples.append(MetricSample("keyspace", "size", float(size), unit="B"))
        samples.append(MetricSample("keyspace", "partitions", float(partitions)))

        if not profile.scylla:
            pools = {str(row["name"]): row for row in await self._rows(_POOLS)}
            for pool, field in _DONE:
                found = pools.get(pool)
                if found is not None:
                    samples.append(
                        MetricSample(
                            "statements",
                            field,
                            float(found["completed_tasks"] or 0),
                            counter=True,
                        )
                    )
            waiting = sum(int(row["pending_tasks"] or 0) for row in pools.values())
            active = sum(int(row["active_tasks"] or 0) for row in pools.values())
            samples.append(MetricSample("tasks", "pending", float(waiting)))
            samples.append(MetricSample("tasks", "active", float(active)))
        return samples


PRESETS: tuple[MetricPreset, ...] = (
    MetricPreset(
        key="cassandra-node",
        name=N_("Cassandra node"),
        description=N_(
            "Clients, requests, reads and writes, waiting work, and the size of "
            "the keyspace on a Cassandra or ScyllaDB node."
        ),
        recipes=(
            MetricRecipe("timeseries", N_("Clients"), (0, 0, 6, 5), "sessions"),
            MetricRecipe(
                "timeseries", N_("Requests per second"), (6, 0, 6, 5), "statements"
            ),
            MetricRecipe(
                "timeseries", N_("Waiting and running work"), (0, 5, 6, 5), "tasks"
            ),
            MetricRecipe(
                "stat", N_("Keyspace size"), (6, 5, 3, 5), "keyspace", ("size",)
            ),
            MetricRecipe(
                "stat", N_("Partitions"), (9, 5, 3, 5), "keyspace", ("partitions",)
            ),
        ),
    ),
)
