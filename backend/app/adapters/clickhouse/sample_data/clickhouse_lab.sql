-- A small lab of organizations, people, projects and their traffic, for a
-- ClickHouse server this application started. It owns the database demo_lab
-- and drops it first, so running it twice is running it once.
--
-- One statement per paragraph, each ending with a semicolon at the end of a
-- line: the installer splits on that and nothing else, so no body below holds
-- a semicolon of its own. Every name is written with its database, since the
-- installer chooses none.

DROP DATABASE IF EXISTS demo_lab SYNC;

CREATE DATABASE demo_lab COMMENT 'The DataPlayer lab';

CREATE TABLE demo_lab.organizations (
  organization_id UInt32,
  slug LowCardinality(String),
  display_name String,
  founded_on Date,
  plan Enum8('free' = 1, 'team' = 2, 'enterprise' = 3) DEFAULT 'free',
  features Array(LowCardinality(String)),
  settings Map(String, String),
  created_at DateTime('UTC') DEFAULT now(),
  CONSTRAINT organizations_slug_shape CHECK NOT match(slug, '\\s')
) ENGINE = MergeTree
ORDER BY organization_id
COMMENT 'Customers of the lab, one row each';

CREATE TABLE demo_lab.app_users (
  user_id UInt32,
  organization_id UInt32,
  email String,
  full_name String,
  reputation Int32 DEFAULT 0,
  satisfaction Nullable(Float32) COMMENT 'From the last survey, when they answered',
  is_admin Bool DEFAULT false,
  last_ip IPv4,
  profile Tuple(theme LowCardinality(String), locale LowCardinality(String)),
  uid UUID DEFAULT generateUUIDv4(),
  email_domain String MATERIALIZED splitByChar('@', email)[2],
  INDEX app_users_email email TYPE bloom_filter GRANULARITY 1
) ENGINE = MergeTree
ORDER BY (organization_id, user_id);

CREATE TABLE demo_lab.projects (
  project_id UInt32,
  organization_id UInt32,
  code FixedString(6),
  title String,
  starts_on Date,
  ends_on Nullable(Date),
  budget Decimal(12, 2)
) ENGINE = MergeTree
ORDER BY project_id;

CREATE TABLE demo_lab.tasks (
  task_id UInt32,
  project_id UInt32,
  assignee_id Nullable(UInt32),
  title String,
  status Enum8('todo' = 1, 'doing' = 2, 'review' = 3, 'done' = 4),
  priority UInt8,
  estimate_hours Decimal(6, 2),
  tags Array(String),
  created_at DateTime64(3, 'UTC'),
  version UInt32
) ENGINE = ReplacingMergeTree(version)
ORDER BY task_id
COMMENT 'Rows with the same task_id are merged into the latest version, sometime';

CREATE TABLE demo_lab.page_views (
  organization_id UInt32,
  user_id UInt32,
  viewed_at DateTime('UTC'),
  path LowCardinality(String),
  duration_ms UInt32 CODEC(T64, ZSTD(1)),
  referrer Nullable(String),
  country FixedString(2),
  INDEX page_views_path path TYPE set(100) GRANULARITY 4
) ENGINE = MergeTree
PARTITION BY toYYYYMM(viewed_at)
ORDER BY (organization_id, viewed_at)
TTL viewed_at + INTERVAL 5 YEAR
COMMENT 'Traffic, one row a page view';

CREATE TABLE demo_lab.daily_views (
  organization_id UInt32,
  day Date,
  views UInt64,
  total_ms UInt64
) ENGINE = SummingMergeTree
ORDER BY (organization_id, day);

CREATE TABLE demo_lab.import_log (
  imported_at DateTime DEFAULT now(),
  source String,
  rows_read UInt64
) ENGINE = Log;

CREATE MATERIALIZED VIEW demo_lab.daily_views_feed TO demo_lab.daily_views AS
SELECT organization_id, toDate(viewed_at) AS day, count() AS views, sum(duration_ms) AS total_ms
FROM demo_lab.page_views
GROUP BY organization_id, day;

CREATE MATERIALIZED VIEW demo_lab.path_totals
ENGINE = SummingMergeTree
ORDER BY path AS
SELECT path, count() AS views, sum(duration_ms) AS total_ms
FROM demo_lab.page_views
GROUP BY path;

CREATE VIEW demo_lab.project_rollup AS
SELECT p.code, p.title, count(t.task_id) AS tasks, countIf(t.status = 'done') AS done,
  sum(t.estimate_hours) AS estimate_hours
FROM demo_lab.projects AS p
LEFT JOIN (SELECT * FROM demo_lab.tasks FINAL) AS t ON t.project_id = p.project_id
GROUP BY p.code, p.title;

INSERT INTO demo_lab.organizations (organization_id, slug, display_name, founded_on, plan, features, settings) VALUES
  (1, 'acme', 'Acme', '2009-03-14', 'enterprise', ['audit', 'sso', 'analytics'], map('region', 'eu', 'retention', '365')),
  (2, 'globex', 'Globex', '2014-07-01', 'team', ['export'], map('region', 'us')),
  (3, 'initech', 'Initech', '2018-11-20', 'free', [], map()),
  (4, 'umbrella', 'Umbrella', '2001-01-05', 'enterprise', ['audit', 'sso'], map('region', 'ap')),
  (5, 'hooli', 'Hooli', '2020-05-30', 'team', ['analytics', 'export'], map('region', 'us', 'beta', 'yes'));

