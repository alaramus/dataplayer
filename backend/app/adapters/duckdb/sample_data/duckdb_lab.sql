-- A small lab of organizations, people, projects and their work, as a DuckDB
-- file in a person's storage (D402). The same lab the PostgreSQL, MySQL and
-- SQLite samples describe, told in what DuckDB has: an enum, a struct, a list,
-- a map, HUGEINT, TIMESTAMPTZ, intervals, JSON, a blob, sequences behind
-- identities, a virtual generated column, checks, foreign keys, an index, a
-- view, a macro, a second schema and a table with no key. Written into a new
-- file, so it never meets an older one.

CREATE TYPE plan_kind AS ENUM ('free', 'team', 'enterprise');
CREATE TYPE task_status AS ENUM ('backlog', 'active', 'blocked', 'done', 'archived');

CREATE SEQUENCE organizations_organization_id_seq;
CREATE SEQUENCE tasks_task_id_seq;

CREATE TABLE organizations (
  organization_id BIGINT PRIMARY KEY DEFAULT nextval('organizations_organization_id_seq'),
  slug VARCHAR NOT NULL UNIQUE CHECK (slug NOT LIKE '% %'),
  display_name VARCHAR NOT NULL,
  legal_name VARCHAR,
  founded_on DATE NOT NULL,
  plan plan_kind NOT NULL DEFAULT 'free',
  settings JSON,
  created_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp
);
COMMENT ON TABLE organizations IS 'Who uses the lab';

CREATE TABLE app_users (
  user_id INTEGER PRIMARY KEY,
  organization_id BIGINT NOT NULL REFERENCES organizations (organization_id),
  email VARCHAR NOT NULL,
  full_name VARCHAR NOT NULL,
  initials VARCHAR GENERATED ALWAYS AS (
    upper(full_name[1] || full_name[strpos(full_name, ' ') + 1])
  ) VIRTUAL,
  reputation INTEGER NOT NULL DEFAULT 0 CHECK (reputation BETWEEN 0 AND 100),
  completion_ratio DOUBLE,
  is_admin BOOLEAN NOT NULL DEFAULT false,
  avatar BLOB,
  profile STRUCT(role VARCHAR, timezone VARCHAR),
  UNIQUE (organization_id, email)
);

CREATE TABLE teams (
  team_id INTEGER PRIMARY KEY,
  organization_id BIGINT NOT NULL REFERENCES organizations (organization_id),
  name VARCHAR NOT NULL,
  budget DECIMAL(14, 2) NOT NULL DEFAULT 0 CHECK (budget >= 0),
  UNIQUE (organization_id, name)
);

CREATE TABLE team_members (
  team_id INTEGER NOT NULL REFERENCES teams (team_id),
  user_id INTEGER NOT NULL REFERENCES app_users (user_id),
  role VARCHAR NOT NULL DEFAULT 'member' CHECK (role IN ('member', 'lead')),
  joined_on DATE NOT NULL,
  PRIMARY KEY (team_id, user_id)
);

CREATE TABLE projects (
  project_id INTEGER PRIMARY KEY,
  team_id INTEGER NOT NULL REFERENCES teams (team_id),
  code VARCHAR NOT NULL UNIQUE,
  title VARCHAR NOT NULL,
  starts_on DATE NOT NULL,
  ends_on DATE,
  budget DECIMAL(14, 2),
  CHECK (ends_on IS NULL OR ends_on >= starts_on)
);

CREATE TABLE tasks (
  task_id BIGINT PRIMARY KEY DEFAULT nextval('tasks_task_id_seq'),
  project_id INTEGER NOT NULL REFERENCES projects (project_id),
  assignee_id INTEGER REFERENCES app_users (user_id),
  title VARCHAR NOT NULL,
  body VARCHAR,
  status task_status NOT NULL DEFAULT 'backlog',
  priority VARCHAR NOT NULL DEFAULT 'normal' CHECK (priority IN ('low', 'normal', 'high', 'critical')),
  tags VARCHAR[] NOT NULL DEFAULT [],
  estimate INTERVAL,
  spent_hours DOUBLE NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL,
  due_at TIMESTAMP
);

