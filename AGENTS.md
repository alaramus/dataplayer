# AGENTS.md

Entry point for coding agents and humans. Keep this file limited to facts needed
before the task is known; details belong in the linked documentation.

- [ENGINEERING.md](ENGINEERING.md) — normative whenever code is touched.
- [docs/migration-roadmap.md](docs/migration-roadmap.md) — current state and the
  next migration slice.
- [docs/architecture/](docs/architecture/) — contracts, decisions and known
  deviations.
- [docs/superpowers/specs/README.md](docs/superpowers/specs/README.md) — design
  history and specification index.

## Project

DataPlayer connects heterogeneous data sources and lets users explore and work
with them through one interface. It is a typed rewrite of two working legacy
applications:

- backend: `C:\Users\maxim\PycharmProjects\dbwebtool`;
- frontend: `C:\Users\maxim\PycharmProjects\myquasar`.

Use the old projects to understand workflows and edge cases. Port ideas, never
files or architecture. The FastAPI template is not a constraint.

Everything newly written is in English: code, comments, UI strings, tests,
commits and documentation. Russian specs dated through 2026-08-27 and plans are
legacy notes and stay unchanged.

## Read before changing

| Area | Read first |
| --- | --- |
| A source type, a capability, a node kind, untrusted input | [sources/contract.md](docs/architecture/sources/contract.md) |
| Query documents, SQL execution, results, history, transactions | [querying.md](docs/architecture/querying.md) |
| Connection options, connection strings, pools, read cache | [sources/connecting.md](docs/architecture/sources/connecting.md) |
| Reading a relation, changing rows, export, import | [sources/relations.md](docs/architecture/sources/relations.md) |
| Columns, indexes, constraints, renaming a node | [sources/ddl.md](docs/architecture/sources/ddl.md) |
| Opening a node as anything but rows: documents, media, archives | [sources/content.md](docs/architecture/sources/content.md) |
| Actions, action previews, downloads, reports | [sources/actions.md](docs/architecture/sources/actions.md) |
| A share link, what it opens, an access request | [sharing.md](docs/architecture/sharing.md) |
| A managed service, a service template, what a container is started with | [services.md](docs/architecture/services.md) |
| Long work the server owns, its progress, its recovery | [jobs.md](docs/architecture/jobs.md) |
| Backend modules, routes, migrations, secrets, database | [backend.md](docs/architecture/backend.md) |
| Screens, components, colours, layers | [frontend.md](docs/architecture/frontend.md) |
| A page of rows: the grid, downloads, charts | [grid.md](docs/architecture/grid.md) |
| Layout, tabs, dragging, floating windows | [workspace.md](docs/architecture/workspace.md) |
| A diagram of nodes and connections, in 2D or 3D | [graphs.md](docs/architecture/graphs.md) |
| Sockets, topics, server-pushed state | [realtime.md](docs/architecture/realtime.md) |
| Any code | [ENGINEERING.md](ENGINEERING.md) |

The roadmap says what comes next. What is already done is recorded by the spec
index and by git; do not inventory it here or there.

## Decision registry

The wording, reasoning and known deviations live in the linked architecture
files. IDs are stable because specs and commits refer to them.

