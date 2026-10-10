# Isolated Timescale compatibility sources

These fixtures are separate from the application Compose project and database.
They publish only loopback ports, use disposable public credentials, keep data
in tmpfs and never mount application storage. Stopping a container discards its
database; recreating it rebuilds the samples.

Every scenario under this directory runs once per source below, so a change to
the adapter is answered by each release at once. The point of the matrix is
that no release is named in `app/`: what a strategy can do is discovered
(D120), and the matrix is how that claim is checked.

## The matrix

| Source | Extension | PostgreSQL | Host port | Compressed chunks are |
| --- | --- | --- | --- | --- |
| `v2_14_pg14` | 2.14.2 | 14 | 55414 | `compress_chunk`, heap |
| `v2_17_pg16` | 2.17.2 | 16 | 55417 | `compress_chunk`, heap |
| `v2_18_pg16` | 2.18.0 | 16 | 55418 | `convert_to_columnstore`, Hypercore |
| `v2_19_pg15` | 2.19.3 | 15 | 55419 | `convert_to_columnstore`, Hypercore |
| `v2_23_pg16` | 2.23.1 | 16 | 55423 | `convert_to_columnstore`, heap |
| `v2_30_pg17` | 2.30.0 | 17 | 55430 | `convert_to_columnstore`, heap |
| `v2_30_pg18` | 2.30.0 | 18 | 55431 | `convert_to_columnstore`, heap |

It spans every PostgreSQL major the extension still ships for, the last release
for the majors it has dropped, and the releases where its public API changed
shape. The image index digests are pinned in [compose.yml](compose.yml) for
`linux/amd64`, resolved from Docker Hub on 2026-09-12. A version tag or a
matching public signature is not evidence of tested compatibility.

The fixture SQL names no release. Whether a chunk is converted with
`compress_chunk` or `convert_to_columnstore`, whether that takes the Hypercore
access method, and which size and compression statistics exist are all read
from the installed extension, so adding a service needs no edit to the SQL.
PostgreSQL 18 images keep the cluster in a major-version subdirectory, so that
one service mounts its tmpfs a level higher.

## What the sources hold

Each server has `plain_fixture` (hstore, no Timescale) and `timescale_fixture`.
The latter holds:

- ordinary data in `public` beside timestamp, integer and empty hypertables;
- bigint values above 2^53, and both compressed and uncompressed chunks;
- identically named hypertables in two schemas, a refreshed continuous
  aggregate, and a paused ten-year retention policy with one recorded run;
- `fixture_reader`, `fixture_no_stats` and `fixture_no_metadata`, with
  different source permissions, to exercise partial inspection and unavailable
  discovery.

The administrator is `fixture_admin`. All fixture roles use the disposable
password `fixture-only`. Application credentials and `demo_lab` are not used.

A third database, `lifecycle_fixture`, starts without extensions. The lifecycle
scenario installs and removes Timescale there, checking fresh-adapter discovery
and report visibility while the other databases keep their state. Removal is in
a `finally` block and uses no cascade. Recreate the containers after changing
initialization SQL; existing ones do not rerun it.

Mutation scenarios create their own disposable schema per test and drop it
afterwards, which removes its policy jobs too. Policy thresholds are ten and
twenty years, so a background run drops or compresses none of the 2026 rows.

## Running it

From the repository root, after user approval:

```bash
docker compose -f backend/compatibility/timescale/compose.yml up -d --wait
```

Do not add this file as an override of the application's Compose stack. The
standalone project name is `dataplayer-timescale-compat` and its health check
requires the final fixture marker, not merely an accepting PostgreSQL socket.
Inspect initialization failures with this same Compose file's `logs` command.
The project can be removed with the same file's `down`.

Then, from `backend/`, with every source healthy:

```bash
uv run pytest compatibility/timescale -q
uv run ruff check compatibility
```

Use the explicit compatibility path: `tests/` loads the application fixtures,
whose autouse database fixture initializes and deletes application users. The
harness reuses the application's Windows-compatible loop factory and session
loop settings but starts no application lifespan and makes no application
database query. The adapter imports still load application settings, so the
usual local backend configuration is required.

