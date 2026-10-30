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
with them through one interface: a FastAPI backend in `backend/` and a Vue 3 +
Quasar frontend in `frontend/`, run together with Docker Compose. It began
from the FastAPI full-stack template, which is not a constraint.

Everything needed to work on it is in this repository. Specs in
`docs/decisions/` sometimes mention "the old application": a private
predecessor that is not published. Do not look for it.

Everything is in English: code, comments, UI strings, tests, commits and
documentation.

## Read before changing

| Area | Read first |
| --- | --- |
| A source type, a capability, a node kind, untrusted input, the user's guide | [sources/contract.md](docs/architecture/sources/contract.md) |
| What a catalog shows of a node, searching it, a key space | [sources/catalog.md](docs/architecture/sources/catalog.md) |
| Query documents, SQL execution, results, history, transactions | [querying.md](docs/architecture/querying.md) |
| SQL over files, the DuckDB sandbox behind it | [sources/file-sql.md](docs/architecture/sources/file-sql.md) |
| MySQL and MariaDB, their catalog, values, pages, row and structure edits, console, reports, search, catalog actions, copying tables, backups, metrics | [sources/mysql.md](docs/architecture/sources/mysql.md) |
| SQLite, the file it opens and how, its catalog, what is read from a table's text, values, pages, row edits, structure changes, the table designer, reports, search, catalog actions and console | [sources/sqlite.md](docs/architecture/sources/sqlite.md) |
| ClickHouse, its HTTP interface, its catalog, values, pages, row edits, structure changes, the table designer, reports, search, export, catalog actions and console | [sources/clickhouse.md](docs/architecture/sources/clickhouse.md) |
| MongoDB, the server it reaches, its catalog, how a collection becomes columns, how documents are read and changed, fields and indexes | [sources/mongodb.md](docs/architecture/sources/mongodb.md) |
| Connection options, connection strings, pools, read cache | [sources/connecting.md](docs/architecture/sources/connecting.md) |
| TimescaleDB, extension discovery, hypertables, chunks and policies | [sources/timescale.md](docs/architecture/sources/timescale.md) |
| A source action too long for a request: its plan, review and outcomes | [sources/operations.md](docs/architecture/sources/operations.md) |
| A source made of files, the storage it brings, the explorer over it | [sources/explorer.md](docs/architecture/sources/explorer.md) |
| An SSH server, the server key it trusts, SSH keys and their passphrases, a database reached through an SSH tunnel | [sources/ssh.md](docs/architecture/sources/ssh.md) |
| A terminal, its socket, who may open one, a client program run in a container as one | [terminals.md](docs/architecture/terminals.md) |
| Reading a relation, changing the rows in it | [sources/relations.md](docs/architecture/sources/relations.md) |
| Copying rows between sources, pasting into another connection, copying tables with their structure, a transfer job, loading a file in, exporting every row | [sources/transfer.md](docs/architecture/sources/transfer.md) |
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
| Backend modules, routes, migrations, secrets, database, the server's log | [backend.md](docs/architecture/backend.md) |
| Screens, where state lives, Markdown rendering | [frontend.md](docs/architecture/frontend.md) |
| Any text a person reads, a language, the way it reads, a refusal a route sends | [localization.md](docs/architecture/localization.md) |
| The component kit, colours, layers, a size of text, a weight, a height, an icon size, a theme | [design-system.md](docs/architecture/design-system.md) |
| A page of rows: the grid, downloads, charts | [grid.md](docs/architecture/grid.md) |
| Layout, tabs, dragging, the bar and card at the foot | [workspace.md](docs/architecture/workspace.md) |
| A floating window, the forms in it, detaching a tab, a pair of catalogs | [windows.md](docs/architecture/windows.md) |
| A notification, something waiting for an answer, running work on screen | [notifications.md](docs/architecture/notifications.md) |
| A diagram of nodes and connections, in 2D or 3D | [graphs.md](docs/architecture/graphs.md) |
| A pipeline, its cards, links, run, schedule and history, what connections can give each other | [pipelines.md](docs/architecture/pipelines.md) |
| Metrics from agents and connections, their store, dashboards | [dashboards.md](docs/architecture/dashboards.md) |
| Sockets, topics, server-pushed state | [realtime.md](docs/architecture/realtime.md) |
| The agent, its tools, sending data to a third party, quick chat | [ai.md](docs/architecture/ai.md) |
| Models, provider keys, Jev | [ai-models.md](docs/architecture/ai-models.md) |
| One search over everything, its providers, the field in the header | [search.md](docs/architecture/search.md) |
| A connection's names and files' text kept for search, search by meaning and its model, the search-keeper process, the Search index window | [search-kept.md](docs/architecture/search-kept.md) |
| Any code | [ENGINEERING.md](ENGINEERING.md) |

What is already done is recorded by the spec
index and by git; do not inventory it here or there.

## Decision registry

The wording, reasoning and known deviations live in the linked architecture
files. IDs are stable because specs and commits refer to them. One row per
file; `D247–D262` is every number between, all in that file.

