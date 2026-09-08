# Isolated Timescale compatibility sources

These fixtures are separate from the application Compose project and database.
They publish only loopback ports, use disposable public credentials, keep data
in tmpfs and never mount application storage. Stopping a container discards its
database; recreating it rebuilds the samples.

## Candidate matrix

| Service | Extension | PostgreSQL | Host port | Compressed storage | Status |
| --- | --- | --- | --- | --- | --- |
| `legacy` | 2.17.2 | 16 | 55417 | `compress_chunk` | Not run |
| `columnstore` | 2.18.0 | 16 | 55418 | `convert_to_columnstore`, Hypercore access method | Not run |

The exact image index digests are pinned in [compose.yml](compose.yml), for
`linux/amd64`. They were resolved from Docker Hub on 2026-09-08. A version tag
or matching public signature is not evidence of tested compatibility. Record
the actual PostgreSQL version and test results here after an approved run.

Both servers contain `plain_fixture` (hstore, no Timescale) and
`timescale_fixture`. The latter holds:

- ordinary data in `public` beside timestamp, integer and empty hypertables;
- bigint values above 2^53, and both compressed and uncompressed chunks;
- identically named hypertables in two schemas, a refreshed continuous
  aggregate, and a paused retention policy;
- `fixture_reader`, `fixture_no_stats` and `fixture_no_metadata`, with different
  source permissions to exercise partial inspection and unavailable discovery.

The administrator is `fixture_admin`. All fixture roles use the disposable
password `fixture-only`. Application credentials and `demo_lab` are not used.

## Commands requiring approval

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
lifespan. API grant/browser acceptance remains a separate follow-up.

Contract and outstanding acceptance:
The harness now covers per-database discovery, catalog/path/model/summary
agreement, mixed-storage reads and exports, exact integers, report paging and
source permission failures. These scenarios are written but have not been run.

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

Outstanding acceptance:
[Timescale architecture](../../../docs/architecture/sources/timescale.md),
[T1 specification](../../../docs/superpowers/specs/2026-09-07-timescale-capabilities-design.md).
