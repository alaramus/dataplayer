# AGENTS.md

Entry point for coding agents and humans. This file is loaded into every
session, so it holds only what is needed before knowing what the task is: what
the project is, where to read the rest, how to run things, and the traps that
cost time.

- [ENGINEERING.md](ENGINEERING.md) — how code is written, with what enforces
  each rule. **Normative whenever you touch code, whatever the task.** Also
  loaded into every session.
- [docs/migration-roadmap.md](docs/migration-roadmap.md) — what to port next,
  in dependency order, and where the next session should resume.
- `docs/architecture/` — what exists, why it was decided that way, and where it
  falls short. Read the file for the area you are touching.
- `docs/superpowers/specs/` — the full argument behind each decision.
  [README.md](docs/superpowers/specs/README.md) lists them in order.

## What this project is

**DataPlayer** — a platform for connecting to heterogeneous data sources,
exploring them and working with them through one interface.

This repository is a **rewrite** of an older, working application: a Python
aiohttp backend with 70+ data adapters at `C:\Users\maxim\PycharmProjects\dbwebtool`
and a Vue 3 + Quasar frontend at `C:\Users\maxim\PycharmProjects\myquasar`. The
old application works but was written as a student project: no typing, no clear
boundaries between layers, single files grown to thousands of lines.

**We port ideas, not code.** Read the old sources for the shape of a problem and
for decisions that turned out right, then design the new implementation from
scratch. Never copy a file across.

The starting point was `fastapi/full-stack-fastapi-template`. The template is
not a constraint: any part of it may be rewritten or deleted, and most of it
already has been.

Everything in the repository is in **English**: code, comments, docstrings, UI
strings, test names, commit messages and documentation. Known deviation: the
specs dated up to 2026-08-27 in `docs/superpowers/specs/`, and every plan in
`docs/superpowers/plans/`, are working notes in Russian and stay that way as
legacy. Anything written from 2026-08-28 onwards is English, those directories
included; the spec index lists the older titles in translation.

## Where to read what

| You are about to | Read first |
| --- | --- |
| Add or change a source type, the adapter contract, actions, pooling | [docs/architecture/adapters.md](docs/architecture/adapters.md) |
| Add a module, a route, a migration; touch secrets or the database | [docs/architecture/backend.md](docs/architecture/backend.md) |
| Build a screen, touch the component kit, colours or layers | [docs/architecture/frontend.md](docs/architecture/frontend.md) |
| Touch the layout, tabs, dragging or floating windows | [docs/architecture/workspace.md](docs/architecture/workspace.md) |
| Push anything to the client, or add a socket topic | [docs/architecture/realtime.md](docs/architecture/realtime.md) |
| Write any code at all | ENGINEERING.md — already in context |

## What already works

- Sign in; register a connection through a form built from the adapter's own
  schema; check it before and after saving; manage the list of connections.
- Two source types: PostgreSQL (schemas, relations, server-side paging and
  sorting) and the personal file storage every user owns (directories and files;
  a delimited file becomes columns, anything else readable becomes numbered
  lines).
- In that storage: create a folder, rename, delete, upload — one node at a time
  or several at once. What is offered comes from the server for exactly the
  nodes that are ticked, so the screen knows nothing about any particular
  source.
- A connection can be shared with a colleague at one of three levels:
  reading it, changing its rows, changing its shape. Its owner alone edits it,
  deletes it and manages who holds what; an administrator manages accounts and
  reaches nobody's data without a grant.
- Credentials encrypted at rest, never leaving the server. PostgreSQL keeps its
  connections between requests.
- One screen of three columns — connections, catalogs, data — with resizable
  columns, tabs that can be dragged between them, and a layout that survives a
  reload.
- Connections are edited in floating windows, several at once, with the
  connection string composed by the driver and parsed back from a pasted one.
- The state of every connection arrives by itself over one socket, while the
  screen is open. A connection can be switched off: it stays in the list, is
  not probed and cannot be opened.
- Light and dark themes, remembered.
- A relation describes itself: columns with a parsed type, ordered constraints,
  indexes and partitioning. Its structure opens in a tab beside its rows, where
  PostgreSQL columns can be added from a safe type list or explicitly dropped,
  asked to require a value or to take another type from the same list; rows
  that stand in the way are counted and reported rather than turned into a
  failure.
- The row grid filters and ordered multi-sorts on the server, pages up to 500
  rows, remembers its query and column layout, selects and copies exact TSV, and
  renders lossless values by type with a full-value viewer. PostgreSQL cells in
  keyed tables can be edited with optimistic conflict detection; rows can be
  inserted with defaults preserved and selected rows deleted atomically.
- Any bounded grid page can open as a line, bar or pie chart beside its rows;
  the page boundary is explicit and field suggestions stay in the browser.
