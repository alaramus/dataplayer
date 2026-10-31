"""What a MongoDB server reports about itself, for dashboards (D128, D293).

`serverStatus` for the server — connections, operations by kind, documents
by what was done to them, memory, network, cache — and `dbStats` for the size
of the database the connection names, or of every database not the server's
own when it names none. Two commands per poll; nothing is written.
"""

from collections.abc import Mapping
from typing import Any

from app.adapters.metrics import MetricPreset, MetricRecipe, MetricSample
from app.adapters.mongodb.catalog import SYSTEM_DATABASES
from app.adapters.mongodb.session import MongodbSession
from app.core.translation import N_

# (path in serverStatus, metric, field, unit, counter, label).
_READINGS: tuple[tuple[tuple[str, ...], str, str, str, bool, str], ...] = (
    (("connections", "current"), "sessions", "connections", "", False, ""),
    (("connections", "active"), "sessions", "active", "", False, ""),
    (("opcounters", "query"), "operations", "query", "", True, ""),
    (("opcounters", "insert"), "operations", "insert", "", True, ""),
    (("opcounters", "update"), "operations", "update", "", True, ""),
    (("opcounters", "delete"), "operations", "delete", "", True, ""),
    (("opcounters", "getmore"), "operations", "getmore", "", True, ""),
    (("opcounters", "command"), "operations", "command", "", True, ""),
    (("metrics", "document", "returned"), "documents", "returned", "", True, ""),
    (("metrics", "document", "inserted"), "documents", "inserted", "", True, ""),
    (("metrics", "document", "updated"), "documents", "updated", "", True, ""),
    (("metrics", "document", "deleted"), "documents", "deleted", "", True, ""),
    (("mem", "resident"), "memory", "resident", "MiB", False, ""),
    (("network", "bytesIn"), "traffic", "received", "B", True, ""),
    (("network", "bytesOut"), "traffic", "sent", "B", True, ""),
    (("wiredTiger", "cache", "bytes currently in the cache"), "cache", "used", "B", False, ""),
    (("asserts", "user"), "problems", "user_asserts", "", True, ""),
)


def _at(document: Mapping[str, Any], path: tuple[str, ...]) -> float | None:
    found: Any = document
    for step in path:
        if not isinstance(found, Mapping) or step not in found:
            return None
        found = found[step]
    if isinstance(found, bool) or not isinstance(found, int | float):
        return None
    return float(found)


class MongodbMetrics:
    def __init__(self, session: MongodbSession) -> None:
        self._session = session

    async def metric_samples(self) -> list[MetricSample]:
        own = self._session.database()
        async with self._session.client() as client:
            with self._session.failures():
                status = await client.admin.command("serverStatus")
                if own:
                    databases = [own]
                else:
                    listed = await client.admin.command(
                        "listDatabases", nameOnly=True, authorizedDatabases=True
                    )
                    databases = [
                        str(entry["name"])
                        for entry in listed.get("databases", [])
                        if str(entry["name"]) not in SYSTEM_DATABASES
                    ]
                sizes = [await client[name].command("dbStats") for name in databases]
        samples = [
            MetricSample(metric, field, value, label=label, unit=unit, counter=counter)
            for path, metric, field, unit, counter, label in _READINGS
            if (value := _at(status, path)) is not None
        ]
        stored = [_at(stats, ("storageSize",)) for stats in sizes]
        indexes = [_at(stats, ("indexSize",)) for stats in sizes]
        documents = [_at(stats, ("objects",)) for stats in sizes]
        samples.append(MetricSample("database", "size", sum(value or 0.0 for value in stored), unit="B"))
        samples.append(MetricSample("database", "indexes", sum(value or 0.0 for value in indexes), unit="B"))
        samples.append(MetricSample("database", "documents", sum(value or 0.0 for value in documents)))
        return samples


PRESETS: tuple[MetricPreset, ...] = (
    MetricPreset(
        key="mongodb-server",
        name=N_("MongoDB server"),
        description=N_(
            "Connections, operations, documents read and written, memory, cache, "
            "network and size of a MongoDB server."
        ),
        recipes=(
            MetricRecipe("timeseries", N_("Connections"), (0, 0, 6, 5), "sessions"),
            MetricRecipe("timeseries", N_("Operations per second"), (6, 0, 6, 5), "operations"),
            MetricRecipe("timeseries", N_("Documents per second"), (0, 5, 6, 5), "documents"),
            MetricRecipe("timeseries", N_("Cache in use"), (6, 5, 6, 5), "cache", ("used",)),
            MetricRecipe("timeseries", N_("Network traffic"), (0, 10, 6, 5), "traffic"),
            MetricRecipe("stat", N_("Database size"), (6, 10, 3, 5), "database", ("size",)),
            MetricRecipe("stat", N_("Documents"), (9, 10, 3, 5), "database", ("documents",)),
        ),
    ),
)
