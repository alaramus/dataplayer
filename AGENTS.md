# AGENTS.md

This is the entry point for coding agents and humans: what the project is,
what has been decided, and what trips people up. Other instruction files point
here instead of duplicating it.

- [ENGINEERING.md](ENGINEERING.md) — how code is written, with what enforces
  each rule. **Normative whenever you touch code, whatever the task.**
- `docs/superpowers/specs/` — the full argument behind each decision, in
  Russian.

## What this project is

**DataPlayer** — a platform for connecting to heterogeneous data sources,
exploring them and working with them through one interface.

This repository is a **rewrite** of an older, working application:

| Part | Old location | Stack |
| --- | --- | --- |
| Backend | `C:\Users\maxim\PycharmProjects\dbwebtool` | Python, aiohttp, 70+ data adapters, LangGraph agent |
| Frontend | `C:\Users\maxim\PycharmProjects\myquasar` | Vue 3, Quasar |

The old application works but was written as a student project: no typing, no
clear boundaries between layers, single files grown to thousands of lines.

**We port ideas, not code.** Read the old sources for the shape of a problem
and for decisions that turned out right, then design the new implementation
from scratch. Never copy a file across.

The starting point of this repository was `fastapi/full-stack-fastapi-template`.
The template is not a constraint: any part of it may be rewritten or deleted.
Most of it already has been.

### Language

Everything in the repository is in **English**: code, comments, docstrings, UI
strings, test names, commit messages and documentation. The only exception is
`docs/superpowers/`, which holds working notes in Russian.

## Current state

A user can sign in, register a connection through a form built from the
adapter's own schema, check the connection before and after saving, manage the
list of connections, browse a connection's catalog and read rows in a paged
grid. Two source types exist: PostgreSQL — schemas down to columns, with
server-side paging and sorting — and the personal file storage every user
owns, where the catalog is directories and files and a delimited file becomes
columns while anything else readable becomes numbered lines. In that storage a
user can also create a folder, rename, delete and upload a file: the buttons
offered for a node come from the server, so the screen has no knowledge of any
particular source. Credentials are encrypted at rest and never leave the
server, and a source that has connections keeps them between requests. Every
screen is built from one component kit, and what a screen may not reach for is
a lint error rather than a convention.

### What exists

```
backend/app/
├── adapters/            source types: contract, registry, drivers
│   ├── protocol.py      DataAdapter, SupportsCatalog, SupportsFetch, AdapterError
│   ├── catalog.py       CatalogNode: a union discriminated by kind; NodeKind
│   ├── fetch.py         FetchRequest, FetchResult, closed set of predicates
│   ├── actions.py       Action, ActionSet, SupportsActions, transports, refusals
│   ├── resources.py     ResourceStore: what outlives a request; Pooling
│   ├── registry.py      type registry, AdapterContext, secret_field_names
│   ├── routes.py        GET /adapter-types
│   ├── postgres/        session.py, pool.py, catalog.py, fetch.py,
│   │                    adapter.py (facade)
│   └── file/            session.py (root and containment), catalog.py,
│                        fetch.py, readers.py, actions.py, adapter.py (facade)
├── connectors/          user connections
│   ├── models.py        Connector + API schemas
│   ├── crud.py          database access only
│   ├── service.py       option splitting, adapter construction
│   └── routes.py        CRUD + connection checks
├── users/               users and authentication
│   ├── models.py        User, User* schemas, Token, NewPassword
│   ├── crud.py          database access only
│   ├── deps.py          CurrentUser, get_current_active_superuser
│   ├── tokens.py        password reset tokens
│   ├── storage.py       personal directory of a user
│   ├── bootstrap.py     init_db: creates the first superuser
│   ├── routes.py        /users
│   ├── auth_routes.py   /login, /password-recovery, /reset-password
│   └── private_routes.py
├── system/              operational routes: /utils health check, test email
├── seed_storage.py     dev tool: sample files into a personal directory
├── core/                depends on nothing else in the app
│   ├── crypto.py        AES-GCM for connector secrets
│   ├── db.py            async engine, session, SessionDep, loop_factory
│   ├── schemas.py       Message, get_datetime_utc
│   ├── email.py         sending and templating
│   ├── config.py        settings
│   └── security.py      passwords and JWT
├── api/main.py          router aggregation only
└── main.py              application assembly; the lifespan owns the store

frontend/src/
├── client/              generated from OpenAPI, never edited by hand
├── shared/
│   ├── ui/              the component kit every screen is built from;
│   │                    tokens.ts turns meaning into Quasar props,
│   │                    useToast and useConfirm replace $q, index.ts is
│   │                    the one import path
│   ├── api/             client setup, and one reading of an API error
│   ├── auth/            the session, watched across tabs
│   ├── SchemaForm/      JSON Schema to form, framework-independent core
│   └── testing/         helpers for tests, not shipped by any screen
├── stores/              Pinia: client-side state only
└── features/
    ├── auth/
    ├── catalog/         lazy tree, row grid, and the actions a node admits;
    │                    treeNodes.ts, rows.ts and actions.ts are pure mappers
    ├── connectors/
    └── dev/             /ui-kit, the showcase of the kit; dev builds only
```