CREATE INDEX tasks_due ON tasks (project_id, due_at);

CREATE TABLE measurements (
  organization_id BIGINT NOT NULL REFERENCES organizations (organization_id),
  metric_name VARCHAR NOT NULL,
  measured_on DATE NOT NULL,
  value DOUBLE NOT NULL,
  labels MAP(VARCHAR, VARCHAR),
  PRIMARY KEY (organization_id, metric_name, measured_on)
);

CREATE TABLE ledger (
  entry_id UUID PRIMARY KEY DEFAULT uuid(),
  organization_id BIGINT NOT NULL REFERENCES organizations (organization_id),
  -- Tiny units, so a sum never overflows.
  amount_micros HUGEINT NOT NULL,
  booked_at TIMESTAMPTZ NOT NULL
);

-- No key at all: its rows can be read and added, not changed.
CREATE TABLE import_log (
  imported_at TIMESTAMP NOT NULL,
  source VARCHAR NOT NULL,
  note VARCHAR
);

CREATE VIEW project_rollup AS
SELECT p.project_id, p.code, p.title, t.name AS team,
       count(k.task_id) AS tasks,
       count(k.task_id) FILTER (WHERE k.status = 'done') AS done,
       sum(k.spent_hours) AS spent_hours
FROM projects AS p
JOIN teams AS t ON t.team_id = p.team_id
LEFT JOIN tasks AS k ON k.project_id = p.project_id
GROUP BY ALL;

CREATE MACRO hours(span) AS epoch(span) / 3600;

CREATE SCHEMA archive;
CREATE TABLE archive.closed_projects (
  project_id INTEGER PRIMARY KEY,
  code VARCHAR NOT NULL,
  closed_on DATE NOT NULL,
  summary VARCHAR
);

INSERT INTO organizations (slug, display_name, legal_name, founded_on, plan, settings)
VALUES
  ('northstar-labs', 'Northstar Labs', 'Northstar Labs LLC', '2018-04-12', 'enterprise',
   '{"region": "eu", "retention_days": 365, "features": ["audit", "sso", "analytics"]}'),
  ('blue-orbit', 'Blue Orbit', NULL, '2021-09-01', 'team', '{"region": "eu", "retention_days": 90}'),
  ('quiet-harbor', 'Quiet Harbor', 'Quiet Harbor Ltd', '2015-02-20', 'free', NULL);

INSERT INTO app_users (user_id, organization_id, email, full_name, reputation, completion_ratio, is_admin, avatar, profile)
VALUES
  (1, 1, 'ana@example.test', 'Ana Kovalenko', 92, 0.91, true, '\x89\x50\x4E\x47'::BLOB, {'role': 'architect', 'timezone': 'Europe/Kyiv'}),
  (2, 1, 'boris@example.test', 'Boris Novak', 67, 0.74, false, NULL, {'role': 'engineer', 'timezone': 'Europe/Warsaw'}),
  (3, 1, 'dana@example.test', 'Dana Melnyk', 75, 0.88, false, NULL, {'role': 'analyst', 'timezone': NULL}),
  (4, 2, 'chen@example.test', 'Chen Wei', 81, 0.86, true, NULL, {'role': 'manager', 'timezone': 'Asia/Shanghai'}),
  (5, 2, 'eva@example.test', 'Eva Lindqvist', 58, NULL, false, NULL, NULL),
  (6, 3, 'filipe@example.test', 'Filipe Costa', 40, 0.5, true, NULL, {'role': 'owner', 'timezone': NULL});

INSERT INTO teams VALUES
  (1, 1, 'Platform', 250000.00), (2, 1, 'Data', 180000.00), (3, 2, 'Delivery', 90000.00), (4, 3, 'Everything', 15000.00);

