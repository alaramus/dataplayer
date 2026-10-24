-- A small lab of organizations, people, projects and their work, as a SQLite
-- file in a person's storage (D261). The same lab the PostgreSQL and MySQL
-- samples describe, told in what SQLite has: STRICT and WITHOUT ROWID tables,
-- AUTOINCREMENT, generated columns, checks, foreign keys, a partial index,
-- JSON kept as text, blobs, a view, a trigger, a full-text table and a table
-- with no key. Written into a new file, so it never meets an older one.

PRAGMA foreign_keys = ON;

CREATE TABLE organizations (
  organization_id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  legal_name TEXT,
  founded_on DATE NOT NULL,
  plan TEXT NOT NULL DEFAULT 'free' CHECK (plan IN ('free', 'team', 'enterprise')),
  settings JSON,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT organizations_slug_shape CHECK (slug NOT LIKE '% %')
);

CREATE TABLE app_users (
  user_id INTEGER PRIMARY KEY,
  organization_id INTEGER NOT NULL
    CONSTRAINT app_users_organization REFERENCES organizations ON DELETE CASCADE,
  email TEXT NOT NULL COLLATE NOCASE,
  full_name TEXT NOT NULL,
  initials TEXT GENERATED ALWAYS AS (
    upper(substr(full_name, 1, 1) || substr(full_name, instr(full_name, ' ') + 1, 1))
  ) VIRTUAL,
  reputation INTEGER NOT NULL DEFAULT 0,
  completion_ratio REAL,
  is_admin BOOLEAN NOT NULL DEFAULT 0,
  avatar BLOB,
  profile JSON CHECK (profile IS NULL OR json_valid(profile)),
  UNIQUE (organization_id, email),
  CONSTRAINT app_users_reputation CHECK (reputation BETWEEN 0 AND 100)
);

CREATE TABLE teams (
  team_id INTEGER PRIMARY KEY,
  organization_id INTEGER NOT NULL REFERENCES organizations ON DELETE CASCADE,
  name TEXT NOT NULL,
  budget NUMERIC(14, 2) NOT NULL DEFAULT 0,
  UNIQUE (organization_id, name),
  CONSTRAINT teams_budget CHECK (budget >= 0)
);

CREATE TABLE team_members (
  team_id INTEGER NOT NULL REFERENCES teams ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES app_users ON DELETE CASCADE,
  role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('member', 'lead')),
  joined_on DATE NOT NULL,
  PRIMARY KEY (team_id, user_id)
) WITHOUT ROWID;

CREATE TABLE projects (
  project_id INTEGER PRIMARY KEY,
  team_id INTEGER NOT NULL CONSTRAINT projects_team REFERENCES teams ON DELETE RESTRICT,
  code TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  starts_on DATE NOT NULL,
  ends_on DATE,
  budget NUMERIC(14, 2),
  CONSTRAINT projects_dates CHECK (ends_on IS NULL OR ends_on >= starts_on)
);

CREATE TABLE tasks (
  task_id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects ON DELETE CASCADE,
  assignee_id INTEGER REFERENCES app_users ON DELETE SET NULL,
  title TEXT NOT NULL,
  body TEXT,
  status TEXT NOT NULL DEFAULT 'backlog'
    CHECK (status IN ('backlog', 'active', 'blocked', 'done', 'archived')),
  priority TEXT NOT NULL DEFAULT 'normal' CHECK (priority IN ('low', 'normal', 'high', 'critical')),
  estimate_hours REAL,
  spent_hours REAL NOT NULL DEFAULT 0,
  overrun REAL GENERATED ALWAYS AS (spent_hours - coalesce(estimate_hours, 0)) STORED,
  created_at TEXT NOT NULL,
  due_at TEXT
) STRICT;

CREATE INDEX tasks_due ON tasks (project_id, due_at);
CREATE INDEX tasks_open ON tasks (priority, due_at) WHERE status IN ('backlog', 'active', 'blocked');

CREATE TABLE tags (
  tag_id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  color TEXT NOT NULL DEFAULT '#888888' CHECK (length(color) = 7)
);

CREATE TABLE task_tags (
  task_id INTEGER NOT NULL REFERENCES tasks ON DELETE CASCADE,
  tag_id INTEGER NOT NULL REFERENCES tags ON DELETE CASCADE,
  PRIMARY KEY (task_id, tag_id)
) WITHOUT ROWID;

CREATE TABLE task_dependencies (
  task_id INTEGER NOT NULL REFERENCES tasks ON DELETE CASCADE,
  depends_on INTEGER NOT NULL REFERENCES tasks ON DELETE CASCADE,
  PRIMARY KEY (task_id, depends_on),
  CONSTRAINT task_dependencies_not_self CHECK (task_id <> depends_on)
);

CREATE TABLE measurements (
  organization_id INTEGER NOT NULL REFERENCES organizations ON DELETE CASCADE,
  metric_name TEXT NOT NULL,
  measured_at DATE NOT NULL,
  value REAL NOT NULL,
  PRIMARY KEY (organization_id, metric_name, measured_at)
);