### API

```
POST   /api/v1/login/access-token
GET    /api/v1/adapter-types/
POST   /api/v1/connectors/
GET    /api/v1/connectors/
GET    /api/v1/connectors/{connector_id}
PATCH  /api/v1/connectors/{connector_id}
DELETE /api/v1/connectors/{connector_id}
POST   /api/v1/connectors/{connector_id}/check
POST   /api/v1/connectors/check-draft
GET    /api/v1/connectors/{connector_id}/catalog
POST   /api/v1/connectors/{connector_id}/fetch
GET    /api/v1/connectors/{connector_id}/actions
POST   /api/v1/connectors/{connector_id}/actions/{action_name}
POST   /api/v1/connectors/{connector_id}/actions/{action_name}/file
```

## Decisions that shape the code

These were argued through and are not to be reversed casually. Full reasoning
lives in `docs/superpowers/specs/2026-08-15-connector-registry-design.md`.

**D1. The adapter type registry lives in code, not in the database.** Each
source type is a driver class plus a Pydantic options schema next to it,
registered by a decorator. There is no `adapter` table; `Connector.adapter_type`
is a plain string key. Adding a source type needs no migration. The old
application stored a driver class name in a row and resolved it dynamically,
which is exactly why it has no typing and a 3685-line options file.

**D2. The adapter contract is a `typing.Protocol`, not a base class, and
capabilities are optional.** `DataAdapter` requires only
`check_connection()`. Everything else is a separate `runtime_checkable`
protocol — `SupportsCatalog` and `SupportsFetch` today — that a route checks
before using; an adapter that lacks the capability answers 501 instead of
faking it. A queue has
no columns, an object store has no SQL, so a contract demanding everything
would force meaningless implementations.

**D2b. A driver is a session plus capability modules, composed.**
`postgres/session.py` knows how to reach the server and nothing else;
`postgres/catalog.py` knows what to ask and nothing about connections;
`postgres/adapter.py` is a thin facade. A new capability is a new module, not
more lines in one class.

Inheritance was considered — a base driver with business logic layered on top,
as in the old application — and rejected on the evidence of that application:
it split exactly that way, moved backups, monitoring, extensions, replication
and the producer into their own files, and `postgres_extended_adaptor.py` still
reached 1243 lines. One cut cannot absorb growth that happens along many
capability axes at once, and a single inheritance chain forces them into one
line: that is how the old code ended up four base classes deep.

**D2a. Sources differ by node kind, not by source family.** `list_children()`
walks a tree one level at a time, which suits an SQL database and an object
store equally. What varies is the node, and `CatalogNode` is a discriminated
union: only `id`, `name` and `has_children` are shared, so a key cannot pick up
a second meaning — in the old application `schema` held a database schema name
for PostgreSQL and the literal `"directory"` for S3. Grouping sources into
families was considered and rejected: the boundary is arbitrary for ClickHouse,
Kafka, Sheets or parquet-on-S3, and misclassifying a source is exactly what
broke before. One source may contain nodes of several kinds.

Adding a kind means adding a class to the union. `list_children()` raises
`AdapterError` rather than returning an empty list on failure: an empty node and
a broken query must stay distinguishable.

**D2c. A query is never built from client strings.** Filters are a closed set
of predicates, column names are validated against the relation before anything
is assembled, identifiers go through `psycopg.sql.Identifier` and values through
placeholders. `limit` has a default and a ceiling. The old application formatted
a template with client input and additionally accepted a raw SQL fragment,
guarded only by a blacklist; it also defaulted to `limit=-1`, meaning no limit.

