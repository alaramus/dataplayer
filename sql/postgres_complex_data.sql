-- Demo data for postgres_complex_schema.sql.
BEGIN;
SET search_path = demo_lab, public;

INSERT INTO organizations (slug, display_name, legal_name, founded_on, headquarters, service_area, office_network, settings)
VALUES ('northstar-labs', 'Northstar Labs', 'Northstar Labs LLC', '2018-04-12',
        ROW('42 Aurora Avenue', 'Kyiv', '01001', 'UA'), '10.20.0.0/16', '10.20.4.15',
        '{"plan":"enterprise","features":["audit","sso","analytics"]}'),
       ('blue-orbit', 'Blue Orbit', NULL, '2021-09-01',
        ROW('7 Dock Street', 'Gdansk', '80-001', 'PL'), '172.16.0.0/20', '172.16.2.10',
        '{"plan":"team","features":["analytics"]}')
ON CONFLICT (slug) DO NOTHING;

INSERT INTO app_users (organization_id, email, full_name, initials, reputation, completion_ratio,
                       satisfaction, preferred_languages, profile)
SELECT o.organization_id, v.email::citext, v.full_name, v.initials, v.reputation, v.ratio, v.satisfaction,
       v.languages, v.profile::json
FROM organizations o
JOIN (VALUES
    ('northstar-labs', 'ana@example.test', 'Ana Kovalenko', 'AK ', 92::smallint, 0.91::real, 4.8::double precision,
     ARRAY['en','uk']::varchar(8)[], '{"role":"architect","timezone":"Europe/Kyiv"}'),
    ('northstar-labs', 'boris@example.test', 'Boris Novak', 'BN ', 67::smallint, 0.74::real, 4.1::double precision,
     ARRAY['en','pl']::varchar(8)[], '{"role":"engineer","timezone":"Europe/Warsaw"}'),
    ('blue-orbit', 'chen@example.test', 'Chen Wei', 'CW ', 81::smallint, 0.86::real, 4.6::double precision,
     ARRAY['en','zh']::varchar(8)[], '{"role":"manager","timezone":"Asia/Shanghai"}')
) AS v(slug, email, full_name, initials, reputation, ratio, satisfaction, languages, profile)
ON v.slug = o.slug
ON CONFLICT (organization_id, email) DO NOTHING;

INSERT INTO teams (organization_id, name, budget)
SELECT organization_id, 'Platform', 250000.00 FROM organizations WHERE slug = 'northstar-labs'
UNION ALL
SELECT organization_id, 'Research', 125000.00 FROM organizations WHERE slug = 'blue-orbit';

INSERT INTO team_members (team_id, user_id, role_name, allocation)
SELECT t.team_id, u.user_id, v.role_name, v.allocation
FROM (VALUES
    ('northstar-labs', 'Platform', 'ana@example.test', 'lead', 60.00::numeric),
    ('northstar-labs', 'Platform', 'boris@example.test', 'engineer', 100.00::numeric),
    ('blue-orbit', 'Research', 'chen@example.test', 'lead', 80.00::numeric)
) AS v(slug, team_name, email, role_name, allocation)
JOIN organizations o ON o.slug = v.slug
JOIN teams t ON t.organization_id = o.organization_id AND t.name = v.team_name
JOIN app_users u ON u.organization_id = o.organization_id AND u.email = v.email::citext;

INSERT INTO projects (organization_id, owner_id, code, name, priority, status, budget, launch_date, deadline, duration)
SELECT o.organization_id, u.user_id, v.code, v.name, v.priority::priority_level, v.status::task_status,
       v.budget, v.launch_date, v.deadline, v.duration
FROM organizations o
JOIN app_users u ON u.organization_id = o.organization_id
JOIN (VALUES
    ('northstar-labs','NS-CORE1','Core Platform','critical','active',180000.00::numeric,'2026-01-15'::date,'2026-12-20'::timestamptz,interval '11 months'),
    ('blue-orbit','BO-ML001','Signal Research','high','backlog',90000.00::numeric,'2026-03-01'::date,'2026-10-31'::timestamptz,interval '8 months')
) AS v(slug, code, name, priority, status, budget, launch_date, deadline, duration)
  ON v.slug = o.slug AND u.email = CASE WHEN v.slug = 'northstar-labs' THEN 'ana@example.test'::citext ELSE 'chen@example.test'::citext END;

INSERT INTO tasks (project_id, assignee_id, title, description, status, priority, estimate_hours,
                   progress, due_at, time_window, recurrence, labels, custom_fields)
SELECT p.project_id, u.user_id, v.title, v.description, v.status::task_status, v.priority::priority_level,
       v.hours, v.progress, v.due_at, tstzrange(v.due_at - interval '2 days', v.due_at + interval '1 day'),
       int4range(1, 5), v.labels, v.custom_fields::jsonb