| ID | Home |
| --- | --- |
| D1 | [sources/contract](docs/architecture/sources/contract.md) |
| D2 | [sources/contract](docs/architecture/sources/contract.md) |
| D2a | [sources/contract](docs/architecture/sources/contract.md) |
| D2b | [sources/contract](docs/architecture/sources/contract.md) |
| D2c | [sources/contract](docs/architecture/sources/contract.md) |
| D2d | [sources/contract](docs/architecture/sources/contract.md) |
| D3 | [backend](docs/architecture/backend.md) |
| D4 | [backend](docs/architecture/backend.md) |
| D5 | [backend](docs/architecture/backend.md) |
| D6 | [frontend](docs/architecture/frontend.md) |
| D7 | [frontend](docs/architecture/frontend.md) |
| D8 | [sources/contract](docs/architecture/sources/contract.md) |
| D9 | [sources/actions](docs/architecture/sources/actions.md) |
| D10 | [sources/connecting](docs/architecture/sources/connecting.md) |
| D11 | [frontend](docs/architecture/frontend.md) |
| D12 | [workspace](docs/architecture/workspace.md) |
| D13 | [sources/contract](docs/architecture/sources/contract.md) |
| D14 | [workspace](docs/architecture/workspace.md) |
| D15 | [sources/connecting](docs/architecture/sources/connecting.md) |
| D16 | [sources/connecting](docs/architecture/sources/connecting.md) |
| D17 | [sources/connecting](docs/architecture/sources/connecting.md) |
| D18 | [realtime](docs/architecture/realtime.md) |
| D19 | [realtime](docs/architecture/realtime.md) |
| D20 | [sources/contract](docs/architecture/sources/contract.md) |
| D21 | [sources/contract](docs/architecture/sources/contract.md) |
| D22 | [sources/relations](docs/architecture/sources/relations.md) |
| D23 | [sources/relations](docs/architecture/sources/relations.md) |
| D24 | [grid](docs/architecture/grid.md) |
| D25 | [sources/relations](docs/architecture/sources/relations.md) |
| D26 | [sources/relations](docs/architecture/sources/relations.md) |
| D27 | [sources/ddl](docs/architecture/sources/ddl.md) |
| D28 | [grid](docs/architecture/grid.md) |
| D29 | [sources/ddl](docs/architecture/sources/ddl.md) |
| D30 | [sources/ddl](docs/architecture/sources/ddl.md) |
| D31 | [sources/connecting](docs/architecture/sources/connecting.md) |
| D32 | [sources/ddl](docs/architecture/sources/ddl.md) |
| D33 | [backend](docs/architecture/backend.md) |
| D34 | [backend](docs/architecture/backend.md) |
| D35 | [grid](docs/architecture/grid.md) |
| D36 | [sources/relations](docs/architecture/sources/relations.md) |
| D37 | [sources/ddl](docs/architecture/sources/ddl.md) |
| D38 | [sources/ddl](docs/architecture/sources/ddl.md) |
| D39 | [sources/ddl](docs/architecture/sources/ddl.md) |
| D40 | [sources/ddl](docs/architecture/sources/ddl.md) |
| D41 | [sources/relations](docs/architecture/sources/relations.md) |
| D42 | [sources/relations](docs/architecture/sources/relations.md) |
| D43 | [sources/relations](docs/architecture/sources/relations.md) |
| D44 | [sources/relations](docs/architecture/sources/relations.md) |
| D45 | [sources/relations](docs/architecture/sources/relations.md) |
| D46 | [sources/actions](docs/architecture/sources/actions.md) |
| D47 | [sources/content](docs/architecture/sources/content.md) |
| D48 | [sources/content](docs/architecture/sources/content.md) |
| D49 | [sources/actions](docs/architecture/sources/actions.md) |
| D50 | [frontend](docs/architecture/frontend.md) |
| D51 | [sources/content](docs/architecture/sources/content.md) |
| D52 | [sources/content](docs/architecture/sources/content.md) |
| D53 | [sources/content](docs/architecture/sources/content.md) |
| D54 | [sources/relations](docs/architecture/sources/relations.md) |
| D55 | [sources/actions](docs/architecture/sources/actions.md) |
| D56 | [sources/actions](docs/architecture/sources/actions.md) |
| D57 | [sources/content](docs/architecture/sources/content.md) |
| D58 | [sharing](docs/architecture/sharing.md) |
| D59 | [sharing](docs/architecture/sharing.md) |
| D60 | [sharing](docs/architecture/sharing.md) |
| D61 | [sharing](docs/architecture/sharing.md) |
| D62 | [querying](docs/architecture/querying.md) |
| D63 | [querying](docs/architecture/querying.md) |
| D64 | [querying](docs/architecture/querying.md) |
| D65 | [querying](docs/architecture/querying.md) |
| D66 | [querying](docs/architecture/querying.md) |
| D67 | [grid](docs/architecture/grid.md) |
| D68 | [sources/actions](docs/architecture/sources/actions.md) |
| D69 | [workspace](docs/architecture/workspace.md) |
| D70 | [sources/relations](docs/architecture/sources/relations.md) |
| D71 | [sources/content](docs/architecture/sources/content.md) |
| D72 | [sources/relations](docs/architecture/sources/relations.md) |
| D73 | [sources/actions](docs/architecture/sources/actions.md) |
| D74 | [sources/actions](docs/architecture/sources/actions.md) |
| D75 | [sources/contract](docs/architecture/sources/contract.md) |
| D76 | [sources/contract](docs/architecture/sources/contract.md) |
| D77 | [querying](docs/architecture/querying.md) |
| D78 | [querying](docs/architecture/querying.md) |
| D79 | [sources/actions](docs/architecture/sources/actions.md) |
| D80 | [services](docs/architecture/services.md) |
| D81 | [jobs](docs/architecture/jobs.md) |
| D82 | [services](docs/architecture/services.md) |
| D83 | [services](docs/architecture/services.md) |
| D84 | [services](docs/architecture/services.md) |
| D85 | [services](docs/architecture/services.md) |
| D86 | [services](docs/architecture/services.md) |
| D87 | [services](docs/architecture/services.md) |
| D88 | [services](docs/architecture/services.md) |
| D89 | [services](docs/architecture/services.md) |
| D90 | [services](docs/architecture/services.md) |
| D91 | [sources/contract](docs/architecture/sources/contract.md) |
| D92 | [workspace](docs/architecture/workspace.md) |
| D93 | [workspace](docs/architecture/workspace.md) |
| D94 | [workspace](docs/architecture/workspace.md) |
| D95 | [jobs](docs/architecture/jobs.md) |
| D96 | [querying](docs/architecture/querying.md) |
| D97 | [graphs](docs/architecture/graphs.md) |
| D98 | [sources/contract](docs/architecture/sources/contract.md) |
| D99 | [frontend](docs/architecture/frontend.md) |
| D100 | [sources/connecting](docs/architecture/sources/connecting.md) |
| D101 | [sources/connecting](docs/architecture/sources/connecting.md) |