Paging reports `has_more` by reading one row past the page rather than running
`COUNT(*)`; the approximate total already arrives on the catalog node. The old
application smuggled an exact count in as a pseudo-column named
`____total_count____` that clients had to know to discard.

**D2d. What a source cannot do is stated in the answer.** `FetchResult`
carries `sortable` and `filterable`. A file has no index to order by and the
columns of a CSV have no types, so the file source answers `false` and refuses
a request that asks for either. The grid learns from the first answer and stops
offering what the source cannot do — without the frontend ever branching on the
type of the source. The same reasoning covers the missing row estimate: a file
has none, so the grid pages by `has_more` alone.

Sorting a page in memory and calling it sorted was rejected: the order would
depend on where the reader stopped. Reading the whole file up to a size ceiling
was rejected too — the answer would then depend on the size of the file.

**D8. Every user owns one directory, and a file connector cannot leave it.**
`USER_STORAGE_ROOT / <user_id>` is created when the user is created. The root
of a file connector is composed by the server from the owner of the connector;
the only option is a folder inside it. A client can name a path but never a
root, and every path is checked against the root before anything is opened —
one rule, in one place. The old application checked containment in one branch
of one method, and the check let through any ancestor of the root, so the tree
could be walked up to `/`.

**D9. An action is one object, and the declaration is the callable.** A name,
a title, the kinds of node it applies to, a Pydantic model of its parameters
and the implementation live in one class; a driver hands out those objects and
a route calls them. Nothing that is not in the set resolves. Full reasoning in
`docs/superpowers/specs/2026-08-21-action-registry-design.md`.

The old application dispatched `getattr(connector, action)(**request_body)`
guarded only by `hasattr`, so every public method of a driver was callable by
name from a client, and its 765-line table of supported actions took no part in
the guard — it decorated the interface while the guard let through anything
that happened to exist.

Three consequences worth stating separately:

- **What a node admits is asked of the server, per node.** `GET
  /connectors/{id}/actions?node_id=…`; the same call decides what the client is
  offered and what the server allows, so the two cannot drift. Applicability
  depends on state as well as kind: the root of a connector is an ordinary
  directory that may not be renamed or removed, and the driver leaves those
  actions out of the answer.
- **The transport is a protocol, not a flag.** An action that carries a file
  satisfies `TakesFile`; `takes_file` in the API answer is an `isinstance`
  check, derived the way secret fields are derived from `SecretStr`. There are
  two routes because HTTP has two shapes of body, and each refuses an action of
  the other transport with 415.
- **What to re-read is in the answer.** `ActionResult.reload_node_id` names the
  branch that changed, rather than the client inferring it from the name of the
  action.

**D10. What outlives a request belongs to the application; what it holds
belongs to a driver.** An adapter is built per request and cannot own a
connection pool. `adapters/resources.py` is a container of long-lived objects
that names no driver, created and closed by the lifespan and handed to drivers
through `AdapterContext.pooling`; `postgres/pool.py` holds every psycopg
decision about pooling. Full reasoning in
`docs/superpowers/specs/2026-08-21-connection-pool-design.md`.

A module-level dictionary inside the driver was rejected: the application would
reach for it rather than be handed it, and closing it at shutdown would make
application assembly name one driver by hand. Pooling above all adapters was
rejected earlier, by sub-project 6 — a file source has no connection at all.

- **The key is the connector plus a hash of its options**, so editing a
  password produces a different pool by itself. An invalidation step elsewhere
  is a step that can be forgotten, and a forgotten one means working with
  credentials the user has already changed.
- **A pool loses the reason it could not connect.** It reports only that it had
  nothing to hand out, which would turn a wrong password into "could not reach
  the server". On the failure path, and only there, the session connects once
  directly to learn the real reason.
- **Checks are never pooled.** A check is meant to exercise the credentials,
  and a draft has no identity to key anything by.

**D3. The backend is fully asynchronous.** `AsyncSession`, `async def`
throughout, psycopg 3 in async mode. The application is network-I/O bound by
definition.

