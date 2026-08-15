# AGENTS.md

This is the canonical repository guide for coding agents and humans. Other
instruction files must point here instead of duplicating this content.

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

The first slice is complete: a user can sign in, register a PostgreSQL
connection through a form built from the adapter's own schema, check the
connection before and after saving, and manage the list of connections.
Credentials are encrypted at rest and never leave the server.

### What exists

```
backend/app/
├── adapters/            source types: contract, registry, drivers
│   ├── protocol.py      DataAdapter Protocol, ConnectionCheckResult
│   ├── registry.py      type registry, secret_field_names
│   ├── routes.py        GET /adapter-types
│   └── postgres/        the only driver so far
├── connectors/          user connections
│   ├── models.py        Connector + API schemas
│   ├── crud.py          database access only
│   ├── service.py       option splitting, adapter construction
│   └── routes.py        CRUD + connection checks
├── core/
│   ├── crypto.py        AES-GCM for connector secrets
│   ├── db.py            async engine, session, loop_factory
│   ├── config.py        settings
│   └── security.py      passwords and JWT
├── models.py            User and shared API schemas (flat, see D5)
├── crud.py              user CRUD (flat, see D5)
└── api/routes/          login, users, utils, private (flat, see D5)

frontend/src/
├── client/              generated from OpenAPI, never edited by hand
├── shared/              api client setup, layout
├── stores/              Pinia: client-side state only
└── features/
    ├── auth/
    └── connectors/
        └── SchemaForm/  JSON Schema to form, framework-independent core
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

**D2. The adapter contract is a `typing.Protocol`, not a base class.** A driver
inherits nothing; conformance is checked structurally by mypy. The contract
currently has one method, `check_connection()`. The rest arrive when their
return types are understood — the old application returns bare `dict` from
`get_catalog`, and that is what we are not repeating.

**D3. The backend is fully asynchronous.** `AsyncSession`, `async def`
throughout, psycopg 3 in async mode. The application is network-I/O bound by
definition.

**D4. Secrets are split by schema, not by hand.** Fields declared as
`SecretStr` go into the encrypted `Connector.secrets` blob; everything else
goes into the `config` jsonb column. No list of secret fields exists anywhere,
so a field cannot be forgotten. `CONNECTOR_SECRET_KEY` is deliberately separate
from `SECRET_KEY`: rotating the latter only logs everyone out, rotating the
former requires migrating stored data.

**D5. New code goes in feature modules; the flat template files stay for now.**
`app/adapters/` and `app/connectors/` are modules. `app/models.py`,
`app/crud.py` and `app/api/routes/` are still flat because breaking them up
touches users and login without adding anything to the current work. That is
sub-project 2a below. New code is written as modules.

**D6. Server state lives in vue-query; Pinia holds only client state.** The old
frontend spread server data across Pinia stores, each with its own cache and
its own invalidation, and that is where its desynchronisation bugs come from.

**D7. The frontend is Vue 3 with Quasar.** The value of the rewrite is backend
architecture and end-to-end typing; the UI kit was never the problem. The
typed client generated from OpenAPI is kept — it does not depend on the
framework.

## Commands

The database and backend run in Docker. Bring them up first:

```bash
docker compose up -d db backend
```

### Backend

```bash
cd backend
uv sync                     # install dependencies
uv run pytest tests/ -q     # tests (needs the db container)
uv run mypy app             # strict mode, configured in pyproject.toml
uv run ruff check app tests
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

**`vue-tsc` does not work under the bun runtime.** It fails to register the
`.vue` extension, so every component silently drops out of the compiler
program and imports like `@/App.vue` appear to be missing. Measured: 4 files
under Node, 0 under bun. On Windows `bun run type-check` happens to work
because the `.cmd` shim invokes Node. The `oven/bun:1` image has no real Node
at all, which is why `bun run build` performs only `vite build`; type checking
lives in `type-check` and `build:checked`.

**Running the backend test suite wipes all users**, including the superuser,
because the tests share the development database. Restore it with:

```bash
docker compose exec backend python -m app.initial_data
```

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

1. Read the surrounding module before changing behaviour.
2. Tests first. Every task in the completed slice went failing test →
   implementation → passing test → commit.
3. Never claim something works without running the check and seeing the output.
4. Secrets never appear in API responses, error messages or logs. There are
   regression tests for this; keep them passing.
5. `mypy --strict` and `ruff` must pass on the backend; `vue-tsc` and ESLint on
   the frontend. No new `type: ignore` without a reason in a comment.
6. `frontend/src/client` is generated. Never edit it; regenerate instead.
7. `.env` is not tracked. Add new settings to `.env.example` as well.
8. When a plan turns out to be wrong during execution, fix the plan document
   too, not just the code.

## What comes next

From the design document, in order:

| # | Sub-project |
| --- | --- |
| 2a | Break up `models.py`, `crud.py` and `api/routes/` into an `app/users/` module |
| 3 | Catalog: `get_catalog` and `refresh_model` with real types |
| 4 | Data fetching: `fetch` with paging, filters, sorting; a connection pool |
| 5 | Action registry: what each source type can do |
| 6 | A second, non-SQL adapter (MongoDB or S3) to prove the abstraction does not leak |
| 7+ | Realtime, AI, data grid |

Each sub-project gets its own design document, its own plan and its own
iteration.

### Known limitation

`POST /connectors/check-draft` opens a TCP connection to an address supplied by
the client, which lets an authenticated user map the internal network by
response timing and error kind. Mitigated by a hard timeout and uniform error
messages. A host allow-list is the remaining fix and is not implemented.