INSERT INTO team_members VALUES
  (1, 1, 'lead', '2019-01-07'), (1, 2, 'member', '2020-03-02'), (2, 3, 'lead', '2021-06-14'),
  (2, 1, 'member', '2021-06-14'), (3, 4, 'lead', '2021-09-01'), (3, 5, 'member', '2022-01-10'),
  (4, 6, 'lead', '2015-02-20');

INSERT INTO projects VALUES
  (1, 1, 'PLT-CORE', 'Core platform rewrite', '2025-01-06', NULL, 120000.00),
  (2, 1, 'PLT-OBS', 'Observability', '2025-05-12', '2026-03-31', 40000.00),
  (3, 2, 'DAT-LAKE', 'Lakehouse migration', '2025-02-03', NULL, 90000.00),
  (4, 3, 'DEL-PORT', 'Customer portal', '2025-09-15', '2026-06-30', 55000.00),
  (5, 4, 'EVR-SITE', 'New website', '2026-01-05', NULL, NULL);

INSERT INTO tasks (project_id, assignee_id, title, body, status, priority, tags, estimate, spent_hours, created_at, due_at)
SELECT 1 + (i % 5),
       CASE WHEN i % 7 = 0 THEN NULL ELSE 1 + (i % 6) END,
       (['Fix', 'Add', 'Review', 'Measure', 'Document', 'Remove'])[1 + i % 6] || ' '
         || (['login flow', 'export', 'billing report', 'search index', 'audit trail', 'cache layer', 'onboarding', 'API limits'])[1 + i % 8]
         || ' #' || i,
       CASE WHEN i % 4 = 0 THEN NULL
            ELSE 'Raised during review ' || (1 + i % 12) || '. Touches the '
              || (['backend', 'frontend', 'database'])[1 + i % 3] || ' and needs a test.' END,
       (['backlog', 'active', 'blocked', 'done', 'archived'])[1 + (i // 5) % 5]::task_status,
       (['low', 'normal', 'high', 'critical'])[1 + i % 4],
       CASE i % 3 WHEN 0 THEN ['bug'] WHEN 1 THEN ['feature', 'docs'] ELSE [] END,
       CASE WHEN i % 3 = 0 THEN NULL ELSE to_hours(2 + i % 13) END,
       (i * 7 % 40) / 2.0,
       TIMESTAMPTZ '2025-01-06 09:00:00+00' + to_hours(i * 31) + to_seconds(i * 137 % 1000),
       CASE WHEN i % 5 = 3 THEN NULL ELSE TIMESTAMP '2025-02-01 18:00:00' + to_days(i * 2) END
FROM range(1, 241) AS n (i)
ORDER BY i;

INSERT INTO measurements
SELECT o.organization_id, m.metric_name, DATE '2025-12-01' + d.i::INTEGER,
       round(m.base + o.organization_id * 3 + 10 * sin(d.i / 7.0) + (d.i * 17 % 11) / 3.0, 3),
       MAP {'source': 'agent', 'window': '1d'}
FROM range(0, 180) AS d (i)
CROSS JOIN organizations AS o
CROSS JOIN (VALUES ('active_users', 120), ('api_latency_ms', 45)) AS m (metric_name, base);

INSERT INTO ledger (organization_id, amount_micros, booked_at)
SELECT 1 + i % 3, (i * 1234567)::HUGEINT * 1000000000, TIMESTAMPTZ '2026-01-01 00:00:00+00' + to_days(i)
FROM range(1, 61) AS n (i);

INSERT INTO import_log VALUES
  ('2026-04-01 02:00:00', 'crm', 'nightly'),
  ('2026-04-01 02:00:00', 'crm', 'nightly'),
  ('2026-04-02 02:00:00', 'crm', NULL),
  ('2026-04-02 02:05:00', 'billing', 'retried once');

INSERT INTO archive.closed_projects VALUES
  (90, 'OLD-CRM', '2024-11-30', 'Replaced by the portal'),
  (91, 'OLD-ETL', '2025-03-15', NULL);
