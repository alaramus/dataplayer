-- The demonstration schema for a database that holds TimescaleDB, in place of
-- the ordinary one: a server somebody started for the extension should open on
-- hypertables, chunks and policies rather than on a schema that says nothing
-- about any of them.
--
-- Re-runnable: it owns demo_lab and drops it first, exactly as the ordinary
-- schema does.
BEGIN;

DROP SCHEMA IF EXISTS demo_lab CASCADE;
CREATE SCHEMA demo_lab;
SET search_path = demo_lab, public;

CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE sensor_kind AS ENUM ('temperature', 'humidity', 'pressure', 'power');
CREATE TYPE alert_severity AS ENUM ('info', 'warning', 'critical');
CREATE DOMAIN celsius AS double precision CHECK (VALUE BETWEEN -90 AND 90);

-- Ordinary tables: what the readings are about, and what a reference between
-- two nodes looks like on the screens that draw them.

CREATE TABLE sites (
    site_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code citext NOT NULL UNIQUE,
    name text NOT NULL,
    country char(2) NOT NULL,
    timezone_name name NOT NULL DEFAULT 'UTC',
    opened_on date NOT NULL,
    labels text[] NOT NULL DEFAULT '{}'
);
COMMENT ON TABLE sites IS 'Places the sensors stand in.';

CREATE TABLE meters (
    meter_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id integer NOT NULL REFERENCES sites,
    serial citext NOT NULL UNIQUE,
    installed_on date NOT NULL,
    tariff numeric(8, 4) NOT NULL
);
COMMENT ON TABLE meters IS 'Electricity meters, one or more to a site.';

CREATE TABLE sensors (
    sensor_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id integer NOT NULL REFERENCES sites,
    public_id uuid NOT NULL DEFAULT gen_random_uuid(),
    kind sensor_kind NOT NULL,
    unit text NOT NULL,
    installed_on date NOT NULL,
    settings jsonb NOT NULL DEFAULT '{}'::jsonb
);
COMMENT ON TABLE sensors IS 'What is being read, and where it stands.';

CREATE TABLE calibrations (
    calibration_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sensor_id integer NOT NULL REFERENCES sensors,
    calibrated_at timestamptz NOT NULL,
    offset_applied double precision NOT NULL,
    engineer text NOT NULL
);
COMMENT ON TABLE calibrations IS 'Every time a sensor was adjusted.';

CREATE TABLE maintenance_visits (
    visit_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id integer NOT NULL REFERENCES sites,
    visited_on date NOT NULL,
    engineer text NOT NULL,
    notes text
);
COMMENT ON TABLE maintenance_visits IS 'Who went where, and what they found.';

CREATE TABLE alert_rules (
    rule_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sensor_id integer NOT NULL REFERENCES sensors,
    severity alert_severity NOT NULL,
    above celsius,
    below celsius,
    window_length interval NOT NULL DEFAULT INTERVAL '15 minutes'
);
COMMENT ON TABLE alert_rules IS 'When a reading is worth saying something about.';

INSERT INTO sites (code, name, country, timezone_name, opened_on, labels)
VALUES ('north-yard', 'North Yard', 'PL', 'Europe/Warsaw', '2021-03-14', '{outdoor,primary}'),
       ('south-hall', 'South Hall', 'PL', 'Europe/Warsaw', '2022-07-01', '{indoor}'),
       ('harbour', 'Harbour Depot', 'DE', 'Europe/Berlin', '2023-01-20', '{outdoor,cold}'),
       ('lab', 'Calibration Lab', 'DE', 'Europe/Berlin', '2024-11-05', '{indoor,reference}');

INSERT INTO meters (site_id, serial, installed_on, tariff)
SELECT site.site_id, format('MTR-%s-%s', upper(site.code::text), n), site.opened_on + n, 0.1834 + n * 0.02
FROM sites AS site, generate_series(1, 2) AS n;

INSERT INTO sensors (site_id, kind, unit, installed_on, settings)
SELECT site.site_id, kind.kind, kind.unit, site.opened_on + 7,
       jsonb_build_object('sampling', '1 minute', 'retain', '90 days')
FROM sites AS site
JOIN (VALUES ('temperature'::sensor_kind, 'C'),
             ('humidity'::sensor_kind, '%'),
             ('power'::sensor_kind, 'kW')) AS kind(kind, unit) ON true;

INSERT INTO calibrations (sensor_id, calibrated_at, offset_applied, engineer)
SELECT sensor.sensor_id, now() - (n || ' months')::interval,
       round((random() * 2 - 1)::numeric, 3), 'A. Kowalska'
FROM sensors AS sensor, generate_series(1, 2) AS n;

INSERT INTO maintenance_visits (site_id, visited_on, engineer, notes)
SELECT site.site_id, current_date - (n * 30), 'J. Weber',
       CASE WHEN n = 1 THEN 'Filters replaced.' ELSE NULL END