- A foreign key in the grid leads to the rows it names: the source says where
  they are and builds the predicate, composite keys included.

## Decisions

One line each. Open the file before changing anything they cover; the reasoning
and the known deviations live there.

| # | Decision | Where |
| --- | --- | --- |
| D1 | The adapter type registry lives in code, not in the database | [adapters](docs/architecture/adapters.md) |
| D2 | The adapter contract is a Protocol, and capabilities are optional | [adapters](docs/architecture/adapters.md) |
| D2a | Sources differ by node kind, not by source family | [adapters](docs/architecture/adapters.md) |
| D2b | A driver is a session plus capability modules, composed | [adapters](docs/architecture/adapters.md) |
| D2c | A query is never built from client strings | [adapters](docs/architecture/adapters.md) |
| D2d | What a source cannot do is stated in the answer | [adapters](docs/architecture/adapters.md) |
| D3 | The backend is fully asynchronous | [backend](docs/architecture/backend.md) |
| D4 | Secrets are split by schema, not by hand | [backend](docs/architecture/backend.md) |
| D5 | Everything lives in feature modules, and dependencies point one way | [backend](docs/architecture/backend.md) |
| D6 | Server state lives in vue-query; Pinia holds only client state | [frontend](docs/architecture/frontend.md) |
| D7 | The frontend is Vue 3 with Quasar | [frontend](docs/architecture/frontend.md) |
| D8 | Every user owns one directory, and a file connector cannot leave it | [adapters](docs/architecture/adapters.md) |
| D9 | An action is one object, and the declaration is the callable | [adapters](docs/architecture/adapters.md) |
| D10 | What outlives a request belongs to the application | [adapters](docs/architecture/adapters.md) |
| D11 | A screen asks the kit for meaning, not Quasar for a look | [frontend](docs/architecture/frontend.md) |
| D12 | The screen is a workspace of sections, and the engine knows nothing about the application | [workspace](docs/architecture/workspace.md) |
| D13 | A source type describes itself, and what it can do is derived | [adapters](docs/architecture/adapters.md) |
| D14 | Work opens in resizable floating windows, and there may be several | [workspace](docs/architecture/workspace.md) |
| D15 | The connection string is a capability, and it is only shown | [adapters](docs/architecture/adapters.md) |
| D16 | A way of connecting is a variant of the options, and the union is flat | [adapters](docs/architecture/adapters.md) |
| D17 | A pasted connection string is taken apart by the driver | [adapters](docs/architecture/adapters.md) |
| D18 | The transport does not know a single topic | [realtime](docs/architecture/realtime.md) |
| D19 | A monitor belongs to a user, and lives only while somebody watches | [realtime](docs/architecture/realtime.md) |
| D20 | A switched-off connection is not a source | [adapters](docs/architecture/adapters.md) |
| D21 | A source says where a node lives, and the client never takes an id apart | [adapters](docs/architecture/adapters.md) |
| D22 | A source describes a relation in full, and a column type is an object | [adapters](docs/architecture/adapters.md) |
| D23 | A fetched column states its type and operations, and a cell crosses the boundary as lossless text | [adapters](docs/architecture/adapters.md) |
| D24 | The grid is controlled state around a headless engine, and source operations stay server-side | [frontend](docs/architecture/frontend.md) |
| D25 | A source issues a versioned row handle, and only it can apply an edit | [adapters](docs/architecture/adapters.md) |
| D26 | Insert names supplied columns; bulk delete changes every versioned row or none | [adapters](docs/architecture/adapters.md) |
| D27 | A source publishes column type choices and alone turns them into DDL | [adapters](docs/architecture/adapters.md) |
| D28 | A download is a fresh copy of the bounded visible page, kept in personal storage | [frontend](docs/architecture/frontend.md) |
| D29 | Renaming a column preserves its source identity and lets the source maintain dependencies | [adapters](docs/architecture/adapters.md) |
| D30 | A column default entered by a user is a literal value, never a source expression | [adapters](docs/architecture/adapters.md) |
| D31 | A source opts into bounded read caching, and a successful mutation drops what it cached | [adapters](docs/architecture/adapters.md) |
| D32 | Renaming a catalog node returns its replacement identity, and open work follows it in place | [adapters](docs/architecture/adapters.md) |
| D33 | Access to a connection is a grant of an ordered level, and a route states the level it needs | [backend](docs/architecture/backend.md) |
| D34 | An administrator has rights over accounts, not over data | [backend](docs/architecture/backend.md) |
| D35 | A chart is a closed view over one bounded fetch, not another query language | [frontend](docs/architecture/frontend.md) |
| D36 | A source issues the target of a reference, and the client never pairs the columns | [adapters](docs/architecture/adapters.md) |
| D37 | Changing nullability counts the rows in the way, and the count is the answer | [adapters](docs/architecture/adapters.md) |
| D38 | A type change is composed by the source, and the way is checked before the table is locked | [adapters](docs/architecture/adapters.md) |