API grant and browser acceptance live elsewhere —
`backend/tests/connectors/test_timescale_read_access.py`,
`frontend/tests/timescale-navigation.spec.ts` and
`frontend/tests/timescale-chunk-jobs.spec.ts` — and use mocked source
responses, so they establish transport and UI behaviour only. The owned job,
its admission and its recovery need the application's database, so
`backend/tests/source_operations` covers those.

Acceptance specification:
[Timescale architecture](../../../docs/architecture/sources/timescale.md),
[T1 specification](../../../docs/decisions/2026-09-07-timescale-capabilities-design.md).

## What the releases disagree about

Found by running the matrix; each is handled in `app/` and covered here.

- **Routine signatures grow and shrink.** `add_compression_policy` gained
  `hypercore_use_access_method` in 2.18 and lost it again by 2.23;
  `add_continuous_aggregate_policy` has had seven, eight, ten and eleven
  arguments; `compress_chunk` gained and lost the same hypercore argument. A
  strategy asks only for the leading arguments it passes and requires every
  further one to have a default (`test_api_discovery.py`).
- **The jobs view names a different relation for a refresh policy.** Up to
  2.19 it names the materialization hypertable; from a later release it names
  the user view. Reading under one identity alone made a policy invisible and
  the next set refuse as a duplicate, so the plan accepts either.
- **`pg_input_is_valid` is PostgreSQL 16 and newer.** Policy settings are read
  on 14 and 15 too, so a value is matched against the shape PostgreSQL writes
  instead of being offered to a cast that may fail.
- **PostgreSQL began range-checking interval fields in 15.** On 14 an
  out-of-range field folds into a representable one, so the scenario about a
  source refusing an absurd interval has nothing to refuse there and skips.
- **Hypercore is the compressed access method only in 2.18 and 2.19.** Before
  and after, a compressed chunk stays heap.
- **An `ALTER TABLE` that leaves a columnstore list out derives it again before
  2.20.** Setting only `compress_chunk_time_interval` chose a segment column
  from an index, the same column the order already named, and the source
  refused. The hypertable editor states both lists in every change
  (`test_hypertable_design.py`).
- **`RESET` of `compress_segmentby` or `compress_orderby` is refused up to
  2.19,** and an unset segment list reads as NULL there whether it was never
  set or set to nothing. From 2.23 NULL means Timescale chooses for each chunk
  and an empty string means none.
- **`hypertable_compression_settings` joins names with commas, unquoted.** A
  column called `x,y` cannot be read back from it; the per-column
  `compression_settings` view, deprecated since 2.18, still lists it whole on
  every release here.
- **`finalized` left `continuous_aggregates`** between 2.23 and 2.30, and
  `hypertable_compression_settings` gained an `index` column; the reports and
  the settings plan project only what every release in the matrix shares.

## Validation record: 2026-10-10, integer time

H5 of D207 added `test_hypertable_integer.py`, six scenarios on every source: an
integer table converted with a template `integer_now` and a counted retention
age, an integer hypertable taking an existing function and swapping it, a taken
function name refused, a dropped `integer_now` kept by its name, a merge
interval on integer time left to SQL, and the designer creating an integer
hypertable with its function. Every release behaved alike.

| Working directory | Command | Result |
| --- | --- | --- |
| backend | `uv run pytest compatibility/timescale -q` | 986 passed, 1 skipped, 7 failed: one conversion scenario proposing an integer column, fixed; the three editor files then 168 passed |
| backend | `uv run pytest tests/ -q` | 3796 passed, 154 skipped |
| frontend | unit, type, lint and build checks | Passed |
| frontend | `bunx playwright test` over the hypertable, designer and Timescale scenarios | 7 passed |

## Validation record: 2026-10-10, the table designer's Hypertable section

H4 of D207 added `test_hypertable_creation.py`, five scenarios on every
source: a designed table created as a hypertable with a hash dimension, a
columnstore, retention and reorder policies and no default index, and the
designer's refusals.

