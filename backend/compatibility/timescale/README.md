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
[T1 specification](../../../docs/decisions/2026-09-07-timescale-capabilities-design.md).

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

### T2 follow-up: user-run checks, 2026-09-09

The user reported running all tests and finding errors only in
`uv run ruff check app tests compatibility`; everything else was reported clean.
No additional command outputs or test counts were supplied. Ruff reported five
unused fixture arguments and one import-formatting error in the interval-plan
and action-route tests. The fixtures are now requested with `usefixtures` where
their return values are unused, preserving setup and teardown; the import block
is expanded. These edits have not been revalidated. This report supersedes the
earlier pending status for the user's completed checks, but does not establish
a clean Ruff result after the fix or complete T2 implementation.

The user subsequently confirmed that the repeat run after `482a537` was entirely
green. No counts or further outputs were supplied. This closes the pending
checks for that commit. The later registration slice adds unit coverage and
extends the chunk-boundary scenario through the registered action's offers,
preview and reviewed execution. Those new changes have not been run and do not
inherit a passing result from the earlier direct-execution scenario.

### T2 policies, compression settings and conversion (2026-09-11)

`test_retention_policy.py` and `test_compression_policy.py` create a
disposable hypertable per scenario through `policy_tables.py` and drop its
schema afterwards, which removes its policy jobs too. Both cover set, replace
and remove through the registered actions, an external policy added after
review and a refused replacement keeping the existing job. Retention also
covers the pause refusal, reading the fixture's paused policy without change,
the jobs-view lock excluding an external `add_retention_policy`, cancellation
releasing locks, ineligible targets, a read-only role and a plain database;
compression covers a hypertable without compression and the add shape of the
installed version. Thresholds are ten and twenty years, so a background run
drops or compresses none of the 2026 fixture rows.

`test_refresh_policy.py` adds a continuous aggregate over the disposable
hypertable and covers set, replace and remove, a window that ends before it
starts, a conflict with a paused source retention policy, an external policy
after review, a window the source rejects keeping the existing job and the add
shape of the installed version. It plans against the fixture's `lab.hourly`
read-only.

`test_compression_settings.py` enables compression on a disposable hypertable
and compares the public settings view with the reviewed lists. It also changes
the settings after compressing one chunk with the version's own API and checks
that chunk's settings stay put, and covers lines that name no column, an
external change after review, an open reader making execution refuse within
the lock timeout, the unique-key disclosure and `lab.metrics` planned
read-only.

`test_conversion.py` creates tables in a disposable schema and converts them
through the registered action. It checks the unchanged node ID and hypertable
specialization, the dimension and interval, and the NOT NULL and time index the
preview promised; a reused one-column time index; rows arriving before and
after review; unique indexes with and without the time column; unlogged, rule,
inheritance and column-less tables; a hypertable referencing the table; the
owner boundary, a populated fixture table and a plain database. All of these
scenarios passed in the run recorded below.

### Validation record: 2026-09-11

The user approved running every check. Results on this branch:

| Working directory | Command | Result |
| --- | --- | --- |
| backend | `uv run ruff check app tests compatibility` | Passed after nine import-layout fixes |
| backend | `uv run mypy app` | 239 source files clean |
| backend | `uv run lint-imports` | 6 contracts kept |
| backend | `uv run pytest tests/ -q` | 2773 passed, 13 skipped |
| backend | `uv run pytest compatibility/timescale -q --tb=short` | 192 passed |
| frontend | `bun run test:unit` | 1554 passed in 172 files |
| frontend | `bun run type-check` | Passed |
| frontend | `bun run lint` | 0 errors, 20 existing warnings |
| frontend | `bun run build` | Passed |
| frontend | `PLAYWRIGHT_BASE_URL=http://localhost:5173 bunx playwright test --reporter=line` | 185 passed, 1 failed; that scenario passed alone after its fix |
| repository | `bash scripts/check-docs.sh` | Passed |

The first matrix run failed six conversion scenarios on both versions. Primary
keys and unique constraints were read as NO INHERIT constraints, because
PostgreSQL marks every index-backed constraint `connoinherit`; the source
refuses only NO INHERIT checks, so the plan now reads `contype = 'c'` and a
scenario covers both. One scenario expected the populated fixture table to be
refused as not empty, but it has no time column, which the plan names first.
The backend capability test gained the nine Timescale titles, including the
interval one that registration had added earlier. The E2E failure depended on
a connection nothing creates — the backend suite deletes the users who owned
them — and the scenario now brings its own.

No browser scenario exercises the shared reviewed form yet, so its browser
acceptance remains open.
