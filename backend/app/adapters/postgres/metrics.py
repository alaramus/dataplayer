"""What a PostgreSQL database reports about itself (D128).

Two catalog reads per poll, both of the database the connection names:
`pg_stat_database` for its counters and `pg_stat_activity` for its sessions.
Nothing is written and nothing outside the database is asked.
"""

from app.adapters.metrics import MetricPreset, MetricRecipe, MetricSample
from app.adapters.postgres.session import PostgresSession
from app.core.translation import N_

_DATABASE_SQL = """
SELECT numbackends, xact_commit, xact_rollback, blks_read, blks_hit,
       tup_returned, tup_fetched, tup_inserted, tup_updated, tup_deleted,
       conflicts, deadlocks, temp_bytes, pg_database_size(datname) AS size
FROM pg_catalog.pg_stat_database
WHERE datname = current_database()
"""

_SESSIONS_SQL = """
SELECT coalesce(state, 'background') AS state, count(*) AS sessions
FROM pg_catalog.pg_stat_activity
WHERE datname = current_database()
GROUP BY 1
"""

# The label of the series that counts every session: a key of the stored
# series, which a dashboard shows as it is, rather than a word.
_TOTAL = "total"

# (metric, field, column, unit, counter)
_COLUMNS: tuple[tuple[str, str, str, str, bool], ...] = (
    ("transactions", "commits", "xact_commit", "", True),
    ("transactions", "rollbacks", "xact_rollback", "", True),
    ("blocks", "read", "blks_read", "", True),
    ("blocks", "hit", "blks_hit", "", True),
    ("tuples", "returned", "tup_returned", "", True),
    ("tuples", "fetched", "tup_fetched", "", True),
    ("tuples", "inserted", "tup_inserted", "", True),
    ("tuples", "updated", "tup_updated", "", True),
    ("tuples", "deleted", "tup_deleted", "", True),
    ("problems", "conflicts", "conflicts", "", True),
    ("problems", "deadlocks", "deadlocks", "", True),
    ("database", "temp_bytes", "temp_bytes", "B", True),
    ("database", "size", "size", "B", False),
)


class PostgresMetrics:
    def __init__(self, session: PostgresSession) -> None:
        self._session = session

    async def metric_samples(self) -> list[MetricSample]:
        samples: list[MetricSample] = []
        rows = await self._session.query(_DATABASE_SQL, inspection=True)
        if rows:
            row = rows[0]
            for metric, field, column, unit, counter in _COLUMNS:
                value = row.get(column)
                if isinstance(value, int | float):
                    samples.append(
                        MetricSample(metric, field, float(value), unit=unit, counter=counter)
                    )
        sessions = await self._session.query(_SESSIONS_SQL, inspection=True)
        # Written for an empty answer too: a gap reads as "nobody asked".
        samples.append(
            MetricSample("sessions", "count", float(sum(int(one["sessions"]) for one in sessions)), label=_TOTAL)
        )
        for one in sessions:
            samples.append(
                MetricSample("sessions", "count", float(one["sessions"]), label=str(one["state"]))
            )
        return samples


PRESETS: tuple[MetricPreset, ...] = (
    MetricPreset(
        key="postgres-database",
        name=N_("PostgreSQL database"),
        description=N_("Sessions, transactions, tuple traffic, block I/O and size of one database."),
        recipes=(
            MetricRecipe("timeseries", N_("Sessions by state"), (0, 0, 6, 5), "sessions", ("count",)),
            MetricRecipe("timeseries", N_("Transactions per second"), (6, 0, 6, 5), "transactions"),
            MetricRecipe("timeseries", N_("Tuples read per second"), (0, 5, 6, 5), "tuples", ("returned", "fetched")),
            MetricRecipe(
                "timeseries", N_("Tuples written per second"), (6, 5, 6, 5), "tuples", ("inserted", "updated", "deleted")
            ),
            MetricRecipe("timeseries", N_("Blocks per second"), (0, 10, 6, 5), "blocks"),
            MetricRecipe("stat", N_("Database size"), (6, 10, 3, 5), "database", ("size",)),
            MetricRecipe("timeseries", N_("Conflicts and deadlocks"), (9, 10, 3, 5), "problems"),
        ),
    ),
)
