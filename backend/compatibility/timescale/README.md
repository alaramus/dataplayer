# Isolated Timescale compatibility sources

These fixtures are separate from the application Compose project and database.
They publish only loopback ports, use disposable public credentials, keep data
in tmpfs and never mount application storage. Stopping a container discards its
database; recreating it rebuilds the samples.

## T1 inspection matrix

| Service | Extension | PostgreSQL | Host port | Compressed storage | Status |
| --- | --- | --- | --- | --- | --- |
| `legacy` | 2.17.2 | 16.6 | 55417 | `compress_chunk` | Passed in 50-test combined run |
| `columnstore` | 2.18.0 | 16.6 | 55418 | `convert_to_columnstore`, Hypercore access method | Passed in 50-test combined run |

The exact image index digests are pinned in [compose.yml](compose.yml), for
`linux/amd64`. They were resolved from Docker Hub on 2026-09-08. A version tag
or matching public signature is not evidence of tested compatibility. The recovered approved run is recorded below.

Both servers contain `plain_fixture` (hstore, no Timescale) and
`timescale_fixture`. The latter holds:

- ordinary data in `public` beside timestamp, integer and empty hypertables;
- bigint values above 2^53, and both compressed and uncompressed chunks;
- identically named hypertables in two schemas, a refreshed continuous
  aggregate, and a paused ten-year retention policy with one manually recorded run;
- `fixture_reader`, `fixture_no_stats` and `fixture_no_metadata`, with different
  source permissions to exercise partial inspection and unavailable discovery.

The administrator is `fixture_admin`. All fixture roles use the disposable
password `fixture-only`. Application credentials and `demo_lab` are not used.

A third database, `lifecycle_fixture`, starts without extensions. The lifecycle
scenario installs and removes Timescale there, checking fresh-adapter discovery
and report visibility while the other databases retain their state. Removal is
in a `finally` block and uses no cascade. Recreate the disposable containers
after changing initialization SQL; existing containers do not rerun it.

## Commands requiring approval

T2 interval-planning scenarios in `test_interval_planning.py` passed in the
2026-09-09 targeted run below. They check unchanged source intervals, schema-specific identities and
refusal of ordinary/integer/aggregate targets, read-only source roles and plain
databases. They certify no mutation semantics, even when later run successfully.

From the repository root, after user approval:

```bash
docker compose -f backend/compatibility/timescale/compose.yml up -d --wait
```

Do not add this file as an override of the application's Compose stack. The
standalone project name is `dataplayer-timescale-compat` and its health check
requires the final fixture marker, not merely an accepting PostgreSQL socket.
Inspect initialization failures with this same Compose file's `logs` command.

After user approval, the disposable project can be removed with:

```bash
docker compose -f backend/compatibility/timescale/compose.yml down
```

The adapter integration harness belongs outside `backend/tests/`: that
directory's autouse database fixture initializes and deletes application users.
The standalone harness must not load that fixture or run an ASGI application
lifespan. API grant/browser acceptance lives separately in
`backend/tests/connectors/test_timescale_read_access.py` and
`frontend/tests/timescale-navigation.spec.ts`: those use mocked source responses
and provide no real-storage evidence. Both passed in the recorded targeted run.

The harness now covers per-database discovery, catalog/path/model/summary
agreement, mixed-storage reads and exports, exact integers, report paging and
source permission failures. Direct insert and reconstructed-DDL refusal scenarios
include hypertables, aggregates, chunks and materializations. These scenarios passed in the recorded isolated run.

Run only after approval, from `backend/`, with both fixture servers ready:

```bash
uv run pytest compatibility/timescale -q
uv run ruff check compatibility
```

Use the explicit compatibility path: `tests/` loads the application fixtures.
The harness reuses the application's Windows-compatible loop factory and
session loop settings, but starts no application lifespan or database fixtures.
The adapter imports still load application settings, so the usual local
backend configuration is required. Every source connection uses the explicit
loopback fixture options; no application database query is made by the harness.

Acceptance specification:
[Timescale architecture](../../../docs/architecture/sources/timescale.md),
[T1 specification](../../../docs/superpowers/specs/2026-09-07-timescale-capabilities-design.md).

## Validation record: 2026-09-08