INSERT INTO demo_lab.app_users (user_id, organization_id, email, full_name, reputation, satisfaction, is_admin, last_ip, profile) VALUES
  (1, 1, 'ada@acme.test', 'Ada Lovelace', 980, 4.8, true, '10.0.0.11', ('dark', 'en-GB')),
  (2, 1, 'alan@acme.test', 'Alan Turing', 870, NULL, false, '10.0.0.12', ('light', 'en-GB')),
  (3, 2, 'grace@globex.test', 'Grace Hopper', 910, 4.2, true, '10.0.1.21', ('dark', 'en-US')),
  (4, 2, 'linus@globex.test', 'Linus Torvalds', 640, 3.9, false, '10.0.1.22', ('dark', 'fi-FI')),
  (5, 3, 'margaret@initech.test', 'Margaret Hamilton', 720, 5, true, '10.0.2.31', ('light', 'en-US')),
  (6, 3, 'dennis@initech.test', 'Dennis Ritchie', 500, NULL, false, '10.0.2.32', ('light', 'en-US')),
  (7, 4, 'barbara@umbrella.test', 'Barbara Liskov', 830, 4.5, true, '10.0.3.41', ('dark', 'en-US')),
  (8, 4, 'ken@umbrella.test', 'Ken Thompson', 450, 2.7, false, '10.0.3.42', ('light', 'en-US')),
  (9, 5, 'frances@hooli.test', 'Frances Allen', 690, 4, true, '10.0.4.51', ('dark', 'en-US')),
  (10, 5, 'edsger@hooli.test', 'Edsger Dijkstra', 760, 3.1, false, '10.0.4.52', ('light', 'nl-NL')),
  (11, 1, 'katherine@acme.test', 'Katherine Johnson', 810, 4.9, false, '10.0.0.13', ('dark', 'en-US')),
  (12, 2, 'tim@globex.test', 'Tim Berners-Lee', 600, NULL, false, '10.0.1.23', ('light', 'en-GB'));

INSERT INTO demo_lab.projects (project_id, organization_id, code, title, starts_on, ends_on, budget) VALUES
  (1, 1, 'ACM-01', 'Analytical engine', '2026-01-05', NULL, 120000.00),
  (2, 1, 'ACM-02', 'Bombe restoration', '2025-09-01', '2026-03-31', 45000.50),
  (3, 2, 'GLX-01', 'Compiler', '2026-02-10', NULL, 88000.00),
  (4, 4, 'UMB-01', 'Abstraction layer', '2025-11-15', '2026-06-30', 64000.00),
  (5, 5, 'HOO-01', 'Shortest paths', '2026-04-01', NULL, 30500.75);

INSERT INTO demo_lab.tasks (task_id, project_id, assignee_id, title, status, priority, estimate_hours, tags, created_at, version) VALUES
  (1, 1, 1, 'Design the mill', 'done', 1, 40, ['design'], '2026-01-06 09:00:00.000', 1),
  (2, 1, 2, 'Punch the first cards', 'doing', 2, 16.5, ['cards', 'io'], '2026-01-08 10:30:00.250', 1),
  (3, 1, 11, 'Check the trajectories', 'todo', 1, 12, ['maths'], '2026-02-01 08:15:00.000', 1),
  (4, 2, 2, 'Rewire the drums', 'review', 2, 24, ['hardware'], '2025-09-10 14:00:00.000', 1),
  (5, 3, 3, 'Write the first compiler', 'doing', 1, 80, ['compiler'], '2026-02-11 09:00:00.000', 1),
  (6, 3, 4, 'Keep the kernel small', 'todo', 3, 8, [], '2026-02-12 16:45:00.000', 1),
  (7, 4, 7, 'State the substitution rule', 'done', 1, 6, ['types'], '2025-11-16 11:00:00.000', 1),
  (8, 4, 8, 'Port to a smaller machine', 'todo', 2, 30, ['porting'], '2025-12-01 13:00:00.000', 1),
  (9, 5, 10, 'Find the shortest path', 'doing', 1, 10, ['graphs'], '2026-04-02 09:30:00.000', 1),
  (10, 5, NULL, 'Nobody has this one yet', 'todo', 3, 2.25, [], '2026-04-03 17:00:00.000', 1);

INSERT INTO demo_lab.tasks (task_id, project_id, assignee_id, title, status, priority, estimate_hours, tags, created_at, version) VALUES
  (2, 1, 2, 'Punch the first cards', 'review', 2, 18, ['cards', 'io'], '2026-01-08 10:30:00.250', 2),
  (5, 3, 3, 'Write the first compiler', 'done', 1, 96, ['compiler'], '2026-02-11 09:00:00.000', 2);

INSERT INTO demo_lab.page_views (organization_id, user_id, viewed_at, path, duration_ms, referrer, country)
SELECT
  1 + number % 5,
  1 + number % 12,
  now() - toIntervalSecond(number * 37),
  ['/', '/pricing', '/docs', '/docs/install', '/blog', '/login', '/projects', '/settings'][1 + cityHash64(number) % 8],
  toUInt32(40 + cityHash64(number, 1) % 6000),
  if(number % 3 = 0, NULL, ['search', 'newsletter', 'partner'][1 + cityHash64(number, 2) % 3]),
  ['DE', 'FR', 'US', 'IN', 'CN', 'ES'][1 + cityHash64(number, 3) % 6]
FROM numbers(200000);

INSERT INTO demo_lab.import_log (source, rows_read) VALUES
  ('page_views.csv', 200000),
  ('tasks.json', 12);
