"""What a ClickHouse server reports about itself, for dashboards (D128, D279).

ClickHouse keeps its counters for the whole server, in `system.events`, and
what is happening now in `system.metrics`; only the size and the parts are of
the database the connection names, or of every database not the server's own
when it names none. One read per poll, which every user may make. Nothing is
written.

`system.events` lists only what has happened at least once, so a counter it
does not list is read as nought rather than left out: a dashboard's rate
starts at the first poll, not at the first insert.
"""

from app.adapters.clickhouse.catalog import SYSTEM_DATABASES
from app.adapters.clickhouse.session import ClickhouseSession
from app.adapters.clickhouse.sql import array_of_strings
from app.adapters.metrics import MetricPreset, MetricRecipe, MetricSample
from app.core.translation import N_

# (table, name there, metric, field, unit, counter, label).
_READINGS: tuple[tuple[str, str, str, str, str, bool, str], ...] = (
    ("metrics", "Query", "sessions", "running_queries", "", False, ""),
    ("metrics", "TCPConnection", "sessions", "count", "", False, "native"),
    ("metrics", "HTTPConnection", "sessions", "count", "", False, "http"),
    ("metrics", "MemoryTracking", "memory", "used", "B", False, ""),
    ("events", "SelectQuery", "statements", "select", "", True, ""),
    ("events", "InsertQuery", "statements", "insert", "", True, ""),
    ("events", "FailedQuery", "problems", "failed_queries", "", True, ""),
    ("events", "SelectedRows", "rows", "read", "", True, ""),
    ("events", "InsertedRows", "rows", "inserted", "", True, ""),
    ("events", "MergedRows", "rows", "merged", "", True, ""),
    ("events", "NetworkReceiveBytes", "traffic", "received", "B", True, ""),
    ("events", "NetworkSendBytes", "traffic", "sent", "B", True, ""),
    ("asynchronous_metrics", "MaxPartCountForPartition", "parts", "most_in_a_partition", "", False, ""),
)

_SQL = """
    SELECT 'metrics' AS kept, metric AS called, toFloat64(value) AS reading
    FROM system.metrics WHERE metric IN {metrics:Array(String)}
    UNION ALL
    SELECT 'events', event, toFloat64(value)
    FROM system.events WHERE event IN {events:Array(String)}
    UNION ALL
    SELECT 'asynchronous_metrics', metric, toFloat64(value)
    FROM system.asynchronous_metrics WHERE metric IN {asynchronous_metrics:Array(String)}
    UNION ALL
    SELECT 'parts', 'size', toFloat64(sum(bytes_on_disk))
    FROM system.parts WHERE active AND (
        database = {database:String}
        OR ({database:String} = '' AND database NOT IN {system:Array(String)}))
    UNION ALL
    SELECT 'parts', 'count', toFloat64(count())
    FROM system.parts WHERE active AND (
        database = {database:String}
        OR ({database:String} = '' AND database NOT IN {system:Array(String)}))
"""


class ClickhouseMetrics:
    def __init__(self, session: ClickhouseSession) -> None:
        self._session = session

    async def metric_samples(self) -> list[MetricSample]:
        wanted = {
            kept: array_of_strings([called for table, called, *_ in _READINGS if table == kept])
            for kept in ("metrics", "events", "asynchronous_metrics")
        }
        rows = await self._session.query(
            _SQL,
            {
                **wanted,
                "database": self._session.database(),
                "system": array_of_strings(sorted(SYSTEM_DATABASES)),
            },
        )
        read = {(str(row["kept"]), str(row["called"])): _number(row["reading"]) for row in rows}
        samples: list[MetricSample] = []
        for table, called, metric, field, unit, counter, label in _READINGS:
            value = read.get((table, called), 0.0 if table == "events" else None)
            if value is not None:
                samples.append(MetricSample(metric, field, value, label=label, unit=unit, counter=counter))
        size = read.get(("parts", "size"))
        if size is not None:
            samples.append(MetricSample("database", "size", size, unit="B"))
        parts = read.get(("parts", "count"))
        if parts is not None:
            samples.append(MetricSample("parts", "active", parts))
        return samples


def _number(value: object) -> float | None:
    try:
        return float(str(value))
    except ValueError:
        return None


PRESETS: tuple[MetricPreset, ...] = (
    MetricPreset(
        key="clickhouse-server",
        name=N_("ClickHouse server"),
        description=N_(
            "Queries, connections, rows read, written and merged, memory, network, "
            "parts and size of a ClickHouse server."
        ),
        recipes=(
            MetricRecipe("timeseries", N_("Connections and running queries"), (0, 0, 6, 5), "sessions"),
            MetricRecipe("timeseries", N_("Queries per second"), (6, 0, 6, 5), "statements"),
            MetricRecipe("timeseries", N_("Rows per second"), (0, 5, 6, 5), "rows"),
            MetricRecipe("timeseries", N_("Memory in use"), (6, 5, 6, 5), "memory", ("used",)),
            MetricRecipe("timeseries", N_("Network traffic"), (0, 10, 6, 5), "traffic"),
            MetricRecipe("timeseries", N_("Active parts"), (6, 10, 3, 5), "parts"),
            MetricRecipe("stat", N_("Database size"), (9, 10, 3, 5), "database", ("size",)),
            MetricRecipe("timeseries", N_("Failed queries"), (0, 15, 6, 5), "problems"),
        ),
    ),
)
