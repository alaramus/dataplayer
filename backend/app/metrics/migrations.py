"""The schema of the metrics store, as numbered steps (D126).

Not Alembic: Alembic owns the application database, and this store is another
database, set up at runtime. Every statement is idempotent and runs in
autocommit, because some of Timescale's cannot run inside a transaction block
(a continuous aggregate) and because a step interrupted halfway is simply run
again. The version is recorded once all of a step's statements have run.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Migration:
    version: int
    statements: tuple[str, ...]


VERSION_TABLE = """
CREATE TABLE IF NOT EXISTS metrics_schema_version (
    version integer PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
)
"""

# Held while migrating, so the web process and the metrics process starting
# together do not run the same step twice at once.
ADVISORY_LOCK_KEY = 7_301_125_126

MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=1,
        statements=(
            "CREATE EXTENSION IF NOT EXISTS timescaledb",
            """
            CREATE TABLE IF NOT EXISTS metric_series (
                id bigserial PRIMARY KEY,
                source_kind text NOT NULL CHECK (source_kind IN ('agent', 'connector')),
                source_id uuid NOT NULL,
                host text NOT NULL,
                metric text NOT NULL,
                field text NOT NULL,
                label text NOT NULL,
                unit text NOT NULL,
                first_seen timestamptz NOT NULL,
                last_seen timestamptz NOT NULL
            )
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS metric_series_identity
            ON metric_series (source_kind, source_id, host, metric, field, label)
            """,
            """
            CREATE TABLE IF NOT EXISTS metric_point (
                series_id bigint NOT NULL,
                ts timestamptz NOT NULL,
                value double precision NOT NULL
            )
            """,
            # The pre-2.13 signature on purpose: an existing store may be an
            # older release than the template's.
            """
            SELECT create_hypertable(
                'metric_point', 'ts',
                chunk_time_interval => INTERVAL '1 day',
                if_not_exists => TRUE
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS metric_point_series_ts
            ON metric_point (series_id, ts DESC)
            """,
            """
            SELECT add_retention_policy(
                'metric_point', INTERVAL '30 days', if_not_exists => TRUE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS metric_process (
                source_id uuid NOT NULL,
                host text NOT NULL,
                ts timestamptz NOT NULL,
                pid integer NOT NULL,
                ppid integer NOT NULL,
                username text NOT NULL,
                command text NOT NULL,
                pcpu real NOT NULL,
                pmem real NOT NULL,
                elapsed text NOT NULL
            )
            """,
            """
            SELECT create_hypertable(
                'metric_process', 'ts',
                chunk_time_interval => INTERVAL '1 day',
                if_not_exists => TRUE
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS metric_process_source_host_ts
            ON metric_process (source_id, host, ts DESC)
            """,
            """
            SELECT add_retention_policy(
                'metric_process', INTERVAL '14 days', if_not_exists => TRUE
            )
            """,
        ),
    ),
)
