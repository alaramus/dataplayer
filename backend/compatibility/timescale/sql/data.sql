SET timezone = 'UTC';
CREATE SCHEMA lab;
CREATE SCHEMA other;

CREATE TABLE public.ordinary (id integer PRIMARY KEY, value text NOT NULL);
INSERT INTO public.ordinary VALUES (1, 'first'), (2, 'second'), (3, 'third');

CREATE TABLE lab.metrics (observed_at timestamptz NOT NULL, value bigint NOT NULL);
SELECT create_hypertable('lab.metrics', 'observed_at', chunk_time_interval => INTERVAL '1 day');
INSERT INTO lab.metrics
SELECT '2026-01-01 00:00:00+00'::timestamptz + n * INTERVAL '1 hour',
       9007199254740993::bigint + n
FROM generate_series(0, 71) AS n;

CREATE TABLE lab.integer_metrics (tick bigint NOT NULL, value text NOT NULL);
SELECT create_hypertable('lab.integer_metrics', 'tick', chunk_time_interval => 1000::bigint);
INSERT INTO lab.integer_metrics
SELECT 9007199254740993::bigint + n * 1000, 'reading-' || n
FROM generate_series(0, 7) AS n;

CREATE TABLE lab.empty_metrics (observed_at timestamptz NOT NULL, value bigint);
SELECT create_hypertable('lab.empty_metrics', 'observed_at', chunk_time_interval => INTERVAL '1 day');

CREATE TABLE other.metrics (observed_at timestamptz NOT NULL, value bigint NOT NULL);
SELECT create_hypertable('other.metrics', 'observed_at', chunk_time_interval => INTERVAL '1 day');
INSERT INTO other.metrics VALUES ('2026-01-01 00:00:00+00', 1), ('2026-01-02 00:00:00+00', 2);

CREATE MATERIALIZED VIEW lab.hourly WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '1 hour', observed_at) AS bucket, count(*) AS readings
FROM lab.metrics GROUP BY 1 WITH NO DATA;
CALL refresh_continuous_aggregate('lab.hourly', NULL, NULL);
SELECT alter_job(add_retention_policy('lab.metrics', INTERVAL '10 years'), scheduled => false);