| Working directory | Command | Result |
| --- | --- | --- |
| backend | `uv run pytest compatibility/timescale -q` | 950 passed, 1 skipped, 1 failed: the scheduler test below, on 2.18 |
| backend | `uv run pytest tests/ -q` | 3789 passed, 154 skipped |
| frontend | unit, type, lint and build checks | Passed |
| frontend | `bunx playwright test` over the hypertable, designer and Timescale scenarios | 11 passed |

## Validation record: 2026-10-09, conversion from the editor

H3 of D207 added `test_hypertable_conversion.py`, seven scenarios on every
source: an empty table converted with its settings at once, a table with rows
converted as a one-unit job, a row without a time rolling the whole job back,
and the refusals.

| Working directory | Command | Result |
| --- | --- | --- |
| backend | `uv run pytest compatibility/timescale -q` | 915 passed, 1 skipped, 1 failed: see below |
| backend | `uv run pytest compatibility/timescale -q -k 2.17`, twice | 131 passed each time |
| backend | `uv run pytest tests/ -q` | 3786 passed, 154 skipped, after the fix the run found |
| frontend | unit, type, lint and build checks | Passed |
| frontend | `bunx playwright test` over the editor and the catalog's and Timescale's scenarios | 29 passed |

`test_recorded_policy_run_has_public_statistics` failed in two of the three
full runs since the editor's scenarios were added, on one to three of 2.14,
2.17 and 2.19: their scheduler did not start the fixture's job within 30
seconds. It passes alone, after the editor's files, and in the whole suite
restricted to one of those sources. Before H2 the full run passed it. The cause
is not established; the editor's scenarios add policies that start at once and
drop their tables minutes later, which is the likeliest difference.

## Validation record: 2026-10-09

The hypertable settings editor (D207, H1 and H2) was added with
`test_hypertable_design.py`, eleven scenarios on every source.

| Working directory | Command | Result |
| --- | --- | --- |
| backend | `uv run pytest compatibility/timescale -q` | 867 passed, 1 skipped, over all seven sources |
| backend | `uv run pytest tests/ -q` | 3786 passed, 154 skipped, after one expected title was added |
| backend | `uv run ruff check app tests compatibility`, `uv run mypy app`, `uv run lint-imports` | Passed |
| frontend | `bun run test:unit`, `bun run type-check`, `bun run lint`, `bun run build` | Passed |
| frontend | `bunx playwright test` over the 31 scenarios that open a menu | 177 passed or skipped; one login timeout passed on its own rerun |

An earlier full run failed `test_recorded_policy_run_has_public_statistics`
on 2.14, 2.17 and 2.19: their job scheduler had stopped starting jobs after
many policies were added and their tables dropped within minutes, by manual
probes and repeated runs. Restarting those three containers cleared it, and
the editor's scenarios followed by that test pass on a fresh source. If it
recurs, restart the source before suspecting the code.

## Validation record: 2026-09-12

The user asked for the implementation to be tested on the common and current
releases and for what failed to be fixed. Results after the fixes above:

| Working directory | Command | Result |
| --- | --- | --- |
| backend | `uv run pytest compatibility/timescale -q` | 790 passed, 1 skipped, over all seven sources |
| backend | `uv run pytest tests/ -q` | 2882 passed, 13 skipped |
| backend | `uv run ruff check app tests compatibility` | Passed |
| backend | `uv run mypy app` | 249 source files clean |
| backend | `uv run lint-imports` | 6 contracts kept |
| repository | `bash scripts/check-docs.sh` | Passed |

The one skip is the interval scenario that needs a source refusal, on
PostgreSQL 14. The frontend was not touched and its checks were not run.

Before the fixes, the same matrix run answered 305 failed, 430 passed: every
mutation scenario on the five sources the version list did not name. The
failures that survived removing that list are the six differences above; each
was found by this run and none of them by the two sources the matrix had
before. Earlier validation records are in git history.

## Adding a source

Resolve the image's index digest, add a service to
[compose.yml](compose.yml) with a free loopback port, add a
`TimescaleSource` to `SOURCES` in [conftest.py](conftest.py) naming the
extension version, the PostgreSQL major and the access method its compressed
chunks use, then start the project and run the suite. The fixture SQL needs no
edit. Nothing in `app/` should: a release that needs one is the finding.