Recovered from command outputs in task
`01a08166-826e-7691-bb55-8bcdea607011`, after the user approved targeted
validation. No checks were rerun while committing the interrupted work.
Both pinned services reported PostgreSQL 16.6. The matrix covers T1 inspection
and refusals, not T2/T3 mutation semantics.

| Working directory | Command / selection | Recovered result |
| --- | --- | --- |
| backend | `uv run pytest compatibility/timescale -q --tb=short` | 40 passed |
| backend | `uv run pytest tests/adapters -q -k timescale --tb=short` | 82 passed, 1325 deselected |
| backend | Targeted report/API command below | 43 passed |
| backend | `uv run ruff check app tests compatibility` | Passed |
| backend | `uv run mypy app` | 217 source files clean |
| backend | `uv run lint-imports` | 6 contracts kept |
| frontend | `bun run type-check` | Passed after fixture discriminator fix |
| frontend | Component command below | 32 passed in 3 files |
| frontend | `bunx eslint tests/timescale-navigation.spec.ts tests/timescale-features.spec.ts` | Passed |
| frontend | Browser command below, localhost origin | 2 passed |
| repository | `bash scripts/check-docs.sh` | Passed before this documentation update; recheck pending |

Exact targeted selections:

```bash
# backend/
uv run pytest tests/adapters/test_postgres_timescale_reports.py tests/adapters/test_postgres_timescale_report_access.py tests/adapters/test_postgres_timescale_policy_projection.py tests/adapters/test_postgres_timescale_job_statistics.py tests/connectors/test_feature_routes.py tests/connectors/test_timescale_read_access.py -q

# frontend/
bun run test:unit -- src/features/summary/SummaryView.spec.ts src/features/summary/facts.spec.ts src/features/connectors/ConnectorFeatures.spec.ts
PLAYWRIGHT_BASE_URL=http://localhost:5173 bunx playwright test tests/timescale-features.spec.ts tests/timescale-navigation.spec.ts --reporter=line
```

Initial failures exposed unsafe constant-folded policy casts, missing background
policy statistics, outdated refusal text, incomplete catalog fixtures and type/
import errors. The committed fixes retain refusal assertions and validate input
before casts. The statistics fixture enables its paused policy, waits at most
30 seconds for a successful background run and pauses it again in cleanup.
The initial browser run used 127.0.0.1 and could not log in because that origin
was not allowed; the localhost retry passed.

### T1 acceptance evidence

The isolated matrix supplies evidence for per-database discovery and lifecycle,
logical identities, mixed-storage reads/export, bigint precision, report
scope/paging, optional statistics, restricted roles and direct insert/DDL
refusals. API and browser scenarios mock source responses and establish
transport/UI behavior only.

The follow-up runs below cover shared guards, backup/restore, ordinary
PostgreSQL workflows and Timescale reference/workspace round trips.
At this stage, full backend/frontend suites, full frontend lint/build and full
E2E were still pending. The final completion confirmation below supersedes
that status.

### Follow-up: shared-operation acceptance

The resumed targeted run completed after user approval:

- Shared classification/action guards, backup programs, archive inventory and
  backup/restore services: 57 passed without warnings after correcting the
  backup test's synchronous connection-string mock.
- Ordinary PostgreSQL dependency, row, relation, reference, index, constraint,
  column, catalog, fetch and import/reference route regressions: 212 passed and
  three fixture failures. The failures omitted the required installed version
  for an available feature. After correction, all six dependency tests passed;
  the other 209 tests were not rerun.
- Real-source protection selection: 14 passed across both pinned sources.
  New scenarios call cell/block updates, delete, bulk insert and column creation
  directly on populated/empty hypertables and an aggregate, verify Timescale
  refusal before forged-handle decoding, and compare rows/models after refusal.
- Ruff passed for all three changed test files.

Exact commands, from backend:

```bash
uv run pytest tests/adapters/test_postgres_relation_context.py tests/adapters/test_postgres_action_guards.py tests/adapters/test_postgres_backup.py tests/adapters/test_postgres_restore_inventory.py tests/services/test_backups.py tests/services/test_restore_files.py -q --tb=short
uv run pytest tests/adapters/test_postgres_dependencies.py tests/adapters/test_postgres_update.py tests/adapters/test_postgres_relation_changes.py tests/adapters/test_postgres_relation.py tests/adapters/test_postgres_references.py tests/adapters/test_postgres_indexes.py tests/adapters/test_postgres_constraints.py tests/adapters/test_postgres_column_type.py tests/adapters/test_postgres_column_changes.py tests/adapters/test_postgres_catalog.py tests/adapters/test_postgres_fetch.py tests/connectors/test_import_routes.py tests/connectors/test_reference_routes.py -q --tb=short
uv run pytest tests/adapters/test_postgres_dependencies.py -q --tb=short
uv run pytest compatibility/timescale/test_protection.py -q --tb=short
uv run ruff check tests/adapters/test_postgres_backup.py tests/adapters/test_postgres_dependencies.py compatibility/timescale/test_protection.py
```