FROM projects p
JOIN organizations o ON o.organization_id = p.organization_id
JOIN app_users u ON u.organization_id = o.organization_id
JOIN (VALUES
 ('NS-CORE1','Design API contract','Define stable resource boundaries','done','critical',24.5::numeric,100.00::numeric,'2026-02-10'::timestamptz,ARRAY['api','design'], '{"reviewed":true}'),
 ('NS-CORE1','Implement catalog paging','Add server-side paging and sorting','active','high',40.0::numeric,62.50::numeric,'2026-09-15'::timestamptz,ARRAY['backend','postgres'], '{"risk":"medium"}'),
 ('BO-ML001','Collect baseline signals','Capture representative measurements','backlog','normal',16.0::numeric,0.00::numeric,'2026-04-20'::timestamptz,ARRAY['research','data'], '{"sample_size":10000}')
) AS v(code, title, description, status, priority, hours, progress, due_at, labels, custom_fields)
 ON p.code = v.code AND u.email = CASE WHEN p.code = 'NS-CORE1' THEN 'boris@example.test'::citext ELSE 'chen@example.test'::citext END;

INSERT INTO tasks (task_id, project_id, assignee_id, title, description, status, priority,
                   estimate_hours, progress, due_at, time_window, recurrence, labels, custom_fields)
OVERRIDING SYSTEM VALUE
SELECT 1001, p.project_id, u.user_id, 'Archive migration records',
       'Move completed migration artifacts into long-term storage', 'archived', 'low',
       8.0, 100.00, '2026-11-15'::timestamptz,
       tstzrange('2026-11-13'::timestamptz, '2026-11-16'::timestamptz),
       int4range(1, 2), ARRAY['archive','operations'], '{"retention_years":7}'::jsonb
FROM projects p
JOIN app_users u ON u.organization_id = p.organization_id
WHERE p.code = 'NS-CORE1' AND u.email = 'ana@example.test';

INSERT INTO task_dependencies (predecessor_id, successor_id, dependency_kind, lag)
SELECT predecessor.task_id, successor.task_id, 'blocks', interval '1 day'
FROM tasks predecessor
JOIN tasks successor ON successor.title = 'Implement catalog paging'
WHERE predecessor.title = 'Design API contract';

INSERT INTO tags (organization_id, label, color)
SELECT organization_id, 'important', '#EF4444' FROM organizations WHERE slug = 'northstar-labs'
UNION ALL
SELECT organization_id, 'experimental', '#8B5CF6' FROM organizations WHERE slug = 'blue-orbit';

INSERT INTO task_tags (task_id, tag_id, added_by)
SELECT t.task_id, g.tag_id, u.user_id
FROM tasks t JOIN projects p ON p.project_id = t.project_id
JOIN tags g ON g.organization_id = p.organization_id
JOIN app_users u ON u.user_id = t.assignee_id
WHERE (t.title, g.label) IN (('Implement catalog paging','important'), ('Collect baseline signals','experimental'));

INSERT INTO measurements (organization_id, measured_at, metric_name, value_numeric, value_integer, unit)
SELECT organization_id, '2025-08-01 12:00+00'::timestamptz, 'cpu_load', 0.612300, 61, 'percent' FROM organizations
UNION ALL
SELECT organization_id, '2026-08-01 12:00+00'::timestamptz, 'cpu_load', 0.732100, 73, 'percent' FROM organizations
UNION ALL
SELECT organization_id, '2026-08-02 12:00+00'::timestamptz, 'cpu_load', 0.481200, 48, 'percent' FROM organizations;

INSERT INTO audit_events (organization_id, actor_id, action, client_ip, client_mac, payload, payload_xml)
SELECT o.organization_id, u.user_id, 'project.created', '192.0.2.10', '08:00:2b:01:02:03',
       '{"source":"import","success":true}', '<event><source>import</source><success>true</success></event>'
FROM organizations o JOIN app_users u ON u.organization_id = o.organization_id
WHERE o.slug = 'northstar-labs' AND u.email = 'ana@example.test';

INSERT INTO documents (organization_id, uploaded_by, file_name, content_type, content, sha256)
SELECT o.organization_id, u.user_id, v.file_name, v.content_type,
       convert_to(v.body, 'UTF8'),
       encode(digest(convert_to(v.body, 'UTF8'), 'sha256'), 'hex')
FROM (VALUES
    ('northstar-labs', 'ana@example.test', 'architecture.txt', 'text/plain', 'Stable resource boundaries'),
    ('blue-orbit', 'chen@example.test', 'baseline.csv', 'text/csv', E'metric,value\ncpu_load,0.61\n')
) AS v(slug, email, file_name, content_type, body)
JOIN organizations o ON o.slug = v.slug
JOIN app_users u ON u.organization_id = o.organization_id AND u.email = v.email::citext;

COMMIT;