**D4. Secrets are split by schema, not by hand.** Fields declared as
`SecretStr` go into the encrypted `Connector.secrets` blob; everything else
goes into the `config` jsonb column. No list of secret fields exists anywhere,
so a field cannot be forgotten. `CONNECTOR_SECRET_KEY` is deliberately separate
from `SECRET_KEY`: rotating the latter only logs everyone out, rotating the
former requires migrating stored data.

**D5. Everything lives in feature modules, and dependencies point one way.**
The flat layer inherited from the template — `app/models.py`, `app/crud.py`,
`app/utils.py`, `app/api/deps.py`, `app/api/routes/` — is gone. `core` depends
on nothing else in the application, `users` depends on `core`, and `connectors`
and `adapters` depend on `core` and `users`. There are no arrows back. That is
why `init_db` lives in `app/users/bootstrap.py` rather than in `core/db.py`:
creating the first superuser is a users concern, and keeping it in core would
have made core import users.

**D6. Server state lives in vue-query; Pinia holds only client state.** The old
frontend spread server data across Pinia stores, each with its own cache and
its own invalidation, and that is where its desynchronisation bugs come from.

**D11. A screen asks the kit for meaning, not Quasar for a look.** Every
component with a choice of appearance is wrapped once in `shared/ui`, and a
screen says `variant="danger"` rather than `flat color="negative"`;
`tokens.ts` is the only place that turns one into the other, and it is plain
functions, so the mapping is tested without mounting anything. Full reasoning
in `docs/superpowers/specs/2026-08-22-shared-ui-kit-design.md`.

It is not a facade over Quasar: what has no choice of appearance
(`q-icon`, `q-separator`, `q-td`, `q-form`) and what has one consumer
(`q-layout`, `q-tree`) stays as it is. Undeclared attributes fall through, so
a rare case does not force a change to the kit — and `data-testid` keeps
landing where Quasar puts it, which is what the existing tests address.

Three consequences worth stating separately:

- **The rule is a lint rule, not a habit.** `vue/no-restricted-html-elements`
  forbids, outside `shared/ui`, exactly those `q-*` that have a replacement,
  in both spellings Vue accepts — matching only `q-btn` would let `<QBtn>`
  walk past. `useQuasar` is forbidden in screens too, now that `useToast` and
  `useConfirm` exist.
- **The kit documents itself at `/ui-kit`**, a route registered only under
  `import.meta.env.DEV`. It renders the real components, so it breaks when one
  of them does; a test compares the page against the files in `shared/ui` so a
  component cannot be added without a demonstration.
- **Reading an API error is one function.** `shared/api/errors.ts` — three
  screens had their own copy, and they had already drifted: only the grid
  understood a validation list.

**D7. The frontend is Vue 3 with Quasar.** The value of the rewrite is backend
architecture and end-to-end typing; the UI kit was never the problem. The
typed client generated from OpenAPI is kept — it does not depend on the
framework.

## Commands

The database and backend run in Docker. Bring them up first:

```bash
docker compose up -d db backend
```

That is the whole startup procedure: nothing has to be migrated or seeded by
hand. `compose.yml` holds a one-shot `prestart` service that waits for the
server, runs `alembic upgrade head` and creates the first superuser, and
`backend` depends on it with `service_completed_successfully`, so the
application starts only after the database is at head. Compose re-runs the
service on every `up`, so a new migration is applied by bringing the stack up
again. In development `compose.override.yml` points it at
`scripts/prestart-dev.sh`, which additionally writes the sample files.

A failing migration therefore stops the backend from starting rather than
letting it serve against an older schema. The reason is in one place:

