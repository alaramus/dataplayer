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
| Adapters, source types, actions, pooling | [adapters.md](docs/architecture/adapters.md) |
| Backend modules, routes, migrations, secrets, database | [backend.md](docs/architecture/backend.md) |
| Screens, components, colours, layers | [frontend.md](docs/architecture/frontend.md) |
| Layout, tabs, dragging, floating windows | [workspace.md](docs/architecture/workspace.md) |
| Sockets, topics, server-pushed state | [realtime.md](docs/architecture/realtime.md) |
| Any code | [ENGINEERING.md](ENGINEERING.md) |

The roadmap is the source of truth for completed behaviour and what comes next;
do not duplicate its feature inventory here.

## Decision registry

The wording, reasoning and known deviations live in the linked architecture
files. IDs are stable because specs and commits refer to them.

| ID | Home |
| --- | --- |
| D1 | [adapters](docs/architecture/adapters.md) |
| D2 | [adapters](docs/architecture/adapters.md) |
| D2a | [adapters](docs/architecture/adapters.md) |
| D2b | [adapters](docs/architecture/adapters.md) |
| D2c | [adapters](docs/architecture/adapters.md) |
| D2d | [adapters](docs/architecture/adapters.md) |
| D3 | [backend](docs/architecture/backend.md) |
| D4 | [backend](docs/architecture/backend.md) |
| D5 | [backend](docs/architecture/backend.md) |
| D6 | [frontend](docs/architecture/frontend.md) |
| D7 | [frontend](docs/architecture/frontend.md) |
| D8 | [adapters](docs/architecture/adapters.md) |
| D9 | [adapters](docs/architecture/adapters.md) |
| D10 | [adapters](docs/architecture/adapters.md) |
| D11 | [frontend](docs/architecture/frontend.md) |
| D12 | [workspace](docs/architecture/workspace.md) |
| D13 | [adapters](docs/architecture/adapters.md) |
| D14 | [workspace](docs/architecture/workspace.md) |
| D15 | [adapters](docs/architecture/adapters.md) |
| D16 | [adapters](docs/architecture/adapters.md) |
| D17 | [adapters](docs/architecture/adapters.md) |
| D18 | [realtime](docs/architecture/realtime.md) |
| D19 | [realtime](docs/architecture/realtime.md) |
| D20 | [adapters](docs/architecture/adapters.md) |
| D21 | [adapters](docs/architecture/adapters.md) |
| D22 | [adapters](docs/architecture/adapters.md) |
| D23 | [adapters](docs/architecture/adapters.md) |
| D24 | [frontend](docs/architecture/frontend.md) |
| D25 | [adapters](docs/architecture/adapters.md) |
| D26 | [adapters](docs/architecture/adapters.md) |
| D27 | [adapters](docs/architecture/adapters.md) |
| D28 | [frontend](docs/architecture/frontend.md) |
| D29 | [adapters](docs/architecture/adapters.md) |
| D30 | [adapters](docs/architecture/adapters.md) |
| D31 | [adapters](docs/architecture/adapters.md) |
| D32 | [adapters](docs/architecture/adapters.md) |
| D33 | [backend](docs/architecture/backend.md) |
| D34 | [backend](docs/architecture/backend.md) |
| D35 | [frontend](docs/architecture/frontend.md) |
| D36 | [adapters](docs/architecture/adapters.md) |
| D37 | [adapters](docs/architecture/adapters.md) |
| D38 | [adapters](docs/architecture/adapters.md) |
| D39 | [adapters](docs/architecture/adapters.md) |
| D40 | [adapters](docs/architecture/adapters.md) |
| D41 | [adapters](docs/architecture/adapters.md) |
| D42 | [adapters](docs/architecture/adapters.md) |
| D43 | [adapters](docs/architecture/adapters.md) |
| D44 | [adapters](docs/architecture/adapters.md) |
| D45 | [adapters](docs/architecture/adapters.md) |
| D46 | [adapters](docs/architecture/adapters.md) |
| D47 | [adapters](docs/architecture/adapters.md) |
| D48 | [adapters](docs/architecture/adapters.md) |
| D49 | [adapters](docs/architecture/adapters.md) |
| D50 | [frontend](docs/architecture/frontend.md) |
| D51 | [adapters](docs/architecture/adapters.md) |
| D52 | [adapters](docs/architecture/adapters.md) |
| D53 | [adapters](docs/architecture/adapters.md) |
| D54 | [adapters](docs/architecture/adapters.md) |
| D55 | [adapters](docs/architecture/adapters.md) |
| D56 | [adapters](docs/architecture/adapters.md) |
| D57 | [adapters](docs/architecture/adapters.md) |

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
