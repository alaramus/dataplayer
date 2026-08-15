# DataPlayer

A platform for connecting to heterogeneous data sources, exploring them and
working with them through one interface.

Register a connection through a form generated from the adapter's own schema,
check that it works before saving, and keep credentials encrypted at rest.

## Stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.14, FastAPI, SQLModel over async SQLAlchemy, PostgreSQL, Alembic |
| Frontend | Vue 3, TypeScript, Quasar, Vite, TanStack Query, Pinia |
| API client | Generated from OpenAPI, so types run end to end |
| Tests | pytest, Vitest, Playwright |

## Getting started

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env
```

Fill in both files: at minimum `SECRET_KEY`, `CONNECTOR_SECRET_KEY`,
`POSTGRES_PASSWORD` and `FIRST_SUPERUSER_PASSWORD`. Generate the encryption
key with:

```bash
python -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

Then start the stack and the dev server:

```bash
docker compose up -d db backend
bun install
bun run dev
```

The application is served at http://localhost:5173, the API at
http://localhost:8000, and the interactive API docs at
http://localhost:8000/docs.

## Documentation

- [AGENTS.md](AGENTS.md) — what the project is, decisions, commands and traps.
  Read this before changing anything.
- [ENGINEERING.md](ENGINEERING.md) — how code is written here, and what
  enforces each rule.
- [development.md](development.md) — day-to-day workflow.
- `docs/superpowers/` — design documents and implementation plans.
