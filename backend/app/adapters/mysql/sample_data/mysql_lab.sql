-- A small lab of organizations, people, projects and their work, for a
-- MySQL or MariaDB server this application started. It owns the database
-- demo_lab and drops it first, so running it twice is running it once.
--
-- One statement per paragraph, each ending with a semicolon at the end of a
-- line: the installer splits on that and nothing else, so no body below holds
-- a semicolon of its own.

DROP DATABASE IF EXISTS demo_lab;

CREATE DATABASE demo_lab CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE demo_lab;

CREATE TABLE organizations (
  organization_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  slug VARCHAR(40) NOT NULL,
  display_name VARCHAR(120) NOT NULL,
  legal_name VARCHAR(160) NULL,
  founded_on DATE NOT NULL,
  plan ENUM('free', 'team', 'enterprise') NOT NULL DEFAULT 'free',
  features SET('audit', 'sso', 'analytics', 'export') NOT NULL DEFAULT '',
  settings JSON NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY organizations_slug (slug),
  CONSTRAINT organizations_slug_shape CHECK (slug NOT LIKE '% %')
) COMMENT 'Customers of the lab, one row each';

CREATE TABLE offices (
  office_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  organization_id INT UNSIGNED NOT NULL,
  city VARCHAR(80) NOT NULL,
  country CHAR(2) NOT NULL,
  location POINT NOT NULL,
  opened TIME NULL COMMENT 'When the doors open',
  SPATIAL KEY offices_location (location),
  CONSTRAINT offices_organization FOREIGN KEY (organization_id)
    REFERENCES organizations (organization_id) ON DELETE CASCADE
);

CREATE TABLE app_users (
  user_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  organization_id INT UNSIGNED NOT NULL,
  email VARCHAR(160) NOT NULL,
  full_name VARCHAR(120) NOT NULL,
  initials CHAR(2) GENERATED ALWAYS AS (UPPER(CONCAT(LEFT(full_name, 1), LEFT(SUBSTRING_INDEX(full_name, ' ', -1), 1)))) VIRTUAL,
  reputation SMALLINT NOT NULL DEFAULT 0,
  completion_ratio FLOAT NULL,
  satisfaction DOUBLE NULL,
  is_admin BIT(1) NOT NULL DEFAULT b'0',
  avatar VARBINARY(64) NULL,
  profile JSON NULL,
  UNIQUE KEY app_users_email (organization_id, email),
  CONSTRAINT app_users_organization FOREIGN KEY (organization_id)
    REFERENCES organizations (organization_id) ON DELETE CASCADE,
  CONSTRAINT app_users_reputation CHECK (reputation BETWEEN 0 AND 100)
);

CREATE TABLE teams (
  team_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  organization_id INT UNSIGNED NOT NULL,
  name VARCHAR(80) NOT NULL,
  budget DECIMAL(14, 2) NOT NULL DEFAULT 0,
  UNIQUE KEY teams_name (organization_id, name),
  CONSTRAINT teams_organization FOREIGN KEY (organization_id)
    REFERENCES organizations (organization_id) ON DELETE CASCADE,
  CONSTRAINT teams_budget CHECK (budget >= 0)
);

CREATE TABLE team_members (
  team_id INT UNSIGNED NOT NULL,
  user_id INT UNSIGNED NOT NULL,
  role ENUM('member', 'lead') NOT NULL DEFAULT 'member',
  joined_on DATE NOT NULL,
  PRIMARY KEY (team_id, user_id),
  CONSTRAINT team_members_team FOREIGN KEY (team_id) REFERENCES teams (team_id) ON DELETE CASCADE,
  CONSTRAINT team_members_user FOREIGN KEY (user_id) REFERENCES app_users (user_id) ON DELETE CASCADE
);