CREATE TABLE audit_events (
  event_id INTEGER PRIMARY KEY,
  organization_id INTEGER NOT NULL REFERENCES organizations ON DELETE CASCADE,
  actor_id INTEGER REFERENCES app_users ON DELETE SET NULL,
  action TEXT NOT NULL,
  payload JSON NOT NULL,
  happened_at DATETIME NOT NULL
);

CREATE INDEX audit_events_when ON audit_events (organization_id, happened_at);

CREATE TABLE documents (
  document_id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects ON DELETE CASCADE,
  file_name TEXT NOT NULL,
  media_type TEXT NOT NULL,
  content BLOB NOT NULL,
  size INTEGER GENERATED ALWAYS AS (length(content)) STORED
);

-- No key at all: its rows are named by their rowid.
CREATE TABLE import_log (
  imported_at DATETIME NOT NULL,
  source TEXT NOT NULL,
  note TEXT
);

CREATE VIEW project_rollup AS
SELECT p.project_id, p.code, p.title, t.name AS team,
       count(k.task_id) AS tasks,
       sum(k.status = 'done') AS done,
       sum(k.spent_hours) AS spent_hours
FROM projects AS p
JOIN teams AS t ON t.team_id = p.team_id
LEFT JOIN tasks AS k ON k.project_id = p.project_id
GROUP BY p.project_id, p.code, p.title, t.name;

CREATE TRIGGER tasks_trim_title AFTER INSERT ON tasks
WHEN NEW.title <> trim(NEW.title)
BEGIN
  UPDATE tasks SET title = trim(NEW.title) WHERE task_id = NEW.task_id;
END;

CREATE VIRTUAL TABLE task_search USING fts5(title, body);

INSERT INTO organizations (slug, display_name, legal_name, founded_on, plan, settings)
VALUES
  ('northstar-labs', 'Northstar Labs', 'Northstar Labs LLC', '2018-04-12', 'enterprise',
   '{"region": "eu", "retention_days": 365, "features": ["audit", "sso", "analytics"]}'),
  ('blue-orbit', 'Blue Orbit', NULL, '2021-09-01', 'team', '{"region": "eu", "retention_days": 90}'),
  ('quiet-harbor', 'Quiet Harbor', 'Quiet Harbor Ltd', '2015-02-20', 'free', NULL);

INSERT INTO app_users (organization_id, email, full_name, reputation, completion_ratio, is_admin, avatar, profile)
VALUES
  (1, 'ana@example.test', 'Ana Kovalenko', 92, 0.91, 1, x'89504E470D0A1A0A', '{"role": "architect", "timezone": "Europe/Kyiv"}'),
  (1, 'boris@example.test', 'Boris Novak', 67, 0.74, 0, NULL, '{"role": "engineer", "timezone": "Europe/Warsaw"}'),
  (1, 'dana@example.test', 'Dana Melnyk', 75, 0.88, 0, NULL, '{"role": "analyst"}'),
  (2, 'chen@example.test', 'Chen Wei', 81, 0.86, 1, NULL, '{"role": "manager", "timezone": "Asia/Shanghai"}'),
  (2, 'eva@example.test', 'Eva Lindqvist', 58, NULL, 0, NULL, NULL),
  (3, 'filipe@example.test', 'Filipe Costa', 40, 0.5, 1, NULL, '{"role": "owner"}');

INSERT INTO teams (organization_id, name, budget)
VALUES (1, 'Platform', 250000.00), (1, 'Data', 180000.00), (2, 'Delivery', 90000.00), (3, 'Everything', 15000.00);

INSERT INTO team_members (team_id, user_id, role, joined_on)
VALUES (1, 1, 'lead', '2019-01-07'), (1, 2, 'member', '2020-03-02'), (2, 3, 'lead', '2021-06-14'),
       (2, 1, 'member', '2021-06-14'), (3, 4, 'lead', '2021-09-01'), (3, 5, 'member', '2022-01-10'),
       (4, 6, 'lead', '2015-02-20');

INSERT INTO projects (team_id, code, title, starts_on, ends_on, budget)
VALUES
  (1, 'PLT-CORE', 'Core platform rewrite', '2025-01-06', NULL, 120000.00),
  (1, 'PLT-OBS', 'Observability', '2025-05-12', '2026-03-31', 40000.00),
  (2, 'DAT-LAKE', 'Lakehouse migration', '2025-02-03', NULL, 90000.00),
  (3, 'DEL-PORT', 'Customer portal', '2025-09-15', '2026-06-30', 55000.00),
  (4, 'EVR-SITE', 'New website', '2026-01-05', NULL, NULL);

INSERT INTO tags (name, color)
VALUES ('bug', '#d73a4a'), ('feature', '#0e8a16'), ('debt', '#fbca04'), ('security', '#b60205'), ('docs', '#0075ca');