Numbers have gaps and suffixes. They are referenced by specs and commit
messages, so they are never renumbered.

## Commands

The database and backend run in Docker. Bring them up first:

```bash
docker compose up -d db backend
```

That is the whole startup procedure: nothing has to be migrated or seeded by
hand. `compose.yml` holds a one-shot `prestart` service that waits for the
server, runs `alembic upgrade head` and creates the first superuser, and
`backend` depends on it with `service_completed_successfully`. In development
`compose.override.yml` points it at `scripts/prestart-dev.sh`, which also writes
the sample files and rebuilds the `demo_lab` PostgreSQL fixture schema from
`sql/`. A failing migration or fixture therefore stops the backend from starting
rather than letting it serve against an older schema; the reason is in
`docker compose logs prestart`.

Useful extras:

```bash
docker compose logs -f backend
docker compose up -d adminer      # database UI on :8080
docker compose up -d mailcatcher  # captured outgoing mail on :1080
docker compose down -v            # drop the volume and start from an empty database
```

### Backend

```bash
cd backend
uv sync                     # install dependencies
uv run pytest tests/ -q     # tests (needs the db container)
uv run mypy app             # strict mode, configured in pyproject.toml
uv run ruff check app tests
uv run lint-imports         # direction of dependencies between packages
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "message"
```

### Frontend

```bash
cd frontend
bun run dev          # dev server on http://localhost:5173
bun run build        # production build into backend/app/frontend
bun run type-check   # vue-tsc; needs real Node, see the trap below
bun run lint
bun run test:unit    # Vitest
bunx playwright test # end-to-end, needs db + backend + dev server
```

### Regenerating the API client

```bash
bash scripts/generate-client.sh
```

Dumps OpenAPI from the backend and regenerates `frontend/src/client`. Run it
after any change to backend routes or schemas.

### Checking the documentation

```bash
bash scripts/check-docs.sh
```

Every relative link resolves, every decision in the table above has exactly one
home in `docs/architecture/`, and this file stays under 24 KB.

### Continuous integration

`.gitlab-ci.yml` runs the same commands on a push: the backend checks against a
postgres service, the frontend checks under Node rather than bun, and the
documentation check. The end-to-end suite is not in the pipeline — it needs the
database, the backend and a dev server at once — so it is run locally.

## Traps

Each of these cost time to find. They are not obvious from the code.

**Running the backend natively on Windows does not work.** psycopg 3 in async
mode is incompatible with `ProactorEventLoop`, which Python selects by default
on Windows. `app/core/db.py` exposes `loop_factory` and it is wired into the
standalone scripts and into pytest, but uvicorn has no such hook. Use Docker.

**A connection pool belongs to the event loop that created it.** The application
has one loop per process, so this never shows in production; pytest used to give
every test its own loop, and a pool built in one test then failed inside the
driver in the next. Tests share one loop
(`asyncio_default_test_loop_scope = "session"`). A background script that opens
its own loop must not be handed a store built in another.

**`vue-tsc` has two ways of checking nothing at all, and both look clean.** Under
the bun runtime it fails to register the `.vue` extension, so every component
drops out of the compiler program — measured: 4 files under Node, 0 under bun. On
Windows the `.cmd` shim invokes Node, so that half is hidden. The other half is
configuration: `vue-tsc --noEmit` against `tsconfig.json`, which lists project
references and `"files": []`, reads no file at all and exits 0. `type-check`
therefore runs `vue-tsc -b --force`. If a check has never been seen to fail,
break something on purpose and confirm that it does.

**Running the backend test suite wipes all users**, including the superuser,
because the tests share the development database. `docker compose up -d db
backend` restores them: `prestart` runs on every `up` and `init_db` is
idempotent.

**A personal directory starts empty**, and `frontend/tests/files.spec.ts` expects
a known set of samples. `scripts/prestart-dev.sh` writes them on every `up`, so
this is only a manual step when the stack is already running:

```bash
docker compose exec backend python -m app.seed_storage
```

The same script removes the home directories of users that no longer exist —
wiping the table underneath the application does not take their files with it.
Only a real directory named after a user id is a candidate; anything else is
reported and left alone. Seeding is deliberately absent from
`scripts/prestart.sh`: sample files have no place in a deployment.

**Alembic only sees models whose module is imported by `app/alembic/env.py`.** A
model in a new module has to be added to the import list there, or autogenerate
will quietly propose dropping its table.

