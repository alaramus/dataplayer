# DataPlayer

One web interface for the data sources you work with: browse what is in them,
query and edit them, move data between them, watch them, and hand routine
work to an AI agent that uses the same connections you do.

DataPlayer runs on your own machine or server with Docker Compose. Credentials
are encrypted at rest and never leave the backend.

![The workspace: connections, a catalog, tabs of rows, a quick chat answered by Gemini Nano in the browser, the server's log and the activity panel](docs/screenshots/overview.webp)

| | |
| --- | --- |
| ![A connection's catalog beside a live grid of rows](docs/screenshots/data.webp) | ![A pipeline: a table copied between PostgreSQL connections, then saved as CSV](docs/screenshots/pipelines.webp) |
| **Data** — a catalog per connection and a grid of rows | **Pipelines** — steps between connections, run as one |
| ![A dashboard of PostgreSQL metrics](docs/screenshots/dashboards.webp) | ![A conversation with the AI agent](docs/screenshots/ai-agent.webp) |
| **Dashboards** — metrics from connection polls and agents | **AI agent** — works through the same connections you do |

## What it does

**Sources**

- **PostgreSQL**, including TimescaleDB: hypertables, chunks, policies and
  continuous aggregates.
- **Redis**: the key space as a tree grouped by `:`, every value type read as
  rows.
- **Files** on the server, and **SSH servers**: a file explorer with preview,
  upload and download, and a terminal in the browser.

A connection is added through a form generated from the source's own schema,
or by pasting a connection string, and is checked before it is saved.

**Working with data**

- A catalog per connection, with filtering and search by name.
- A data grid with sorting, filters, inline editing, inserts and deletes,
  charts, and download of the current page or every row.
- A SQL editor with history, saved query documents, Explain, and explicit
  transactions.
- A table designer for columns, indexes and constraints; every change is
  shown as the statement it will run before anything is sent.
- References drawn by hand between columns, even across connections, and
  relationship diagrams in 2D and 3D.
- Copying rows and whole tables between connections, and loading files in.

**Running things**

- Pipelines of steps between connections, run on demand or on a schedule,
  with a history of runs.
- Dashboards fed by connection polls and by a small metrics agent installed on
  your machines.
- Managed services: start a database or cache in a container from a template,
  and back up and restore databases.
- Share links to a tab, with access requests.

**AI agent**

- A chat that can list, read and change your sources through tools, asking
  before every change by default. Works with several model providers; you
  bring your own API key.

**Everywhere**

- One search over connections, their contents and everything the application
  keeps (`Ctrl + K`).
- A workspace of draggable panels and tabs, floating windows, and several
  light and dark themes.

## Stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.14, FastAPI, SQLModel over async SQLAlchemy, PostgreSQL, Alembic |
| Frontend | Vue 3, TypeScript, Quasar, Vite, TanStack Query, Pinia |
| API client | Generated from OpenAPI, so types run end to end |
| Tests | pytest, Vitest, Playwright |

## Getting started

DataPlayer starts in one of two modes, chosen by one line in `.env`:

| | Run it | Develop it |
| --- | --- | --- |
| `COMPOSE_FILE` in `.env` | `compose.yml,compose.prod.yml` | `compose.yml,compose.override.yml` (the default) |
| You need | Docker | Docker, [Bun](https://bun.sh) and Node.js |
| Interface | built into the image, on `APP_PORT` (8000) | Vite dev server on 5173, reloading on every edit |
| Data at the start | the first superuser only | sample databases, files and references |
| Extras | none; restarted after a reboot | Adminer, Mailcatcher, a test Redis and SSH server, the Docker socket for managed services |

### 1. Configure

```bash
cp .env.example .env
```

In `.env`, keep the `COMPOSE_FILE` line of the mode you want and replace every
placeholder: at minimum `SECRET_KEY`, `CONNECTOR_SECRET_KEY`,
`QUERY_CONTENT_KEY`, `AI_CONTENT_KEY`, `POSTGRES_PASSWORD`,
`FIRST_SUPERUSER_PASSWORD`, `DATA_CACHE_REDIS_PASSWORD` and
`DATA_CACHE_SECRET_KEY`. Generate each key with:

```bash
python -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

Running it refuses to start while `SECRET_KEY`, `POSTGRES_PASSWORD` or
`FIRST_SUPERUSER_PASSWORD` is still `changethis`; the keys are refused in
either mode unless they decode to 32 bytes.

### 2a. Run it

Also set `FRONTEND_HOST` to the address people will open, for example
`http://localhost:8000`, comment out `FASTAPI_ENV`, and give
`DATA_CACHE_DEPLOYMENT` a name of its own. Then:

```bash
docker compose up -d --build
```

Open http://localhost:8000 and sign in as `FIRST_SUPERUSER` with
`FIRST_SUPERUSER_PASSWORD`. The port speaks plain HTTP: to reach DataPlayer
from outside this machine, put a reverse proxy that terminates HTTPS in front
of it (Caddy, Traefik, nginx) and set `FRONTEND_HOST` to its address. Back up
the Docker volume `dataplayer_app-db-data`; it holds everything DataPlayer
keeps.

### 2b. Develop it

```bash
cp frontend/.env.example frontend/.env
docker compose up -d --build backend metrics
cd frontend && bun install && bun run dev
```

The interface is at http://localhost:5173, the API at http://localhost:8000
and its interactive docs at http://localhost:8000/docs. To fill the connections
panel with examples — the bundled PostgreSQL under several names, file storage
and Redis — run `bun run seed:connectors` from the repository root.

The backend cannot run natively on Windows: psycopg 3 in async mode is
incompatible with the event loop Python selects there. Use Docker.

## Working on it

Coding agents and people start in the same place:

- [AGENTS.md](AGENTS.md) — what the project is, where to read the rest,
  commands and traps. Read this before changing anything.
- [ENGINEERING.md](ENGINEERING.md) — how code is written here, and what
  enforces each rule.
- [docs/architecture/](docs/architecture/) — what exists in each area, the
  decisions behind it, and where it falls short.
- [docs/decisions/](docs/decisions/README.md) — the design history: why each
  decision was taken.

## License

DataPlayer is licensed under the [Apache License 2.0](LICENSE). It began from
the [FastAPI full-stack template](https://github.com/fastapi/full-stack-fastapi-template);
the little of that code that remains is used under the MIT License, as
[NOTICE](NOTICE) records.
