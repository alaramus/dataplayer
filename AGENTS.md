# AGENTS.md

Entry point for coding agents and humans. Keep this file limited to facts needed
before the task is known; details belong in the linked documentation.

- [ENGINEERING.md](ENGINEERING.md) — normative whenever code is touched.
- [docs/architecture/](docs/architecture/) — contracts, decisions and known
  deviations.
- [docs/decisions/README.md](docs/decisions/README.md) — design
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
| What a catalog shows of a node, searching it, a key space | [sources/catalog.md](docs/architecture/sources/catalog.md) |
| Query documents, SQL execution, results, history, transactions | [querying.md](docs/architecture/querying.md) |
| Connection options, connection strings, pools, read cache | [sources/connecting.md](docs/architecture/sources/connecting.md) |
| TimescaleDB, extension discovery, hypertables, chunks and policies | [sources/timescale.md](docs/architecture/sources/timescale.md) |
| A source action too long for a request: its plan, review and outcomes | [sources/operations.md](docs/architecture/sources/operations.md) |
| A source made of files, the storage it brings, the explorer over it | [sources/explorer.md](docs/architecture/sources/explorer.md) |
| An SSH server, the server key it trusts, SSH keys and their passphrases | [sources/ssh.md](docs/architecture/sources/ssh.md) |
| A terminal, its socket, who may open one | [terminals.md](docs/architecture/terminals.md) |
| Reading a relation, changing the rows in it | [sources/relations.md](docs/architecture/sources/relations.md) |
| Copying rows between sources, pasting into another connection, a transfer job, loading a file in, exporting every row | [sources/transfer.md](docs/architecture/sources/transfer.md) |
| A reference somebody drew by hand between two columns or two sources, a table declared over Redis keys | [sources/declared.md](docs/architecture/sources/declared.md) |
| Columns, indexes, constraints, renaming a node | [sources/ddl.md](docs/architecture/sources/ddl.md) |
| Opening a node as anything but rows: documents, media, archives | [sources/content.md](docs/architecture/sources/content.md) |
| Actions and action previews | [sources/actions.md](docs/architecture/sources/actions.md) |
| Downloads, what a download asks first, reports a source publishes | [sources/downloads.md](docs/architecture/sources/downloads.md) |
| A share link, what it opens, an access request | [sharing.md](docs/architecture/sharing.md) |
| A managed service, a service template, what a container is started with | [services.md](docs/architecture/services.md) |
| Whether this server may start containers, and what that costs | [services-runtime.md](docs/architecture/services-runtime.md) |
| Copying a database out, putting it back, a program run in a container | [backups.md](docs/architecture/backups.md) |
| Long work the server owns, its progress, its recovery | [jobs.md](docs/architecture/jobs.md) |
| Backend modules, routes, migrations, secrets, database | [backend.md](docs/architecture/backend.md) |
| Screens, components, colours, layers | [frontend.md](docs/architecture/frontend.md) |
| A page of rows: the grid, downloads, charts | [grid.md](docs/architecture/grid.md) |
| Layout, tabs, dragging, the bar and card at the foot | [workspace.md](docs/architecture/workspace.md) |
| A floating window, the forms in it, detaching a tab, a pair of catalogs | [windows.md](docs/architecture/windows.md) |
| A notification, something waiting for an answer, running work on screen | [notifications.md](docs/architecture/notifications.md) |
| A diagram of nodes and connections, in 2D or 3D | [graphs.md](docs/architecture/graphs.md) |
| A pipeline, its cards and links, what connections can give each other | [pipelines.md](docs/architecture/pipelines.md) |
| Metrics from agents and connections, their store, dashboards | [dashboards.md](docs/architecture/dashboards.md) |
| Sockets, topics, server-pushed state | [realtime.md](docs/architecture/realtime.md) |
| The agent, its tools, model providers, sending data to a third party | [ai.md](docs/architecture/ai.md) |
| Any code | [ENGINEERING.md](ENGINEERING.md) |

