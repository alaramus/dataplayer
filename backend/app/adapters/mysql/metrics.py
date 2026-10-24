"""What a MySQL server reports about itself, for dashboards (D128, D241).

MySQL keeps its counters for the whole server rather than for a database, so
the preset is of the server; only the size is of the database the connection
names, or of every database not the server's own when it names none. One
`SHOW GLOBAL STATUS`, which every user may run on both servers, and one read
of `information_schema` per poll. Nothing is written.
"""

from app.adapters.metrics import MetricPreset, MetricRecipe, MetricSample
from app.adapters.mysql.catalog import SYSTEM_DATABASES
from app.adapters.mysql.session import MysqlSession
from app.core.translation import N_

# (metric, field, status variables, unit, counter, label). The first variable
# the server has is read: MariaDB keeps no Innodb_rows_*, and counts rows read
# in Rows_read and rows written through its handlers.
_STATUS: tuple[tuple[str, str, tuple[str, ...], str, bool, str], ...] = (
    ("sessions", "count", ("Threads_connected",), "", False, "connected"),
    ("sessions", "count", ("Threads_running",), "", False, "running"),
    ("statements", "select", ("Com_select",), "", True, ""),
    ("statements", "insert", ("Com_insert",), "", True, ""),
    ("statements", "update", ("Com_update",), "", True, ""),
    ("statements", "delete", ("Com_delete",), "", True, ""),
    ("rows", "read", ("Innodb_rows_read", "Rows_read"), "", True, ""),
    ("rows", "inserted", ("Innodb_rows_inserted", "Handler_write"), "", True, ""),
    ("rows", "updated", ("Innodb_rows_updated", "Handler_update"), "", True, ""),
    ("rows", "deleted", ("Innodb_rows_deleted", "Handler_delete"), "", True, ""),
    ("buffer_pool", "requests", ("Innodb_buffer_pool_read_requests",), "", True, ""),
    ("buffer_pool", "disk_reads", ("Innodb_buffer_pool_reads",), "", True, ""),
    ("traffic", "received", ("Bytes_received",), "B", True, ""),
    ("traffic", "sent", ("Bytes_sent",), "B", True, ""),
    ("problems", "slow_queries", ("Slow_queries",), "", True, ""),
    ("problems", "aborted_connects", ("Aborted_connects",), "", True, ""),
    ("problems", "aborted_clients", ("Aborted_clients",), "", True, ""),
)
_VARIABLES = tuple(dict.fromkeys(name for _, _, names, _, _, _ in _STATUS for name in names))

_STATUS_SQL = "SHOW GLOBAL STATUS WHERE Variable_name IN ({})".format(
    ", ".join(["%s"] * len(_VARIABLES))
)

_SIZE_OF = """
    SELECT COALESCE(SUM(DATA_LENGTH + INDEX_LENGTH), 0) AS size
    FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s
"""
_SIZE_OF_ALL = """
    SELECT COALESCE(SUM(DATA_LENGTH + INDEX_LENGTH), 0) AS size
    FROM information_schema.TABLES WHERE TABLE_SCHEMA NOT IN ({})
""".format(", ".join(["%s"] * len(SYSTEM_DATABASES)))  # noqa: S608  # placeholders only; the names are bound


class MysqlMetrics:
    def __init__(self, session: MysqlSession) -> None:
        self._session = session

    async def metric_samples(self) -> list[MetricSample]:
        rows = await self._session.query(_STATUS_SQL, _VARIABLES)
        status = {str(row["Variable_name"]).lower(): row["Value"] for row in rows}
        samples: list[MetricSample] = []
        for metric, field, names, unit, counter, label in _STATUS:
            found = next((status[name.lower()] for name in names if name.lower() in status), None)
            value = _number(found)
            if value is not None:
                samples.append(
                    MetricSample(metric, field, value, label=label, unit=unit, counter=counter)
                )
        database = self._session.database()
        if database:
            sized = await self._session.query(_SIZE_OF, (database,))
        else:
            sized = await self._session.query(_SIZE_OF_ALL, tuple(sorted(SYSTEM_DATABASES)))
        size = _number(sized[0]["size"]) if sized else None
        if size is not None:
            samples.append(MetricSample("database", "size", size, unit="B"))
        return samples


def _number(value: object) -> float | None:
    try:
        return float(str(value))
    except ValueError:
        return None


PRESETS: tuple[MetricPreset, ...] = (
    MetricPreset(
        key="mysql-server",
        name=N_("MySQL server"),
        description=N_(
            "Connections, statements, InnoDB row and buffer pool traffic, network and "
            "size of a MySQL or MariaDB server."
        ),
        recipes=(
            MetricRecipe("timeseries", N_("Connections"), (0, 0, 6, 5), "sessions", ("count",)),
            MetricRecipe("timeseries", N_("Statements per second"), (6, 0, 6, 5), "statements"),
            MetricRecipe("timeseries", N_("Rows per second"), (0, 5, 6, 5), "rows"),
            MetricRecipe("timeseries", N_("Buffer pool reads per second"), (6, 5, 6, 5), "buffer_pool"),
            MetricRecipe("timeseries", N_("Network traffic"), (0, 10, 6, 5), "traffic"),
            MetricRecipe("stat", N_("Database size"), (6, 10, 3, 5), "database", ("size",)),
            MetricRecipe("timeseries", N_("Slow queries and aborted connections"), (9, 10, 3, 5), "problems"),
        ),
    ),
)
