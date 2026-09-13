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
    # Compression, rollups and restarts (DB5). Widths and retentions are the
    # tiers `history.py` reads by; a test holds the two together.
    Migration(
        version=2,
        statements=(
            # Chunks older than a day, compressed: an agent reporting 62 series
            # every 30 s was measured fifteen times smaller.
            """
            ALTER TABLE metric_point SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'series_id',
                timescaledb.compress_orderby = 'ts DESC'
            )
            """,
            """
            SELECT add_compression_policy(
                'metric_point', INTERVAL '1 day', if_not_exists => TRUE
            )
            """,
            """
            ALTER TABLE metric_process SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'source_id, host',
                timescaledb.compress_orderby = 'ts DESC'
            )
            """,
            """
            SELECT add_compression_policy(
                'metric_process', INTERVAL '1 day', if_not_exists => TRUE
            )
            """,
            # A sum and a count rather than an average, so a wider bucket read
            # from a rollup is an exact mean and not a mean of means.
            #
            # Trap: a refresh whose window reaches back past what raw retention
            # has dropped deletes the rollup of that time. Policy windows are
            # hours to days, under the week raw points are kept, and raw
            # retention is shortened by a step of its own, so running this
            # step again never backfills from a store already trimmed.
            """
            CREATE MATERIALIZED VIEW IF NOT EXISTS metric_point_5m
            WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
            SELECT series_id, time_bucket(INTERVAL '5 minutes', ts) AS bucket,
                   sum(value) AS total, count(*) AS samples,
                   min(value) AS low, max(value) AS high
            FROM metric_point
            GROUP BY series_id, bucket
            WITH NO DATA
            """,
            """
            CREATE INDEX IF NOT EXISTS metric_point_5m_series_bucket
            ON metric_point_5m (series_id, bucket DESC)
            """,
            """
            SELECT add_continuous_aggregate_policy('metric_point_5m',
                start_offset => INTERVAL '6 hours',
                end_offset => INTERVAL '5 minutes',
                schedule_interval => INTERVAL '5 minutes',
                if_not_exists => TRUE)
            """,
            # What the store already holds, once.
            "CALL refresh_continuous_aggregate('metric_point_5m', NULL, now() - INTERVAL '5 minutes')",
            "ALTER MATERIALIZED VIEW metric_point_5m SET (timescaledb.compress = true)",
            """
            SELECT add_compression_policy('metric_point_5m',
                compress_after => INTERVAL '2 days', if_not_exists => TRUE)
            """,
            """
            SELECT add_retention_policy('metric_point_5m', INTERVAL '35 days', if_not_exists => TRUE)
            """,
            """
            CREATE MATERIALIZED VIEW IF NOT EXISTS metric_point_1h
            WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
            SELECT series_id, time_bucket(INTERVAL '1 hour', ts) AS bucket,
                   sum(value) AS total, count(*) AS samples,
                   min(value) AS low, max(value) AS high
            FROM metric_point
            GROUP BY series_id, bucket
            WITH NO DATA
            """,
            """
            CREATE INDEX IF NOT EXISTS metric_point_1h_series_bucket
            ON metric_point_1h (series_id, bucket DESC)
            """,
            """
            SELECT add_continuous_aggregate_policy('metric_point_1h',
                start_offset => INTERVAL '3 days',
                end_offset => INTERVAL '1 hour',
                schedule_interval => INTERVAL '1 hour',
                if_not_exists => TRUE)
            """,
            # What the store already holds, once.
            "CALL refresh_continuous_aggregate('metric_point_1h', NULL, now() - INTERVAL '1 hour')",
            "ALTER MATERIALIZED VIEW metric_point_1h SET (timescaledb.compress = true)",
            """
            SELECT add_compression_policy('metric_point_1h',
                compress_after => INTERVAL '24 days', if_not_exists => TRUE)
            """,
            """
            SELECT add_retention_policy('metric_point_1h', INTERVAL '400 days', if_not_exists => TRUE)
            """,
            # Restarts the collector read from an agent's data (D130).
            """
            CREATE TABLE IF NOT EXISTS metric_restart (
                source_id uuid NOT NULL,
                host text NOT NULL,
                ts timestamptz NOT NULL,
                cause text NOT NULL,
                actions text NOT NULL DEFAULT ''
            )
            """,
            """
            SELECT create_hypertable(
                'metric_restart', 'ts',
                chunk_time_interval => INTERVAL '7 days',
                if_not_exists => TRUE
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS metric_restart_source_ts
            ON metric_restart (source_id, ts DESC)
            """,
            """
            SELECT add_retention_policy(
                'metric_restart', INTERVAL '14 days', if_not_exists => TRUE
            )
            """,
        ),
    ),
    # Raw points for a week, now that the rollups hold what is older.
    Migration(
        version=3,
        statements=(
            "SELECT remove_retention_policy('metric_point', if_exists => TRUE)",
            """
            SELECT add_retention_policy(
                'metric_point', INTERVAL '7 days', if_not_exists => TRUE
            )
            """,
        ),
    ),
)
