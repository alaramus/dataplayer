# Development

Architecture and the reasoning behind it live in [AGENTS.md](AGENTS.md). This
file covers the day-to-day loop.

## Layout

```
backend/    FastAPI application, Alembic migrations, pytest suite
frontend/   Vue 3 application, Vitest unit tests, Playwright end-to-end tests
docs/       design documents and implementation plans
scripts/    generate-client.sh and the test runners
```

## Running

The database and backend always run in Docker. The backend cannot run natively
on Windows — psycopg 3 in async mode is incompatible with the event loop
Python selects there.

```bash
docker compose up -d db backend   # API on :8000, database on :5432
cd frontend && bun run dev        # dev server on :5173
```

The frontend dev server proxies nothing: it calls the API directly at the
address in `frontend/.env`.

Useful extras:

```bash
docker compose logs -f backend
docker compose up -d adminer      # database UI on :8080
docker compose up -d mailcatcher  # captured outgoing mail on :1080
```

## Changing the backend

```bash
cd backend
uv run pytest tests/ -q
uv run mypy app
uv run ruff check app tests
```

The container watches `backend/` and reloads, so no rebuild is needed for code
changes. After changing dependencies:

```bash
docker compose up -d --build backend
```

### Migrations

```bash
cd backend
uv run alembic revision --autogenerate -m "add something"
uv run alembic upgrade head
```

Read the generated file before applying it. Autogenerate sees only models that
are imported by `app/alembic/env.py`, so a model in a new module has to be
added there.

### After changing routes or schemas

Regenerate the typed client, otherwise the frontend still sees the old API:

```bash
bash scripts/generate-client.sh
```

## Changing the frontend

```bash
cd frontend
bun run type-check   # needs real Node, not the bun runtime
bun run lint
bun run test:unit
```

End-to-end tests need the database, the backend and the dev server running:

```bash
bunx playwright test
bunx playwright test --ui   # interactive
```

## Recovering the superuser

The backend test suite deletes every user, including the superuser, because it
shares the development database. After running the suite:

```bash
docker compose exec backend python -m app.initial_data
```

## Starting from a clean database

```bash
docker compose down -v
docker compose up -d db backend
```

This drops the volume and everything in it. The backend recreates the schema
and the superuser on start.