CREATE TABLE projects (
  project_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  team_id INT UNSIGNED NOT NULL,
  code VARCHAR(12) NOT NULL,
  title VARCHAR(160) NOT NULL,
  starts_on DATE NOT NULL,
  ends_on DATE NULL,
  budget DECIMAL(14, 2) NULL,
  UNIQUE KEY projects_code (code),
  CONSTRAINT projects_team FOREIGN KEY (team_id) REFERENCES teams (team_id) ON DELETE RESTRICT,
  CONSTRAINT projects_dates CHECK (ends_on IS NULL OR ends_on >= starts_on)
);

CREATE TABLE tasks (
  task_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  project_id INT UNSIGNED NOT NULL,
  assignee_id INT UNSIGNED NULL,
  title VARCHAR(200) NOT NULL,
  body TEXT NULL,
  status ENUM('backlog', 'active', 'blocked', 'done', 'archived') NOT NULL DEFAULT 'backlog',
  priority ENUM('low', 'normal', 'high', 'critical') NOT NULL DEFAULT 'normal',
  estimate_hours DECIMAL(6, 2) NULL,
  spent_hours DECIMAL(6, 2) NOT NULL DEFAULT 0,
  overrun DECIMAL(7, 2) GENERATED ALWAYS AS (spent_hours - COALESCE(estimate_hours, 0)) STORED,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  due_at DATETIME NULL,
  KEY tasks_due (project_id, due_at),
  KEY tasks_title_prefix (title(12)),
  FULLTEXT KEY tasks_text (title, body),
  CONSTRAINT tasks_project FOREIGN KEY (project_id) REFERENCES projects (project_id) ON DELETE CASCADE,
  CONSTRAINT tasks_assignee FOREIGN KEY (assignee_id) REFERENCES app_users (user_id) ON DELETE SET NULL
);

CREATE TABLE tags (
  tag_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(40) NOT NULL,
  color CHAR(7) NOT NULL DEFAULT '#888888',
  UNIQUE KEY tags_name (name)
);

CREATE TABLE task_tags (
  task_id INT UNSIGNED NOT NULL,
  tag_id INT UNSIGNED NOT NULL,
  PRIMARY KEY (task_id, tag_id),
  CONSTRAINT task_tags_task FOREIGN KEY (task_id) REFERENCES tasks (task_id) ON DELETE CASCADE,
  CONSTRAINT task_tags_tag FOREIGN KEY (tag_id) REFERENCES tags (tag_id) ON DELETE CASCADE
);

CREATE TABLE task_dependencies (
  task_id INT UNSIGNED NOT NULL,
  depends_on INT UNSIGNED NOT NULL,
  PRIMARY KEY (task_id, depends_on),
  CONSTRAINT task_dependencies_task FOREIGN KEY (task_id) REFERENCES tasks (task_id) ON DELETE CASCADE,
  CONSTRAINT task_dependencies_on FOREIGN KEY (depends_on) REFERENCES tasks (task_id) ON DELETE CASCADE,
  CONSTRAINT task_dependencies_not_self CHECK (task_id <> depends_on)
);

CREATE TABLE measurements (
  organization_id INT UNSIGNED NOT NULL,
  metric_name VARCHAR(40) NOT NULL,
  measured_at DATETIME NOT NULL,
  value DOUBLE NOT NULL,
  PRIMARY KEY (organization_id, metric_name, measured_at)
) COMMENT 'Partitioned by year, so it has no foreign key'
PARTITION BY RANGE (YEAR(measured_at)) (
  PARTITION measurements_2025 VALUES LESS THAN (2026),
  PARTITION measurements_2026 VALUES LESS THAN (2027),
  PARTITION measurements_later VALUES LESS THAN MAXVALUE
);

CREATE TABLE audit_events (
  event_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  organization_id INT UNSIGNED NOT NULL,
  actor_id INT UNSIGNED NULL,
  action VARCHAR(40) NOT NULL,
  payload JSON NOT NULL,
  happened_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY audit_events_when (organization_id, happened_at),
  CONSTRAINT audit_events_organization FOREIGN KEY (organization_id)
    REFERENCES organizations (organization_id) ON DELETE CASCADE,
  CONSTRAINT audit_events_actor FOREIGN KEY (actor_id) REFERENCES app_users (user_id) ON DELETE SET NULL
);