What is already done is recorded by the spec
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
| D14 | [windows](docs/architecture/windows.md) |
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
| D43 | [sources/transfer](docs/architecture/sources/transfer.md) |
| D44 | [sources/transfer](docs/architecture/sources/transfer.md) |
| D45 | [sources/transfer](docs/architecture/sources/transfer.md) |
| D46 | [sources/actions](docs/architecture/sources/actions.md) |
| D47 | [sources/content](docs/architecture/sources/content.md) |
| D48 | [sources/content](docs/architecture/sources/content.md) |
| D49 | [sources/downloads](docs/architecture/sources/downloads.md) |
| D50 | [frontend](docs/architecture/frontend.md) |
| D51 | [sources/content](docs/architecture/sources/content.md) |
| D52 | [sources/content](docs/architecture/sources/content.md) |
| D53 | [sources/content](docs/architecture/sources/content.md) |
| D54 | [sources/relations](docs/architecture/sources/relations.md) |
| D55 | [sources/downloads](docs/architecture/sources/downloads.md) |
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
| D73 | [sources/downloads](docs/architecture/sources/downloads.md) |
| D74 | [sources/actions](docs/architecture/sources/actions.md) |
| D75 | [sources/catalog](docs/architecture/sources/catalog.md) |
| D76 | [sources/catalog](docs/architecture/sources/catalog.md) |
| D77 | [querying](docs/architecture/querying.md) |
| D78 | [querying](docs/architecture/querying.md) |
| D79 | [sources/actions](docs/architecture/sources/actions.md) |
| D80 | [services](docs/architecture/services.md) |
| D81 | [jobs](docs/architecture/jobs.md) |
| D82 | [services-runtime](docs/architecture/services-runtime.md) |
| D83 | [services](docs/architecture/services.md) |
| D84 | [services](docs/architecture/services.md) |
| D85 | [services](docs/architecture/services.md) |
| D86 | [services-runtime](docs/architecture/services-runtime.md) |
| D87 | [backups](docs/architecture/backups.md) |
| D88 | [services](docs/architecture/services.md) |
| D89 | [services](docs/architecture/services.md) |
| D90 | [services](docs/architecture/services.md) |
| D91 | [sources/catalog](docs/architecture/sources/catalog.md) |
| D92 | [windows](docs/architecture/windows.md) |
| D93 | [windows](docs/architecture/windows.md) |
| D94 | [workspace](docs/architecture/workspace.md) |
| D95 | [jobs](docs/architecture/jobs.md) |
| D96 | [querying](docs/architecture/querying.md) |
| D97 | [graphs](docs/architecture/graphs.md) |
| D98 | [sources/contract](docs/architecture/sources/contract.md) |
| D99 | [frontend](docs/architecture/frontend.md) |
| D100 | [sources/connecting](docs/architecture/sources/connecting.md) |
| D101 | [sources/connecting](docs/architecture/sources/connecting.md) |
| D102 | [sources/connecting](docs/architecture/sources/connecting.md) |
| D103 | [sources/connecting](docs/architecture/sources/connecting.md) |
| D104 | [sources/connecting](docs/architecture/sources/connecting.md) |
| D105 | [sources/connecting](docs/architecture/sources/connecting.md) |
| D106 | [sources/declared](docs/architecture/sources/declared.md) |
| D107 | [sources/declared](docs/architecture/sources/declared.md) |
| D108 | [sources/declared](docs/architecture/sources/declared.md) |
| D109 | [sources/relations](docs/architecture/sources/relations.md) |
| D110 | [sources/relations](docs/architecture/sources/relations.md) |
| D111 | [grid](docs/architecture/grid.md) |
| D112 | [workspace](docs/architecture/workspace.md) |
| D113 | [notifications](docs/architecture/notifications.md) |
| D114 | [notifications](docs/architecture/notifications.md) |
| D115 | [notifications](docs/architecture/notifications.md) |
| D116 | [grid](docs/architecture/grid.md) |
| D117 | [sources/ddl](docs/architecture/sources/ddl.md) |
| D118 | [sources/actions](docs/architecture/sources/actions.md) |
| D119 | [sources/timescale](docs/architecture/sources/timescale.md) |
| D120 | [sources/timescale](docs/architecture/sources/timescale.md) |
| D121 | [sources/timescale](docs/architecture/sources/timescale.md) |
| D122 | [sources/timescale](docs/architecture/sources/timescale.md) |
| D123 | [sources/operations](docs/architecture/sources/operations.md) |
| D124 | [backend](docs/architecture/backend.md) |
| D125 | [dashboards](docs/architecture/dashboards.md) |
| D126 | [dashboards](docs/architecture/dashboards.md) |
| D127 | [dashboards](docs/architecture/dashboards.md) |
| D128 | [dashboards](docs/architecture/dashboards.md) |
| D129 | [dashboards](docs/architecture/dashboards.md) |
| D130 | [dashboards](docs/architecture/dashboards.md) |
| D131 | [frontend](docs/architecture/frontend.md) |
| D132 | [windows](docs/architecture/windows.md) |
| D133 | [ai](docs/architecture/ai.md) |
| D134 | [ai](docs/architecture/ai.md) |
| D135 | [ai](docs/architecture/ai.md) |
| D136 | [ai](docs/architecture/ai.md) |
| D137 | [ai](docs/architecture/ai.md) |
| D138 | [ai](docs/architecture/ai.md) |
| D139 | [ai](docs/architecture/ai.md) |
| D140 | [ai](docs/architecture/ai.md) |
| D141 | [ai](docs/architecture/ai.md) |
| D142 | [ai](docs/architecture/ai.md) |
| D143 | [workspace](docs/architecture/workspace.md) |
| D144 | [sources/ssh](docs/architecture/sources/ssh.md) |
| D145 | [sources/ssh](docs/architecture/sources/ssh.md) |
| D146 | [sources/ssh](docs/architecture/sources/ssh.md) |
| D147 | [sources/ssh](docs/architecture/sources/ssh.md) |
| D148 | [terminals](docs/architecture/terminals.md) |
| D149 | [terminals](docs/architecture/terminals.md) |
| D150 | [sources/explorer](docs/architecture/sources/explorer.md) |
| D151 | [sources/explorer](docs/architecture/sources/explorer.md) |
| D152 | [sources/explorer](docs/architecture/sources/explorer.md) |
| D153 | [sources/ssh](docs/architecture/sources/ssh.md) |
| D154 | [sources/ssh](docs/architecture/sources/ssh.md) |
| D155 | [windows](docs/architecture/windows.md) |
| D156 | [ai](docs/architecture/ai.md) |
| D157 | [ai](docs/architecture/ai.md) |
| D158 | [ai](docs/architecture/ai.md) |
| D159 | [ai](docs/architecture/ai.md) |
| D160 | [querying](docs/architecture/querying.md) |
| D161 | [sources/transfer](docs/architecture/sources/transfer.md) |
| D162 | [sources/actions](docs/architecture/sources/actions.md) |
| D163 | [sources/transfer](docs/architecture/sources/transfer.md) |
| D164 | [sources/transfer](docs/architecture/sources/transfer.md) |
| D165 | [sources/transfer](docs/architecture/sources/transfer.md) |
| D166 | [sources/transfer](docs/architecture/sources/transfer.md) |
| D167 | [windows](docs/architecture/windows.md) |
| D168 | [sources/transfer](docs/architecture/sources/transfer.md) |
| D169 | [sources/transfer](docs/architecture/sources/transfer.md) |
| D170 | [sources/declared](docs/architecture/sources/declared.md) |
| D171 | [sources/transfer](docs/architecture/sources/transfer.md) |
| D172 | [sources/declared](docs/architecture/sources/declared.md) |
| D173 | [sources/declared](docs/architecture/sources/declared.md) |
| D174 | [pipelines](docs/architecture/pipelines.md) |
| D175 | [pipelines](docs/architecture/pipelines.md) |
| D176 | [pipelines](docs/architecture/pipelines.md) |

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
development, rebuilds fixtures and sample storage and draws the example
declared references between the connections that are already there. A prestart failure prevents
the backend from serving; inspect it with `docker compose logs prestart`.

