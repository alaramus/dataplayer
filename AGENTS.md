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
grid. Two source types exist: PostgreSQL — schemas, relations and server-side
paging and sorting — and the personal file storage every user owns, where the
catalog is directories and files and a delimited file becomes columns while
anything else readable becomes numbered lines. In that storage a user can also
create a folder, rename, delete and upload a file, one node at a time or
several at once: what is offered comes from the server for exactly the nodes
that are ticked, so the screen has no knowledge of any particular source.
Credentials are encrypted at rest and never leave the server, and a source that
has connections keeps them between requests. Every screen is built from one
component kit, and what a screen may not reach for is a lint error rather than
a convention. All of that happens in one screen: three columns that are always
there — the connections, the catalog of the one picked, and the rows of a node
in tabs beside each other — resizable, bounded by the window so each scrolls
inside itself, and the layout a user arrives at is the one they left.

Adding a connection now starts at a catalog of source types rather than at a
dropdown: a sidebar of categories with counts, a search that matches what a
type can do as well as what it is called, tiles, and a panel that says — in
words the server derived from the driver itself — what the type lets a user
see and change. Picking one leads to the form, which states the type instead of
offering a choice of it, and can step back to the catalog. Editing an existing
connection skips the first window entirely.

A connection is a row of three things — the icon of its type, its name, and
what the last check said — and everything else about it lives in the one window
that icon opens, from either of the two columns that show it. Pushed aside, the
column of connections keeps that icon and that dot, and pressing one opens its
catalog. A catalog is a list of one level: a click opens what can be read and
walks into what cannot, a tick box picks a node out without opening it, the way
back is the first row of the list and the path above it starts at a home
button. One menu in the head carries everything the source can do, live for
what is ticked and greyed out for the rest — standing in a folder is not
choosing it, so nothing is renamed or removed because of where the user
happens to be. Tabs wrap onto a second line rather than running off the end of
a strip, and a strip can be cleared down to the tab being looked at.

### What exists