CREATE TABLE documents (
  document_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  project_id INT UNSIGNED NOT NULL,
  file_name VARCHAR(160) NOT NULL,
  media_type VARCHAR(80) NOT NULL,
  content MEDIUMBLOB NOT NULL,
  checksum BINARY(16) GENERATED ALWAYS AS (UNHEX(MD5(content))) STORED,
  CONSTRAINT documents_project FOREIGN KEY (project_id) REFERENCES projects (project_id) ON DELETE CASCADE
);

CREATE TABLE import_log (
  imported_at DATETIME NOT NULL,
  source VARCHAR(40) NOT NULL,
  note VARCHAR(200) NULL
) COMMENT 'No key at all: its rows are named by their values';

CREATE VIEW project_rollup AS
SELECT p.project_id, p.code, p.title, t.name AS team,
       COUNT(k.task_id) AS tasks,
       SUM(k.status = 'done') AS done,
       SUM(k.spent_hours) AS spent_hours
FROM projects p
JOIN teams t ON t.team_id = p.team_id
LEFT JOIN tasks k ON k.project_id = p.project_id
GROUP BY p.project_id, p.code, p.title, t.name;

CREATE FUNCTION task_age_days(created DATETIME) RETURNS INT DETERMINISTIC
RETURN DATEDIFF('2026-10-01', created);

CREATE TRIGGER tasks_trim_title BEFORE INSERT ON tasks
FOR EACH ROW SET NEW.title = TRIM(NEW.title);

INSERT INTO organizations (slug, display_name, legal_name, founded_on, plan, features, settings)
VALUES
  ('northstar-labs', 'Northstar Labs', 'Northstar Labs LLC', '2018-04-12', 'enterprise', 'audit,sso,analytics',
   '{"region": "eu", "retention_days": 365, "features": ["audit", "sso", "analytics"]}'),
  ('blue-orbit', 'Blue Orbit', NULL, '2021-09-01', 'team', 'analytics',
   '{"region": "eu", "retention_days": 90}'),
  ('quiet-harbor', 'Quiet Harbor', 'Quiet Harbor Ltd', '2015-02-20', 'free', '', NULL);

INSERT INTO offices (organization_id, city, country, location, opened)
VALUES
  (1, 'Kyiv', 'UA', ST_GeomFromText('POINT(30.5234 50.4501)'), '09:00:00'),
  (1, 'Lviv', 'UA', ST_GeomFromText('POINT(24.0297 49.8397)'), '08:30:00'),
  (2, 'Gdansk', 'PL', ST_GeomFromText('POINT(18.6466 54.3520)'), '10:00:00'),
  (3, 'Porto', 'PT', ST_GeomFromText('POINT(-8.6291 41.1579)'), NULL);

INSERT INTO app_users (organization_id, email, full_name, reputation, completion_ratio, satisfaction, is_admin, avatar, profile)
VALUES
  (1, 'ana@example.test', 'Ana Kovalenko', 92, 0.91, 4.8, b'1', X'89504E470D0A1A0A', '{"role": "architect", "timezone": "Europe/Kyiv"}'),
  (1, 'boris@example.test', 'Boris Novak', 67, 0.74, 4.1, b'0', NULL, '{"role": "engineer", "timezone": "Europe/Warsaw"}'),
  (1, 'dana@example.test', 'Dana Melnyk', 75, 0.88, 4.4, b'0', NULL, '{"role": "analyst"}'),
  (2, 'chen@example.test', 'Chen Wei', 81, 0.86, 4.6, b'1', NULL, '{"role": "manager", "timezone": "Asia/Shanghai"}'),
  (2, 'eva@example.test', 'Eva Lindqvist', 58, NULL, NULL, b'0', NULL, NULL),
  (3, 'filipe@example.test', 'Filipe Costa', 40, 0.5, 3.9, b'1', NULL, '{"role": "owner"}');

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