Backend checks, from `backend/`:

```bash
uv sync
uv run pytest tests/ -q
uv run mypy app
uv run ruff check app tests
uv run lint-imports
```

The suite needs the database; every other server belongs to the tests of one
piece, and a test whose server does not answer is skipped with the command that
starts it. `pytest --require-services` stops the run instead, as CI does. Redis
is `docker compose up -d redis` — not `redis-cache`, which publishes no port.
See [backend.md](docs/architecture/backend.md#tests-and-the-servers-they-need).

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
  `docker compose up -d --build backend`, and `metrics` when collection changed.
- `docker compose up -d db backend` does not start `metrics`: the backend does
  not depend on it. Dashboards still open, and no agent packet or connection
  poll is written. Start it with `docker compose up -d metrics`, or the whole
  stack with `docker compose up -d`.
- The backend is one process (D124). Development's `fastapi dev` is one too, so
  a second worker breaks transactions, result pages and topics where nobody
  working on the code can see it.
- Backend tests wipe users in the development database. Running
  `docker compose up -d db backend` afterwards restores the superuser and
  development samples through prestart.
- Alembic sees only models imported by `app/alembic/env.py`.
- LangGraph's saver `setup()` builds indexes CONCURRENTLY and waits for ever in
  a process holding a transaction; it runs only in `app.prepare_checkpoints`.
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