WITH RECURSIVE
  n (i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 240),
  verbs (k, word) AS (VALUES (0, 'Fix'), (1, 'Add'), (2, 'Review'), (3, 'Measure'), (4, 'Document'), (5, 'Remove')),
  things (k, word) AS (VALUES (0, 'login flow'), (1, 'export'), (2, 'billing report'), (3, 'search index'),
                              (4, 'audit trail'), (5, 'cache layer'), (6, 'onboarding'), (7, 'API limits')),
  parts (k, word) AS (VALUES (0, 'backend'), (1, 'frontend'), (2, 'database')),
  states (k, word) AS (VALUES (0, 'backlog'), (1, 'active'), (2, 'blocked'), (3, 'done'), (4, 'archived')),
  priorities (k, word) AS (VALUES (0, 'low'), (1, 'normal'), (2, 'high'), (3, 'critical'))
INSERT INTO tasks (project_id, assignee_id, title, body, status, priority, estimate_hours, spent_hours, created_at, due_at)
SELECT 1 + (i % 5),
       CASE WHEN i % 7 = 0 THEN NULL ELSE 1 + (i % 6) END,
       '  ' || v.word || ' ' || t.word || ' #' || i,
       CASE WHEN i % 4 = 0 THEN NULL
            ELSE 'Raised during review ' || (1 + (i % 12)) || '. Touches the ' || p.word || ' and needs a test.' END,
       s.word,
       r.word,
       CASE WHEN i % 3 = 0 THEN NULL ELSE 2.0 + (i % 13) END,
       (i * 7 % 40) / 2.0,
       strftime('%Y-%m-%d %H:%M:%f', '2025-01-06 09:00:00', '+' || (i * 31) || ' hours', '+' || (i * 137 % 1000) || ' seconds'),
       CASE WHEN i % 5 = 3 THEN NULL ELSE datetime('2025-02-01 18:00:00', '+' || (i * 2) || ' days') END
FROM n
JOIN verbs AS v ON v.k = i % 6
JOIN things AS t ON t.k = i % 8
JOIN parts AS p ON p.k = i % 3
JOIN states AS s ON s.k = (i / 5) % 5
JOIN priorities AS r ON r.k = i % 4
ORDER BY i;

INSERT INTO task_search (rowid, title, body) SELECT task_id, title, body FROM tasks;

INSERT INTO task_tags (task_id, tag_id)
SELECT task_id, 1 + (task_id % 5) FROM tasks
UNION
SELECT task_id, 1 + ((task_id + 2) % 5) FROM tasks WHERE task_id % 3 = 0;

INSERT INTO task_dependencies (task_id, depends_on)
SELECT task_id, task_id - 5 FROM tasks WHERE task_id > 5 AND task_id % 4 = 1;

WITH RECURSIVE d (i) AS (SELECT 0 UNION ALL SELECT i + 1 FROM d WHERE i < 179)
INSERT INTO measurements (organization_id, metric_name, measured_at, value)
SELECT o.organization_id, m.metric_name,
       date('2025-12-01', '+' || d.i || ' days'),
       round(m.base + o.organization_id * 3 + 10 * sin(d.i / 7.0) + (d.i * 17 % 11) / 3.0, 3)
FROM d
CROSS JOIN organizations AS o
CROSS JOIN (SELECT 'active_users' AS metric_name, 120 AS base UNION ALL SELECT 'api_latency_ms', 45) AS m;

WITH RECURSIVE
  n (i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 60),
  actions (k, word) AS (VALUES (0, 'sign_in'), (1, 'export'), (2, 'settings.change'), (3, 'task.close'))
INSERT INTO audit_events (organization_id, actor_id, action, payload, happened_at)
SELECT 1 + (i % 3), CASE WHEN i % 9 = 0 THEN NULL ELSE 1 + (i % 6) END,
       a.word,
       json_object('ip', '10.20.' || (i % 8) || '.' || (10 + i), 'ok', json(CASE WHEN i % 5 <> 0 THEN 'true' ELSE 'false' END), 'attempt', i),
       datetime('2026-03-01 08:00:00', '+' || (i * 97) || ' minutes')
FROM n JOIN actions AS a ON a.k = i % 4
ORDER BY i;

INSERT INTO documents (project_id, file_name, media_type, content)
VALUES
  (1, 'architecture.md', 'text/markdown', CAST('# Core platform' || char(10) || char(10) || 'Services talk over one queue.' AS BLOB)),
  (3, 'schema.sql', 'application/sql', CAST('CREATE TABLE lake_events (id BIGINT PRIMARY KEY)' AS BLOB)),
  (4, 'logo.png', 'image/png', x'89504E470D0A1A0A0000000D49484452');

INSERT INTO import_log (imported_at, source, note)
VALUES
  ('2026-04-01 02:00:00', 'crm', 'nightly'),
  ('2026-04-01 02:00:00', 'crm', 'nightly'),
  ('2026-04-02 02:00:00', 'crm', NULL),
  ('2026-04-02 02:05:00', 'billing', 'retried once');

ANALYZE;