INSERT INTO tasks (project_id, assignee_id, title, body, status, priority, estimate_hours, spent_hours, created_at, due_at)
WITH RECURSIVE n (i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 240)
SELECT 1 + (i % 5),
       CASE WHEN i % 7 = 0 THEN NULL ELSE 1 + (i % 6) END,
       CONCAT('  ', ELT(1 + (i % 6), 'Fix', 'Add', 'Review', 'Measure', 'Document', 'Remove'), ' ',
              ELT(1 + (i % 8), 'login flow', 'export', 'billing report', 'search index', 'audit trail',
                  'cache layer', 'onboarding', 'API limits'), ' #', i),
       CASE WHEN i % 4 = 0 THEN NULL ELSE CONCAT('Raised during review ', 1 + (i % 12), '. Touches the ',
            ELT(1 + (i % 3), 'backend', 'frontend', 'database'), ' and needs a test.') END,
       ELT(1 + ((i DIV 5) % 5), 'backlog', 'active', 'blocked', 'done', 'archived'),
       ELT(1 + (i % 4), 'low', 'normal', 'high', 'critical'),
       CASE WHEN i % 3 = 0 THEN NULL ELSE 2 + (i % 13) END,
       (i * 7 % 40) / 2,
       TIMESTAMP('2025-01-06 09:00:00') + INTERVAL i * 31 HOUR + INTERVAL (i * 137 % 1000) * 1000 MICROSECOND,
       CASE WHEN i % 5 = 3 THEN NULL ELSE TIMESTAMP('2025-02-01 18:00:00') + INTERVAL i * 2 DAY END
FROM n;

INSERT INTO task_tags (task_id, tag_id)
SELECT task_id, 1 + (task_id % 5) FROM tasks
UNION ALL
SELECT task_id, 1 + ((task_id + 2) % 5) FROM tasks WHERE task_id % 3 = 0;

INSERT INTO task_dependencies (task_id, depends_on)
SELECT task_id, task_id - 5 FROM tasks WHERE task_id > 5 AND task_id % 4 = 1;

INSERT INTO measurements (organization_id, metric_name, measured_at, value)
WITH RECURSIVE d (i) AS (SELECT 0 UNION ALL SELECT i + 1 FROM d WHERE i < 179)
SELECT o.organization_id, m.metric_name,
       TIMESTAMP('2025-12-01') + INTERVAL d.i DAY,
       ROUND(m.base + o.organization_id * 3 + 10 * SIN(d.i / 7) + (d.i * 17 % 11) / 3, 3)
FROM d
CROSS JOIN organizations o
CROSS JOIN (SELECT 'active_users' AS metric_name, 120 AS base UNION ALL SELECT 'api_latency_ms', 45) AS m;

INSERT INTO audit_events (organization_id, actor_id, action, payload, happened_at)
WITH RECURSIVE n (i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 60)
SELECT 1 + (i % 3), CASE WHEN i % 9 = 0 THEN NULL ELSE 1 + (i % 6) END,
       ELT(1 + (i % 4), 'sign_in', 'export', 'settings.change', 'task.close'),
       JSON_OBJECT('ip', CONCAT('10.20.', i % 8, '.', 10 + i), 'ok', i % 5 <> 0, 'attempt', i),
       TIMESTAMP('2026-03-01 08:00:00') + INTERVAL i * 97 MINUTE
FROM n;

INSERT INTO documents (project_id, file_name, media_type, content)
VALUES
  (1, 'architecture.md', 'text/markdown', CONVERT('# Core platform\n\nServices talk over one queue.' USING utf8mb4)),
  (3, 'schema.sql', 'application/sql', CONVERT('CREATE TABLE lake_events (id BIGINT PRIMARY KEY)' USING utf8mb4)),
  (4, 'logo.png', 'image/png', X'89504E470D0A1A0A0000000D49484452');

INSERT INTO import_log (imported_at, source, note)
VALUES
  ('2026-04-01 02:00:00', 'crm', 'nightly'),
  ('2026-04-01 02:00:00', 'crm', 'nightly'),
  ('2026-04-02 02:00:00', 'crm', NULL),
  ('2026-04-02 02:05:00', 'billing', 'retried once');