T1 audit: discovery/lifecycle, specialization, rows/export, reports/statistics,
grant transport and browser navigation have the recorded targeted evidence.
Shared guards and backup/restore now have the additional evidence above.
The relationship/workspace follow-up below supplies cross-schema cascade and
Timescale navigation evidence. At this stage, full required backend/frontend
validation was still pending; the final completion confirmation below
supersedes that status.

### Follow-up: cross-schema relationships and workspace restoration

The isolated relationship fixture creates two uniquely named schemas with an
ordinary referenced table and a populated hypertable carrying a foreign key.
Cleanup removes only those fixture schemas, including on failure.

- Dropping the ordinary parent relation or schema with cascade refuses in both
  preview and execution, because the dependency scope reaches the hypertable
  in the other schema. Source rows and the foreign key remain unchanged.
- Outgoing and incoming references round-trip through source-issued filters.
  Reopening a serialized fetch request with a fresh adapter retains the logical
  hypertable ID, specialization, matching rows and read-only flags.
- The browser scenario now reloads after editing the Chunks filter and again
  after returning to the hypertable tab. It verifies restored filters, one tab
  for the original logical relation, exact bigint text and disabled writes.
  Browser transport remains mocked; real reference semantics are exercised by
  the isolated fixture.

The first fixture attempt incorrectly used the row-query helper for statements
without result sets; switching setup/cleanup to schema_change fixed it.
The four relationship cases then passed on both pinned versions. The extended
browser scenario passed on localhost. Targeted Ruff, frontend type-check and
ESLint passed.

Commands:

```bash
# backend/
uv run pytest compatibility/timescale/test_relationships.py -q --tb=short
uv run ruff check compatibility/timescale/test_relationships.py

# frontend/
bun run type-check
bunx eslint tests/timescale-navigation.spec.ts
PLAYWRIGHT_BASE_URL=http://localhost:5173 bunx playwright test tests/timescale-navigation.spec.ts --reporter=line
```

The complete isolated matrix was rerun after adding these fixtures:
`uv run pytest compatibility/timescale -q --tb=short` — 50 passed in 46.04s.
This supersedes the initial 40-case matrix; it still certifies inspection and
refusals, not T2/T3 mutation strategies.

### T1 completion: 2026-09-08

The user confirmed that all tests passed and T1 is fully complete. This closes
the remaining T1 validation status above. T2 bounded metadata changes are the
next roadmap item, followed by T3 owned operations.

This final status is based on the user's confirmation; no additional command
outputs or counts were supplied, and no checks were rerun for this documentation
update. The recorded targeted results above remain the detailed command evidence.
T2/T3 mutation strategies still require their own real-source validation.

### T2 interval execution: isolated validation, 2026-09-09

`test_interval_execution.py` uses disposable hypertables on both pinned sources.
It covers existing/future chunk boundaries, native setter exclusion by the
public metadata view lock, stale review after an external change, source
refusal, cancellation cleanup, missing lock permission and a concrete overload.
The implementation uses a database-wide Timescale metadata lock and is not
registered. After explicit user approval, both pinned containers became healthy
and the following command passed from `backend/`:

```bash
uv run pytest compatibility/timescale/test_interval_planning.py compatibility/timescale/test_interval_execution.py -q --tb=short
```

Result: **36 passed in 15.62s**, exit code 0. This covers planning, read-only
snapshot/preview and interval execution on Timescale 2.17.2 and 2.18.0 with
PostgreSQL 16. The fixture verifies each extension version and PostgreSQL major.
It supplies interval mutation evidence independently of T1; it does not certify
storage/policy changes, conversion or other version combinations. Backend unit,
transport, static and frontend review checks remain pending. No other checks
were run in this session, including the documentation check.