## Working rules

1. Write tests with a change, but run tests, linters, type checks, builds or E2E
   only with the user's explicit approval. An implementation-and-test request
   counts as approval. State clearly when validation was not run.
2. Never claim a result works without running the relevant check and reading
   its output. Prefer targeted checks unless a full suite was approved.
3. Preserve unrelated work in a dirty tree. Do not overwrite user changes.
4. `frontend/src/client` is generated. Never edit it; after API schema or route
   changes run `bash scripts/generate-client.sh`.
5. New settings go in `.env.example`; `.env` is not tracked.
6. A lasting contract or intentional deviation must be documented in the
   relevant architecture file and, when it needs a stable ID, in a spec and
   this registry.

A change is ready for validation when implementation and tests are written. It
is verified only when every user-approved command required by ENGINEERING.md for
the affected side is clean.

## Commands

The database and backend run in Docker:

```bash
docker compose up -d db backend
docker compose logs -f backend
docker compose up -d --build backend
```

`prestart` waits for PostgreSQL, migrates, creates the first superuser and, in
development, rebuilds fixtures and sample storage. A prestart failure prevents
the backend from serving; inspect it with `docker compose logs prestart`.

Backend checks, from `backend/`:

```bash
uv sync
uv run pytest tests/ -q
uv run mypy app
uv run ruff check app tests
uv run lint-imports
```

Frontend checks, from `frontend/`:

```bash
bun run dev
bun run test:unit
bun run type-check
bun run lint
bun run build
bunx playwright test
```

Repository checks:

```bash
bash scripts/generate-client.sh   # after backend API changes
bash scripts/check-docs.sh
```

CI runs backend tests and static checks, frontend unit/type/lint/build checks and
the documentation check. E2E is local because it needs the database, backend and
a warmed dev server together.

## Critical traps

- Do not run the FastAPI server natively on Windows: psycopg async is
  incompatible with the default Proactor loop. Use Docker. Standalone scripts
  and pytest use `app/core/db.py::loop_factory`.
- A connection pool belongs to the event loop that created it. Pytest shares
  one session loop; never pass a store into another loop.
- A test marked `skipif(os.name != "posix")` never runs on the development
  machine — Windows refuses to create a symbolic link without privileges — so
  CI is the first thing to execute it. Treat such a test as unproven until the
  pipeline is green.
- The pipeline starts from an empty database and applies the fixtures itself.
  A test that reads or writes inside `demo_lab` passes locally on what prestart
  seeded; if it needs anything the seed does not create, it fails only in CI.
- `docker compose up -d` does not include backend source changes. Rebuild with
  `docker compose up -d --build backend`.
- Backend tests wipe users in the development database. Running
  `docker compose up -d db backend` afterwards restores the superuser and
  development samples through prestart.
- Alembic sees only models imported by `app/alembic/env.py`.
- `bun run type-check` deliberately runs `vue-tsc` under Node in build mode;
  do not replace it with a direct Bun or `tsconfig.json` invocation.
- Warm `bun run dev` before the full E2E suite and set
  `PLAYWRIGHT_BASE_URL=http://localhost:5173`. Use a console reporter while
  Vite is watching; writing the HTML report inside `frontend/` reloads pages.
  The suite runs one worker: several browsers starve the one dev server they
  share and raise each other's notifications, and the failures land anywhere.
- Editing a source file while the E2E suite is running feeds the change to the
  dev server and reloads the page under the test.
- Shell scripts under `backend/scripts/` must keep LF endings.
- Native backend checks started from `backend/` read `../.env`; CI has no such
  file. See [backend.md](docs/architecture/backend.md) for the clean rehearsal.
- The backend container sees PostgreSQL as host `db`, not `localhost`.
- psycopg treats a literal `%` as a placeholder whenever parameters are
  supplied. A query with no bindings must pass no parameters, not `()`.
- Blocking work inside an async handler must go through a thread pool.
- Quasar forwards `data-testid` on fields to the `<input>` itself.

## Resume point

Continue the first unfinished item in
[docs/migration-roadmap.md](docs/migration-roadmap.md). Read the named legacy
sources before designing it, and do not ask what comes next unless an external
decision genuinely blocks progress.