```bash
docker compose logs prestart
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

## Traps

Each of these cost time to find. They are not obvious from the code.

**Running the backend natively on Windows does not work.** psycopg 3 in async
mode is incompatible with `ProactorEventLoop`, which Python selects by default
on Windows. `app/core/db.py` exposes `loop_factory` and it is wired into the
standalone scripts and into pytest, but uvicorn has no such hook. Use Docker.

**A connection pool belongs to the event loop that created it.** The
application has one loop per process, so this never shows in production; pytest
used to give every test its own loop, and a pool built in one test then failed
inside the driver in the next. Tests share one loop
(`asyncio_default_test_loop_scope = "session"` in `pyproject.toml`), matching
how the application runs. A background script that opens its own loop must not
be handed a store built in another.

**`vue-tsc` has two ways of checking nothing at all, and both look clean.**
Under the bun runtime it fails to register the `.vue` extension, so every
component drops out of the compiler program and imports like `@/App.vue` appear
missing — measured: 4 files under Node, 0 under bun. On Windows the `.cmd` shim
invokes Node, so that half is hidden. The other half is the configuration:
`vue-tsc --noEmit` against `tsconfig.json`, which lists project references and
`"files": []`, reads no file at all and exits 0. `type-check` therefore runs
`vue-tsc -b --force`, which follows the references. If a check has never been
seen to fail, break something on purpose and confirm that it does. The
`oven/bun:1` image has no real Node, which is why `bun run build` performs only
`vite build`.

**Running the backend test suite wipes all users**, including the superuser,
because the tests share the development database. Bringing the stack up again
restores them — `prestart` runs on every `up` and `init_db` is idempotent:

```bash
docker compose up -d db backend
```

**A personal directory starts empty**, and the end-to-end scenario
`frontend/tests/files.spec.ts` expects a known set of samples rather than
whatever a previous run left behind. `scripts/prestart-dev.sh` writes them on
every `up`, so this is only a manual step when the stack is already running:

```bash
docker compose exec backend python -m app.seed_storage
```

Seeding is deliberately absent from `scripts/prestart.sh`: sample files have no
place in a deployment.

**Alembic only sees models whose module is imported by `app/alembic/env.py`.**
A model in a new module has to be added to the import list there, or
autogenerate will quietly propose dropping its table.

**`docker compose up -d` does not pick up backend code changes.** The
`develop.watch` block in `compose.override.yml` only applies under
`docker compose watch`; with a plain `up` the code is baked into the image.
After changing the backend, rebuild — otherwise the container keeps serving an
older API and the failure looks like a routing bug:

```bash
docker compose up -d --build backend
```

This covers migrations too. `prestart` runs from the same image, so a new
revision file is invisible to it until the image is rebuilt, and `up` then
reports the database as already at head.

**A shell script under `backend/scripts/` must keep LF line endings.** It is
copied into the image verbatim and run by bash, which reads a trailing `` as
part of the command: `prestart-dev.sh` rewritten with CRLF failed with
`bash: scripts/prestart.sh: No such file or directory`, naming a file that was
plainly there. `.gitattributes` pins `*.sh` to `eol=lf`, but that only applies
when git writes the file — an editor or a script that rewrites it in the
working tree on Windows can still break the container. `file backend/scripts/*.sh`
says which ones are wrong.

**psycopg reads a literal `%` as a placeholder whenever parameters are
supplied**, even an empty tuple. A query with `LIKE 'pg_%'` and no bindings
must pass no parameters at all, not `()`.

**Quasar forwards `data-testid` onto the `<input>` element**, not onto the
field root. Test selectors address the input directly; a nested `input`
locator finds nothing.

**Connection checks run on the server.** In end-to-end tests the database host
must be written as the backend container sees it — `db` inside the compose
network, not `localhost`.

**A blocking call inside an async handler stalls the whole event loop.**
`send_email` talks to SMTP synchronously and is wrapped in
`run_in_threadpool`. Any new blocking code needs the same treatment.

## Working rules

The rules themselves, and what enforces each of them, are in
[ENGINEERING.md](ENGINEERING.md). Four things worth knowing before the first
line of code:

1. **Tests first.** Every task so far went failing test → implementation →
   passing test → commit.
2. **Never claim something works without running the check and reading the
   output.** A green unit test is not evidence the user sees the result.
3. **`frontend/src/client` is generated.** Never edit it; regenerate with
   `bash scripts/generate-client.sh`.
4. **`.env` is not tracked.** A new setting goes into `.env.example` too.

A change is ready when every command in "What holds it up" touching the
affected side is clean.

## What comes next

From the design document, in order:

| # | Sub-project |
| --- | --- |
| 7+ | Realtime, AI, data grid |

Sub-project 6 is done: the file source is the second type, and it was
deliberately not SQL. What it exposed is recorded above as D2d, and one thing
it settled belongs to 4б: a file source has no connection at all, so pooling
cannot be a mechanism above all adapters — it belongs to the session module of
a driver that has one.

Sub-project 4b is done: PostgreSQL keeps its connections between requests
(D10). The place it created — a container the application owns and drivers ask
for things by key — is where anything else that must outlive a request belongs:
a websocket registry, a running agent, a cached model.

Sub-project 5 is done: actions are a registry (D9), and personal storage got
the first four. Two things it settled are worth carrying forward. A capability
protocol is now the way a source says what it cannot do — 501 for the whole
capability, and per-node applicability inside it — which is the shape any later
capability should take. And an action that carries bytes needed a second route
rather than a second body type; download in sub-project 7 answers with bytes
and will need the same treatment in the other direction.

The shared UI kit is done, ahead of 7 rather than as part of it: every screen
now builds from `shared/ui`, and a lint rule keeps the next one from going
around it (D11). A new screen starts by looking at `/ui-kit`.

Each sub-project gets its own design document, its own plan and its own
iteration.

## Known deviations

Where the code knowingly differs from what the documents describe, or falls
short of what it should be. Listed so it is not rediscovered as a surprise.

- **SSRF in `check-draft`.** The endpoint opens a TCP connection to an address
  supplied by the client, which lets an authenticated user map the internal
  network by response timing and error kind. Mitigated by a hard timeout and
  uniform error messages; a host allow-list is the remaining fix.
- **A broken connector can wait two timeouts.** When the pool cannot hand out a
  connection, the session connects once more to find out why, so that a wrong
  password is not reported as an unreachable host. The successful path pays
  nothing; a broken one may wait up to twice the connection timeout.
- **A pool outlives the connector it belonged to.** Editing the options or
  deleting the connector leaves the old pool holding open connections until it
  ages out — up to `POOL_MAX_IDLE_SECONDS`. That is the price of having no
  invalidation step to forget; nothing can be read through it, because
  reaching it needs a key nobody composes any more.
- **Pools are per process and per connector.** Four workers may hold four times
  `POOL_MAX_SIZE` connections to the same database, and nothing coordinates
  them. There is also no limit on how many requests one user may have in
  flight.
- **Nothing reports on the pools.** How many exist, how busy they are and what
  was evicted is invisible; `application_name` in `pg_stat_activity` is the
  only way to see them from outside.
- **Catalog children are not paginated.** Fine for PostgreSQL, where the count
  is bounded. A directory is not bounded, so the file source refuses to list one
  holding more than 2000 entries rather than truncating it silently. Adding a
  cursor changes the contract for every adapter.
- **A deep offset over a file costs a full scan.** Paging a file means skipping
  `offset` lines every time, because a file has no index. Bounded by the limit
  ceiling, and acceptable while pages are read in order.
- **A file can be uploaded but not downloaded.** Reading bytes back out is
  sub-project 7, so a picture put into personal storage can be listed and
  deleted but not opened.
- **Nothing moves or copies.** An action works inside one node of one
  connector; moving a file to another folder means downloading and uploading it
  again.
- **Personal storage has no quota.** Nothing counts what a user has stored;
  only a single upload is bounded, by `MAX_UPLOAD_BYTES`.
- **A conflict is detected, then acted upon.** `create_folder`, `rename` and
  `upload` check that a name is free and then use it; another writer in that
  gap wins. The window is small and the directory belongs to one user, so it is
  left rather than papered over with a lock.
- **An upload gives no progress and cannot be resumed.** A large file is one
  request that either finishes or leaves nothing behind.
- **Nothing records what was done.** Actions change files without an audit
  trail; there is no history to show a user what they deleted.
- **`.env` is in the git history.** It was tracked before being removed, so the
  values it held at the time are still recoverable from earlier commits. They
  are development placeholders, but a real deployment must not reuse them.
- **Part of the UI kit has one consumer** (`AppBadge`, `AppFileInput`,
  `AppSpinner`, `AppTooltip`). A knowing departure from "generalise on the
  second or third use": the point of the kit is predictability as the number
  of screens grows, not the smallest diff today.
- **Attribute fall-through is a way around the kit.** Nothing stops a screen
  passing `color="purple"` straight to the Quasar component underneath. Only
  review catches it.
- **`q-tree` is outside the kit**, so the catalog tree is still Quasar's, and
  sub-project 7 will have to decide about it again.
- **There is no dark theme.** Tokens are build-time sass variables; switching
  at runtime needs CSS custom properties and its own task.
- **D2b — a driver is a session plus capability modules — rests on review.**
  There is no check that a capability module keeps out of connection handling.
- **The reuse rules rest on review.** No machine flags the third similar thing
  in a diff.
