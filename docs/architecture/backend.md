# Backend

How the application is divided, how it talks to the database, how secrets are
handled, and what the API is. Read this before adding a module, a route or a
migration.

Decisions here: D3, D4, D5.

## What exists today

FastAPI, SQLModel over async SQLAlchemy, PostgreSQL, Alembic. A user signs in,
registers connections, checks them, browses their catalogs and reads rows.
Credentials are encrypted at rest and never leave the server. Every user owns a
personal directory, created with the user.

A connection is identified by its id and by nothing else. Names are a label the
user writes for themselves and two connections of one owner may share one:
pointing the same tool at two databases that are meant to be the same, staging
and production side by side, is the normal case and not a mistake to prevent.
The unique constraint that used to sit on `(owner_id, name)` was also never
caught anywhere — a duplicate reached the client as a 500 out of psycopg rather
than as an answer — so removing it took a failure mode with it
(`b8c4d2e91a57`). What follows is that nothing may address a connection by
name: the API takes ids, and a screen showing a list shows the name but acts on
the id.

```
backend/app/
├── adapters/            source types — see adapters.md
├── connectors/          user connections
│   ├── models.py        Connector + API schemas
│   ├── crud.py          database access only
│   ├── service.py       option splitting, adapter construction
│   └── routes.py        CRUD, connection checks, reading a pasted DSN
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
├── seed_database.py     dev tool: rebuilds the demo_lab PostgreSQL fixtures
├── seed_storage.py      dev tool: sample files into a personal directory
├── core/                depends on nothing else in the app
│   ├── crypto.py        AES-GCM for connector secrets
│   ├── db.py            async engine, session, SessionDep, loop_factory
│   ├── schemas.py       Message, get_datetime_utc
│   ├── email.py         sending and templating
│   ├── config.py        settings
│   └── security.py      passwords and JWT
├── api/main.py          router aggregation only
└── main.py              application assembly; the lifespan owns the store
```

## API

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
POST   /api/v1/connectors/describe-draft
POST   /api/v1/connectors/parse-url
GET    /api/v1/connectors/{connector_id}/catalog
GET    /api/v1/connectors/{connector_id}/relation-model
POST   /api/v1/connectors/{connector_id}/fetch
POST   /api/v1/connectors/{connector_id}/actions
POST   /api/v1/connectors/{connector_id}/actions/{action_name}
POST   /api/v1/connectors/{connector_id}/actions/{action_name}/file
```

After changing a route or a schema, regenerate the typed client:
`bash scripts/generate-client.sh`.

## D3. The backend is fully asynchronous

`AsyncSession`, `async def` throughout, psycopg 3 in async mode. The application
is network-I/O bound by definition.

Two things follow, both of which have cost time: a blocking call inside a
handler stalls the whole event loop and must go through `run_in_threadpool`, and
anything holding connections belongs to the loop that created it. Both are in
the traps list in [AGENTS.md](../../AGENTS.md).

## D4. Secrets are split by schema, not by hand

Fields declared as `SecretStr` go into the encrypted `Connector.secrets` blob;
everything else goes into the `config` jsonb column. No list of secret fields
exists anywhere, so a field cannot be forgotten. With a union of options the
split reads every variant — see D16 in [adapters.md](adapters.md).

`CONNECTOR_SECRET_KEY` is deliberately separate from `SECRET_KEY`: rotating the
latter only logs everyone out, rotating the former requires migrating stored
data.

Known deviation:

- **`.env` is in the git history.** It was tracked before being removed, so the
  values it held at the time are still recoverable from earlier commits. They are
  development placeholders, but a real deployment must not reuse them.

## D5. Everything lives in feature modules, and dependencies point one way

The flat layer inherited from the template — `app/models.py`, `app/crud.py`,
`app/utils.py`, `app/api/deps.py`, `app/api/routes/` — is gone. `core` depends on
nothing else in the application, `users` depends on `core`, and `connectors` and
`adapters` depend on `core` and `users`. There are no arrows back.

That is why `init_db` lives in `app/users/bootstrap.py` rather than in
`core/db.py`: creating the first superuser is a users concern, and keeping it in
core would have made core import users.

Enforced by `uv run lint-imports`.