```
backend/app/
├── adapters/            source types: contract, registry, drivers
│   ├── protocol.py      DataAdapter, SupportsCatalog, SupportsFetch, AdapterError
│   ├── catalog.py       CatalogNode: a union discriminated by kind; NodeKind
│   ├── fetch.py         FetchRequest, FetchResult, closed set of predicates
│   ├── actions.py       Action, ActionSet, SupportsActions, ActionType,
│   │                    DeclaresActions, transports, refusals
│   ├── resources.py     ResourceStore: what outlives a request; Pooling
│   ├── registry.py      type registry, AdapterContext, secret_field_names,
│   │                    Category, Capability, capabilities_of
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

frontend/public/
└── icons/services/      the logo of a source type, one SVG per type

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
│   ├── workspace/       the panel engine: a layout tree, tabs, drag and drop,
│   │                    sections that carry a role and outlive their panels;
│   │                    tree.ts, dropZone.ts, placement.ts and persist.ts are
│   │                    pure, the components see one injected context
│   └── testing/         helpers for tests, not shipped by any screen
├── stores/              Pinia: client-side state only — the session, and what
│                        the last connection check said
└── features/
    ├── auth/
    ├── catalog/         the list of one level, the row grid, and the menu of
    │                    what the ticked nodes admit; nodes.ts, rows.ts and
    │                    actions.ts are pure mappers, and nodes.ts holds the
    │                    table that says what a kind of node does;
    │                    useCatalogLevel.ts walks a catalog outside any
    │                    component
    ├── connectors/      the list of sources, the catalog of source types that
    │                    starts a new one, and the form that registers it;
    │                    adapterSearch.ts is a pure mapper
    ├── workspace/       the panels, the registry that names them and the role
    │                    that puts each in one of the three columns
    └── dev/             /ui-kit and /workspace-demo, dev builds only
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
POST   /api/v1/connectors/{connector_id}/actions
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

- **What a set of nodes admits is asked of the server, in one call.** `POST
  /connectors/{id}/actions` with a list of node ids; the answer is everything
  the source can do with `applicable` saying which of it every one of them
  admits, and the same call decides what the client offers and what the server
  allows, so the two cannot drift — running an action asks `available` again,
  so being listed permits nothing. A flag rather than a shorter list because a
  menu that lost its entries as the user walked the catalog would teach nobody
  what the source can do. Applicability depends on state as well as kind: the
  root of a connector is an ordinary directory that may not be renamed or
  removed, and the driver leaves those actions out of what it admits. A read
  expressed as a POST for the same reason `fetch` is one — the input is an
  unbounded list of opaque identifiers, and selecting a directory of five
  hundred files leaves no room in a query string.
- **An action says what it changes, so the client knows what to send it.**
  `acts_on` is `"node"` for what is done to the rows a user ticked and
  `"children"` for what is made inside the level being looked at. Declared
  beside `applies_to`, because it is the same sort of statement about the
  action; without it the screen would have to read the difference off the names
  of the actions and be taught every one that is ever added. It is also what
  keeps a folder from being deleted by being stood in: only the ticked nodes
  reach an action of the first kind. Full reasoning in
  `docs/superpowers/specs/2026-08-23-explorer-and-strip-design.md`, which also
  carries the rest of this round: the way back as a row, the home crumb, the
  strip of icons a collapsed column keeps, wrapped tabs and the bar at the
  bottom.
- **Whether one filled form may be applied to many is the action's own
  business.** `Action.bulk`; `Delete` says yes, `Rename` cannot, since one name
  for five files is not five renames. The flag never leaves the server: when
  more than one node is asked about, the server itself leaves out what did not
  declare it, so the client still knows only what it may do to what is ticked.
  Full reasoning in
  `docs/superpowers/specs/2026-08-22-catalog-list-design.md`.
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

**D13. A source type describes itself, and what it can do is derived.**
`@register` takes a category — a `Literal`, so a typo does not compile — and a
description, and `GET /adapter-types` answers with both plus a list of
capabilities. Nothing lists those capabilities: `capabilities_of` reads them
off the driver class, by `issubclass` against the capability protocols and by
the titles of the action classes it declares. `FILE_ACTION_TYPES` has two
readers and no copy — `FileActions` builds its set from it, the registry reads
titles off it — which is the shape `secret_field_names` already had. Full
reasoning in `docs/superpowers/specs/2026-08-23-adapter-catalog-design.md`.

The old application kept 105 capability names by hand on the client, in a
931-line file, and its own README called that deliberate duplication and named
the cost. Here the rule from ENGINEERING.md applies instead: the same statement
made in two places is a defect, and this one belongs to the server.

Two consequences worth stating separately:

- **A class answers, not an instance.** The question is about a *type* of
  source, asked before any connector exists, so there are no options and no
  session to build one from. That is why `DeclaresActions` is a classmethod
  rather than a `ClassVar`: a protocol holding data cannot be used with
  `issubclass`, and reaching for the attribute with `getattr` would be exactly
  the `hasattr` dispatch D9 was written to remove.
- **The catalog and the form are two windows, not two steps.** A grid needs
  900px and a form 520, and one component changing width between them would
  carry two roles as well. It is also what lets editing an existing connection
  open its form directly, with no step behind it — so the form states its type
  rather than offering a disabled dropdown of it.

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

**D12. The screen is a workspace of sections, and the engine behind it knows
nothing about the application.** A layout is a tree of sections; every change
to it is a pure function; a section is a list of panels with one active, and
that is the only notion of a tab in the application. What a panel is belongs to
`features/workspace`, which hands the engine a component and a look per panel.
Full reasoning in `docs/superpowers/specs/2026-08-22-workspace-design.md`.

The old application had such an engine and it grew to 2438 lines: nodes were
mutated in place and carried parent back-pointers, so undoing anything needed a
history of layouts and a command language of nine verbs, and a node it could
not remove had to be left in place marked `fake`.

Three consequences worth stating separately:

- **A column is a role, not a place something was dragged to.** A section
  carries `accepts`, the role of panel that lands in it, and `pinned`, which
  keeps it on screen when the last thing in it is closed; the engine compares
  the role and never reads it. That is what makes the screen three columns
  that are always there while leaving the engine ignorant of what a column
  means — and what makes a source type that brings its own view a new kind
  with an existing role rather than a change to the layout. Full reasoning in
  `docs/superpowers/specs/2026-08-22-three-column-workspace-design.md`.
- **A column pushed aside may keep something on screen.** The engine knows the
  section is narrow and asks the feature what is worth that width, the way it
  asks what stands in an empty one; only the connections answer, with their
  icons and their state dots. Closing every tab but the active one is the
  engine's too — it is a layout operation, and what a panel is has no bearing
  on it — and it leaves a panel the feature says has no cross, exactly as its
  own cross would.
- **A tab that is not showing is kept, not destroyed.** Switching away and back
  is no reason to re-read a catalog or to lose the page a grid was on, so the
  section wraps the active panel in `<KeepAlive>`. That puts one requirement on
  the feature: `component(panel)` must answer with the same component for the
  same panel. A wrapper built afresh on each call is a different component each
  time — the panel would be remounted on every render, and a functional wrapper
  cannot be kept alive at all.
- **Walking a catalog is not logic of a screen.** `useCatalogTree` holds it,
  and it invalidates the branch it re-reads rather than trusting whoever
  changed it to have done so.

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

The same script also removes the home directories of users that no longer
exist. Deleting a user through the API takes their directory with it, but
wiping the table underneath the application does not, so each test run would
otherwise strand a full directory under an id nobody can log in as. Only a real
directory named after a user id is a candidate; a symlink or any other name is
reported and left alone.

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
copied into the image verbatim and run by bash, which reads a trailing `
` as
part of the command: `prestart-dev.sh` rewritten with CRLF failed with
`bash: scripts/prestart.sh: No such file or directory`, naming a file that was
plainly there. `.gitattributes` pins `*.sh` to `eol=lf`, but that only applies
when git writes the file — an editor or a script that rewrites it in the
working tree on Windows can still break the container. `file backend/scripts/*.sh`
says which ones are wrong.

The same rewrite is worth watching on any tracked text file. `text=auto`
normally normalises on commit, but AGENTS.md once went in as CRLF anyway and
turned a five-line edit into a 597-line diff. `git diff --stat` says so before
the commit; `git show :FILE | file -` says what is actually about to be stored.

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

The workspace is done: one screen of resizable sections with tabs (D12),
replacing the connections page and the catalog modal. The engine under it knows
nothing about panels, and what it settled is worth carrying into 7: a section
keeps the panel of an inactive tab alive, which is what makes a long-running
panel — a terminal, an agent, a subscription — possible without the layout
resetting it.

The screen it produced is now three columns that are always there: sources,
what is being browsed, and what is being worked on. What that settled matters
more than the shape: a column is a role, and where a panel goes is decided by
the role it declares rather than by the layout knowing what a catalog is. Every
view a later source type brings — a topic browser, a monitor, a query editor —
is a new panel kind with one of those three roles, and the screen does not
change to take it.

What the three columns hold was then rebuilt to match how they are worked in.
The catalog is a list of one level rather than a tree, and what a click means
follows from the kind of the node — a schema is a grouping and lives in the
filter above the list, a directory is walked into, a table is opened. Ticking
replaced selecting, which is what made an action over several nodes possible at
all, and that turned the question "what can be done here" from one about a node
into one about a set. A connection lost its row menu to the one window its icon
opens. Full reasoning in
`docs/superpowers/specs/2026-08-22-catalog-list-design.md`.

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
- **A home can outlive its user by a failure.** `crud.delete_user` removes the
  row, commits, then removes the files, so a user is never left able to log in
  with their files gone. If that last step fails the directory stays, and
  nothing in a deployment sweeps it up — `app.seed_storage` does, but it is a
  development tool.
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
- **`AppTree` is a wrapper over `q-tree`, not a tree of its own.** The kit now
  owns it and the lint rule forbids the Quasar one outside `shared/ui`, but the
  types of its nodes and of a lazy load are read off Quasar's props, so
  replacing the tree would change what a screen passes it.
- **`AppTree` is in the kit and nothing uses it.** The catalog was its only
  consumer and is now a list. It stays because the kit is built as an alphabet
  rather than by the count of today's callers, and it is still demonstrated at
  `/ui-kit` — but nothing but that page renders it.
- **Where one was in a catalog is not remembered.** The layout survives a
  reload; the path inside a catalog does not, so a reloaded page is back at the
  root of the connection.
- **A set is acted on one call at a time.** Deleting five files is five
  requests from the browser, run in order; a refusal in the middle is collected
  and reported rather than stopping the rest. Nothing is transactional: four of
  five may be gone.
- **Applicability costs a call per node.** The route asks the driver about
  every node in the set, so ticking a thousand files means a thousand
  filesystem checks behind one request. Bounded by a ceiling of a thousand
  node ids and by the file source refusing to list more than 2000 entries.
- **The name of a row loses to its captions in a narrow column.** With several
  groupings on, the row carries the name of its grouping and its size or row
  estimate, and the name is elided first. The columns are resizable, which is
  the only answer today.
- **One catalog at a time.** Opening a connection closes the catalog of the
  previous one, so the expanded tree of the one before is lost on the way
  back. The panel is still identified by its connection, so allowing two
  catalogs side by side is dropping one flag at one call site — but nothing
  offers that today.
- **A source that has no catalog has not been seen.** Both source types
  implement every capability, so the middle column has never had to say "this
  one has nothing to browse". The mechanism does not stand in the way — such a
  source opens no panel of that role and the column keeps its hint — but the
  branch is untested. The server does report a type's capabilities now (D13),
  so the catalog says so before a connection is made; the middle column still
  has no wording for it.
- **The state dot only knows about this session.** A connection shows grey
  until the user checks it; nothing checks in the background, because that
  would mean opening a connection to every source on every load. The record is
  not persisted: a dot restored from yesterday would claim more than it knows.
- **The menu of actions costs two calls.** One about the level being looked at,
  which carries the vocabulary, and one about what is ticked. They could be one
  call taking two sets of nodes, at the price of a request body that says two
  different things.
- **The bar at the bottom of the screen is empty.** It closes the layout and
  holds the room for a status line; nothing puts anything in it yet.
- **Tabs cannot be reordered inside a strip.** Dragging a tab moves it to
  another section or splits one; dropping it back into its own strip does
  nothing.
- **The layout is one per browser.** It lives in localStorage, so it does not
  follow a user to another machine and is not shared between two windows.
- **A panel of a connector that was deleted stays until it is closed.** It
  shows the error the server gave rather than disappearing, because the panel
  cannot tell a deleted connector from a failed request.
- **A closed panel is still held.** Both the map of bound components in
  `features/workspace/panels.ts` and the cache inside `<KeepAlive>` keep what
  they were given for as long as the page lives; nothing prunes them when a tab
  is closed. Bounded by how many distinct panels one session opens.
- **There is no dark theme.** Tokens are build-time sass variables; switching
  at runtime needs CSS custom properties and its own task.
- **D2b — a driver is a session plus capability modules — rests on review.**
  There is no check that a capability module keeps out of connection handling.
- **A capability is coarser than what a source actually does.** "Read rows" is
  true of PostgreSQL and of a file, and says nothing about the file having no
  index to sort by. The honest finer answer already exists in
  `FetchResult.sortable` / `filterable`, but it belongs to a connection rather
  than to a type, so the catalog cannot show it.
- **A capability describes a type, not a node.** The file driver declares
  `Delete`, and the root of a connector may not be deleted — that is state,
  known only to `available()`. The catalog therefore promises slightly more
  than any particular node will allow.
- **A type's description is unchecked free text.** Nothing requires
  `@register` to be given a meaningful one, and an empty string passes.
- **The catalog search knows no morphology.** Substring matching over the name,
  category, description and capability titles, so "migrations" does not find
  "migration" and a Russian word finds nothing. The old application reached for
  an embedding model in the browser; over a registry this size that is not
  worth the download.
- **Two categories make for a thin sidebar.** "All", "SQL Databases" and
  "Files & Storage", one type each. Built for the registry D1 anticipates
  rather than for its size today — the same reasoning as building the UI kit
  as an alphabet.
- **The reuse rules rest on review.** No machine flags the third similar thing
  in a diff.