| Home | Decisions |
| --- | --- |
| [sources/contract](docs/architecture/sources/contract.md) | D1, D2, D2a, D2b, D2c, D2d, D8, D13, D20, D21, D98, D183, D264 |
| [backend](docs/architecture/backend.md) | D3–D5, D33, D34, D124, D184 |
| [frontend](docs/architecture/frontend.md) | D6, D7, D50, D99, D131 |
| [sources/actions](docs/architecture/sources/actions.md) | D9, D46, D56, D68, D74, D79, D118, D162, D209, D210 |
| [sources/connecting](docs/architecture/sources/connecting.md) | D10, D15–D17, D31, D100–D105 |
| [design-system](docs/architecture/design-system.md) | D11, D185–D187, D196 |
| [workspace](docs/architecture/workspace.md) | D12, D69, D94, D112, D143 |
| [windows](docs/architecture/windows.md) | D14, D92, D93, D132, D155, D167 |
| [realtime](docs/architecture/realtime.md) | D18, D19 |
| [sources/relations](docs/architecture/sources/relations.md) | D22, D23, D25, D26, D36, D41, D42, D54, D70, D72, D109, D110, D246 |
| [grid](docs/architecture/grid.md) | D24, D28, D35, D67, D111, D116 |
| [sources/ddl](docs/architecture/sources/ddl.md) | D27, D29, D30, D32, D37–D40, D117 |
| [sources/transfer](docs/architecture/sources/transfer.md) | D43–D45, D161, D163–D166, D168, D169, D171, D182 |
| [sources/content](docs/architecture/sources/content.md) | D47, D48, D51–D53, D57, D71 |
| [sources/downloads](docs/architecture/sources/downloads.md) | D49, D55, D73 |
| [sharing](docs/architecture/sharing.md) | D58–D61 |
| [querying](docs/architecture/querying.md) | D62–D66, D160, D206 |
| [sources/catalog](docs/architecture/sources/catalog.md) | D75, D76, D91, D265 |
| [sources/file-sql](docs/architecture/sources/file-sql.md) | D77, D78, D96 |
| [services](docs/architecture/services.md) | D80, D83–D85, D88–D90 |
| [jobs](docs/architecture/jobs.md) | D81, D95 |
| [services-runtime](docs/architecture/services-runtime.md) | D82, D86 |
| [backups](docs/architecture/backups.md) | D87 |
| [graphs](docs/architecture/graphs.md) | D97 |
| [sources/declared](docs/architecture/sources/declared.md) | D106–D108, D170, D172, D173, D195 |
| [notifications](docs/architecture/notifications.md) | D113–D115, D181 |
| [sources/timescale](docs/architecture/sources/timescale.md) | D119–D122, D207, D208, D211 |
| [sources/operations](docs/architecture/sources/operations.md) | D123 |
| [dashboards](docs/architecture/dashboards.md) | D125–D130 |
| [ai](docs/architecture/ai.md) | D133–D139, D141, D142, D158, D159, D223 |
| [ai-models](docs/architecture/ai-models.md) | D140, D156, D157 |
| [sources/ssh](docs/architecture/sources/ssh.md) | D144–D147, D153, D154, D266, D282 |
| [terminals](docs/architecture/terminals.md) | D148, D149, D286 |
| [sources/explorer](docs/architecture/sources/explorer.md) | D150–D152 |
| [pipelines](docs/architecture/pipelines.md) | D174–D180 |
| [search](docs/architecture/search.md) | D197–D205 |
| [search-kept](docs/architecture/search-kept.md) | D212–D222 |
| [localization](docs/architecture/localization.md) | D224–D227, D281 |
| [sources/mysql](docs/architecture/sources/mysql.md) | D228–D245 |
| [sources/sqlite](docs/architecture/sources/sqlite.md) | D247–D263 |
| [sources/clickhouse](docs/architecture/sources/clickhouse.md) | D267–D280 |
| [sources/mongodb](docs/architecture/sources/mongodb.md) | D283–D285, D287, D288 |

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

Demo connections for a full connections panel — the same PostgreSQL under
several names, file storage, Redis and SSH — come from `bun run seed:connectors`,
which reads `.env` and skips names that already exist.

Kept lists for search are read by `search-keeper`, and search by meaning needs
its model, which `docker compose up -d` starts only when `COMPOSE_PROFILES` in
`.env` names `meaning` (D214, D220). A fresh checkout gets its `.env` from
`docker compose -f compose.setup.yml run --rm setup`; Adminer, Mailcatcher
and the test Redis and SSH server are behind `--profile tools`, and naming one starts it.

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
is `docker compose up -d redis` — not `redis-cache`, which publishes no port;
MySQL and MariaDB are `docker compose up -d mysql mariadb`, ClickHouse is
`docker compose up -d clickhouse`, MongoDB is `docker compose up -d mongodb`.
The scenario that provisions the Timescale
`docker compose -f backend/compatibility/timescale/compose.yml up -d v2_30_pg18`
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

E2E scenarios that use the optional Redis, SSH and metrics services skip when
their service is unavailable. Start them with `docker compose up -d redis`,
`docker compose up -d sshd` and `docker compose up -d metrics` respectively.
The scenario that provisions the Timescale metrics store skips by default; set
`E2E_ALLOW_TIMESCALE_START=1` in the environment to opt in.

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