FROM sites AS site, generate_series(1, 3) AS n;

INSERT INTO alert_rules (sensor_id, severity, above, below)
SELECT sensor.sensor_id,
       CASE WHEN sensor.kind = 'temperature' THEN 'critical'::alert_severity
            ELSE 'warning'::alert_severity END,
       CASE WHEN sensor.kind = 'temperature' THEN 31 ELSE NULL END,
       CASE WHEN sensor.kind = 'temperature' THEN 4 ELSE NULL END
FROM sensors AS sensor
WHERE sensor.kind IN ('temperature', 'power');

-- The hypertables: a fortnight of readings a chunk a day, and a second one
-- with nothing compressed and no policy on it, so both states are on screen.

CREATE TABLE sensor_readings (
    observed_at timestamptz NOT NULL,
    sensor_id integer NOT NULL,
    reading double precision NOT NULL,
    status text NOT NULL
);
COMMENT ON TABLE sensor_readings IS 'A fortnight of readings, a chunk a day, the oldest compressed.';

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
-- The policy that acts on this comes later: every job is attached once the
-- demonstration is built, or one of them runs against it while it is being
-- written and the two collide over the same chunk or the same window.
ALTER TABLE sensor_readings SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'sensor_id',
    timescaledb.compress_orderby = 'observed_at'
);

CREATE TABLE device_events (
    occurred_at timestamptz NOT NULL,
    sensor_id integer NOT NULL,
    severity alert_severity NOT NULL,
    code text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb
);
COMMENT ON TABLE device_events IS 'A hypertable with nothing compressed and no policy on it.';

SELECT create_hypertable('demo_lab.device_events', 'occurred_at',
                         chunk_time_interval => INTERVAL '2 days');

INSERT INTO device_events (occurred_at, sensor_id, severity, code, payload)
SELECT stamp,
       1 + (extract(epoch FROM stamp)::bigint % 3),
       (ARRAY['info', 'info', 'warning', 'critical']::alert_severity[])[
           1 + (extract(epoch FROM stamp)::bigint % 4)],
       (ARRAY['heartbeat', 'reconnect', 'threshold', 'battery'])[
           1 + (extract(epoch FROM stamp)::bigint % 4)],
       jsonb_build_object('firmware', '2.4.1', 'retries', extract(epoch FROM stamp)::bigint % 5)
FROM generate_series(now() - INTERVAL '14 days', now(), INTERVAL '10 minutes') AS stamp;

-- WITH NO DATA, because filling one refreshes it, and a refresh ends its own
-- transaction: the file that follows this one does that outside of any.
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
COMMENT ON VIEW readings_hourly IS 'An hour of readings per sensor, kept up by a policy.';

CREATE MATERIALIZED VIEW events_daily WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '1 day', occurred_at) AS bucket,
       severity,
       count(*) AS events
FROM device_events
GROUP BY bucket, severity
WITH NO DATA;
COMMENT ON VIEW events_daily IS 'A day of events per severity, with no policy behind it.';

-- Empty tables with a time column, which is exactly what this source converts:
-- the action turns an ordinary table into a hypertable, and only while there is
-- nothing in it yet. One of each shape it accepts - a key that carries the time
-- column, no key at all, and a date rather than a timestamp.

CREATE TABLE energy_meter_ticks (
    observed_at timestamptz NOT NULL,
    meter_id integer NOT NULL REFERENCES meters,
    kwh numeric(12, 3) NOT NULL,
    tariff numeric(8, 4)
);
-- The key has to carry the column the table would be divided by, so it is
-- written that way round: a key on the meter alone would refuse the conversion.
ALTER TABLE energy_meter_ticks ADD PRIMARY KEY (observed_at, meter_id);
COMMENT ON TABLE energy_meter_ticks IS 'Empty: turn it into a hypertable on observed_at.';

CREATE TABLE weather_observations (
    observed_at timestamptz NOT NULL,
    station citext NOT NULL,
    temperature celsius,
    humidity double precision,
    wind_speed double precision,
    conditions text
);
COMMENT ON TABLE weather_observations IS 'Empty: turn it into a hypertable on observed_at.';

CREATE TABLE trade_ticks (
    traded_at timestamptz NOT NULL,
    symbol text NOT NULL,
    price numeric(14, 4) NOT NULL,
    volume bigint NOT NULL,
    venue text
);
COMMENT ON TABLE trade_ticks IS 'Empty: turn it into a hypertable on traded_at.';

CREATE TABLE daily_totals (
    day date NOT NULL,
    site_id integer NOT NULL,
    readings bigint NOT NULL,
    energy numeric(14, 3) NOT NULL,
    PRIMARY KEY (day, site_id)
);
COMMENT ON TABLE daily_totals IS 'Empty, and dated by the day: a conversion here takes whole days or weeks.';

COMMIT;
