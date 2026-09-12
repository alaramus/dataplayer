-- The TimescaleDB part of the demo schema, run only where the extension is
-- installed. It shares demo_lab with postgres_complex_schema.sql, which drops
-- and creates that schema, so the files are one demonstration and running them
-- again is running them once.
--
-- Everything here is a thing one of the Timescale screens is about: a
-- hypertable divided into chunks, compression with a policy behind it, a
-- continuous aggregate with its own refresh policy, and a retention policy.
BEGIN;
SET search_path = demo_lab, public;

CREATE TABLE sensor_readings (
    observed_at timestamptz NOT NULL,
    sensor_id integer NOT NULL,
    reading double precision NOT NULL,
    status text NOT NULL
);

COMMENT ON TABLE sensor_readings IS 'Two weeks of readings from three sensors, a chunk per day.';

-- A day per chunk over a fortnight of data: enough chunks that the list of
-- them says something, and small enough that filling it is seconds.
SELECT create_hypertable('demo_lab.sensor_readings', 'observed_at',
                         chunk_time_interval => INTERVAL '1 day');

INSERT INTO sensor_readings (observed_at, sensor_id, reading, status)
SELECT stamp,
       sensor,
       round((20 + 8 * sin(extract(epoch FROM stamp) / 7200.0 + sensor) + sensor * 0.7)::numeric, 3),
       CASE WHEN random() < 0.02 THEN 'suspect' ELSE 'ok' END
FROM generate_series(now() - INTERVAL '14 days', now(), INTERVAL '1 minute') AS stamp,
     generate_series(1, 3) AS sensor;

-- Compressed by sensor and ordered by time, which is how this table is read.
ALTER TABLE sensor_readings SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'sensor_id',
    timescaledb.compress_orderby = 'observed_at'
);
SELECT add_compression_policy('demo_lab.sensor_readings', INTERVAL '7 days');

-- Longer than the data is old, so the policy is there to be read rather than
-- to take anything away while somebody is looking at it.
SELECT add_retention_policy('demo_lab.sensor_readings', INTERVAL '90 days');

-- WITH NO DATA, because filling it refreshes it, and a refresh ends its own
-- transaction: the file that follows this one does it outside of any.
CREATE MATERIALIZED VIEW readings_hourly WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '1 hour', observed_at) AS bucket,
       sensor_id,
       count(*) AS readings,
       avg(reading) AS average,
       min(reading) AS lowest,
       max(reading) AS highest
FROM sensor_readings
GROUP BY bucket, sensor_id
WITH NO DATA;

SELECT add_continuous_aggregate_policy('demo_lab.readings_hourly',
                                       start_offset => INTERVAL '3 days',
                                       end_offset => INTERVAL '1 hour',
                                       schedule_interval => INTERVAL '1 hour');

COMMIT;