**`docker compose up -d` does not pick up backend code changes.** The
`develop.watch` block in `compose.override.yml` only applies under
`docker compose watch`; with a plain `up` the code is baked into the image. After
changing the backend, rebuild — otherwise the container keeps serving an older
API and the failure looks like a routing bug. This covers migrations too:
`prestart` runs from the same image, so a new revision file is invisible until
the image is rebuilt.

```bash
docker compose up -d --build backend
```

**A shell script under `backend/scripts/` must keep LF line endings.** It is
copied into the image verbatim and run by bash, which reads a trailing `\r` as
part of the command: `prestart-dev.sh` rewritten with CRLF failed with
`bash: scripts/prestart.sh: No such file or directory`, naming a file that was
plainly there. `.gitattributes` pins `*.sh` to `eol=lf`, but that only applies
when git writes the file. `file backend/scripts/*.sh` says which ones are wrong.

The same rewrite is worth watching on any tracked text file. AGENTS.md once went
in as CRLF and turned a five-line edit into a 597-line diff. `git show :FILE |
file -` says what is actually about to be stored.

**A local test run reads `../.env`, and CI has none.** Settings name that file,
so anything the developer keeps there — `FASTAPI_ENV`, `SMTP_HOST`,
`EMAILS_FROM_EMAIL` — silently fills the gaps in a run started from `backend/`.
Two pipelines went red on variables that a local run appeared to prove present.
A rehearsal that means anything uses a checkout without `.env`, on Linux:

```bash
git archive HEAD | tar -x -C /tmp/rehearsal
docker run --rm --network ci --network-alias … -w /repo/backend \
  ghcr.io/astral-sh/uv:bookworm-slim bash -c "uv sync --frozen && …"
```

**The whole end-to-end suite needs a dev server that is already warm.**
`playwright.config.ts` starts `bun run dev` itself, and four workers then hit a
Vite that is still compiling: the first two dozen scenarios time out inside
`login` on `page.waitForURL`, which reads exactly like a wiped superuser. Two
full runs failed that way and a third passed 89/89 with nothing changed. Start
the server first, load one spec against it, then run the suite pointed at it:

```bash
PLAYWRIGHT_BASE_URL=http://localhost:5173 bunx playwright test
```

**A closed port is refused at once on Linux and left hanging on Windows.** A
test that wants a timeout cannot point at one: it would assert about the
platform. `tests/utils/network.py` listens without accepting, so the handshake
completes from the backlog and the client waits for a greeting that never
comes. The 4 tests that skip on Windows — symlinks, file modes — run in CI, so
a suite green here is not a suite green there either.

**psycopg reads a literal `%` as a placeholder whenever parameters are
supplied**, even an empty tuple. A query with `LIKE 'pg_%'` and no bindings must
pass no parameters at all, not `()`.

**Quasar forwards `data-testid` onto the `<input>` element**, not onto the field
root. Test selectors address the input directly; a nested `input` locator finds
nothing.

**Connection checks run on the server.** In end-to-end tests the database host
must be written as the backend container sees it — `db` inside the compose
network, not `localhost`.

**A blocking call inside an async handler stalls the whole event loop.**
`send_email` talks to SMTP synchronously and is wrapped in `run_in_threadpool`.
Any new blocking code needs the same treatment.

## Working rules

1. **Write tests with the change, but run validation only with the user's
   explicit approval.** Several related changes may be accumulated before
   validation. Do not automatically run tests, linters, type checks, builds or
   end-to-end checks. When changes are ready to validate, report the proposed
   commands and their scope, then wait for approval. A request that explicitly
   asks to implement and test in the same task counts as approval. Prefer
   targeted checks; run a full relevant suite only when the user approves it.
2. **Never claim something works without running the check and reading the
   output.** If validation was not approved or run, say so explicitly. A green
   unit test is not evidence the user sees the result.
3. **`frontend/src/client` is generated.** Never edit it; regenerate with
   `bash scripts/generate-client.sh`.
4. **`.env` is not tracked.** A new setting goes into `.env.example` too.
5. **A decision that shaped the code is written down** — one line in the table
   above, the reasoning in `docs/architecture/`, the full argument in a spec.
   Where the code knowingly falls short, it is listed as a known deviation next
   to the decision it departs from, not left to be rediscovered.

A change is ready for validation when its implementation and tests are written.
It is verified only after every user-approved command in "What holds it up" in
ENGINEERING.md touching the affected side is clean.

## What comes next

Sub-projects 1–6 and the workspace rounds are done; see
[the spec index](docs/superpowers/specs/README.md) for what each settled.

The first data and structure editing rounds are done: update, insert, atomic
bulk delete, and add/drop column. Further DDL starts only after its safe
vocabulary and dependency behaviour are specified; this is not a generic SQL editor.

Phase 1.1 and the first two slices of 1.2 are done: navigating by a foreign
key, changing column nullability (D37) and changing a column's type (D38). The
next slice is source-owned index creation and removal.
