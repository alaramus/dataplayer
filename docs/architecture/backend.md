# Backend

How the application is divided, how it talks to the database, how secrets are
handled, and what the API is. Read this before adding a module, a route or a
migration.

Decisions here: D3, D4, D5, D33, D34.

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
├── adapters/            source types — see sources/README.md
├── connectors/          user connections
│   ├── models.py        Connector, ConnectorGrant + API schemas
│   ├── crud.py          database access only, including access resolution
│   ├── service.py       option splitting, adapter construction
│   └── routes.py        CRUD, connection checks, a pasted DSN, grants
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
├── queries/             query documents and runs — see querying.md
│   ├── models.py        QueryDocument, EditorLayout + API schemas
│   ├── runs.py          ExecutionRun, StatementRun + API schemas
│   ├── content.py       the one place the query content key is used
│   ├── crud.py          database access only, including the Trash sweep
│   ├── execution.py     admission, the run task, restart recovery
│   ├── results.py       captured results, process-local and bounded
│   ├── topic.py         run state on the socket
│   ├── cleanup.py       the lifespan timer that empties Trash
│   └── routes.py        the library, one document, Trash, runs, results
├── system/              operational routes: /utils health check, test email
├── seed_database.py     dev tool: rebuilds the demo_lab PostgreSQL fixtures
├── seed_storage.py      dev tool: sample files into a personal directory
├── core/                depends on nothing else in the app
│   ├── access.py        the ordered scale of what a user may do
│   ├── crypto.py        AES-GCM, under the key each purpose names
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
GET    /api/v1/users/directory
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
GET    /api/v1/connectors/{connector_id}/catalog?refresh=false
GET    /api/v1/connectors/{connector_id}/relation-model
POST   /api/v1/connectors/{connector_id}/fetch?refresh=false
POST   /api/v1/connectors/{connector_id}/content
POST   /api/v1/connectors/{connector_id}/content/editor
PATCH  /api/v1/connectors/{connector_id}/content/editor
GET    /api/v1/connectors/content-files/{ticket}
POST   /api/v1/connectors/{connector_id}/downloads/page
POST   /api/v1/connectors/{connector_id}/downloads/export
GET    /api/v1/connectors/export-downloads/{ticket}
PATCH  /api/v1/connectors/{connector_id}/columns
POST   /api/v1/connectors/{connector_id}/actions
POST   /api/v1/connectors/{connector_id}/actions/{action_name}
POST   /api/v1/connectors/{connector_id}/actions/{action_name}/download
POST   /api/v1/connectors/{connector_id}/actions/{action_name}/file
GET    /api/v1/connectors/action-downloads/{ticket}
GET    /api/v1/connectors/{connector_id}/grants
PUT    /api/v1/connectors/{connector_id}/grants
DELETE /api/v1/connectors/{connector_id}/grants/{user_id}
```

After changing a route or a schema, regenerate the typed client:
`bash scripts/generate-client.sh`.

## Rehearsing the pipeline locally

Settings name `../.env`, so a run started from `backend/` reads whatever the
developer keeps there — `FASTAPI_ENV`, `SMTP_HOST`, `EMAILS_FROM_EMAIL` — and
silently fills the gaps that CI, which has no such file, will not fill. Three
pipelines went red on variables that a local run appeared to prove present.

The commonest of those is now a test rather than a procedure: a setting with no
default is one somebody has to supply, and `tests/core/test_settings.py` fails
locally when the backend job of `.gitlab-ci.yml` or `.env.example` does not
name it. It was written after the third red pipeline and checked by taking the
variable out again.

That leaves what a list of names cannot cover — a value CI sets to something
different, a service alias, a step order. A rehearsal of those uses a checkout
without `.env`, on Linux:

```bash
git archive HEAD | tar -x -C /tmp/rehearsal
docker run --rm --network ci --network-alias … -w /repo/backend \
  ghcr.io/astral-sh/uv:bookworm-slim bash -c "uv sync --frozen && …"
```

## D3. The backend is fully asynchronous

`AsyncSession`, `async def` throughout, psycopg 3 in async mode. The application
is network-I/O bound by definition.

Two things follow, both of which have cost time: a blocking call inside a
handler stalls the whole event loop and must go through `run_in_threadpool`, and
anything holding connections belongs to the loop that created it. Both are in
the traps list in [AGENTS.md](../../AGENTS.md).

Spec: [The connector registry and the adapter contract](../superpowers/specs/2026-08-15-connector-registry-design.md)

## D4. Secrets are split by schema, not by hand

Fields declared as `SecretStr` go into the encrypted `Connector.secrets` blob;
everything else goes into the `config` jsonb column. No list of secret fields
exists anywhere, so a field cannot be forgotten. With a union of options the
split reads every variant — see D16 in [sources/connecting.md](sources/connecting.md).

`CONNECTOR_SECRET_KEY` is deliberately separate from `SECRET_KEY`: rotating the
latter only logs everyone out, rotating the former requires migrating stored
data.

Known deviation:

- **`.env` is in the git history.** It was tracked before being removed, so the
  values it held at the time are still recoverable from earlier commits. They are
  development placeholders, but a real deployment must not reuse them.

Spec: [The connector registry and the adapter contract](../superpowers/specs/2026-08-15-connector-registry-design.md)

## D5. Everything lives in feature modules, and dependencies point one way

The flat layer inherited from the template — `app/models.py`, `app/crud.py`,
`app/utils.py`, `app/api/deps.py`, `app/api/routes/` — is gone. `core` depends on
nothing else in the application, `users` depends on `core`, and `connectors` and
`adapters` depend on `core` and `users`. There are no arrows back.

That is why `init_db` lives in `app/users/bootstrap.py` rather than in
`core/db.py`: creating the first superuser is a users concern, and keeping it in
core would have made core import users.

Enforced by `uv run lint-imports`.

Spec: [Breaking the flat layer up into a users module](../superpowers/specs/2026-08-15-users-module-design.md)

## D33. Access to a connection is a grant of an ordered level, and a route states the level it needs

A grant is a row — connector, user, level — and nothing else. The question
"may this user do this here" is a primary key lookup, not a policy to evaluate.

The levels are a total order, and that order is the whole semantics:

| Level | What it admits |
| --- | --- |
| `read` | catalog, relation model, rows, node path, page or whole export, a connection check |
| `write` | plus changing rows: cell update, insert, bulk delete |
| `structure` | plus changing shape: add, drop, rename a column, a column default, renaming a relation |
| `own` | plus the connection itself: its options, its credentials, its grants, deleting it |

`own` is on the scale because routes compare against it and off `Grant`
because ownership is a column on the connector, not a row somebody can be
handed. `app/core/access.py` holds the scale: `connectors` resolves a level and
an action in `adapters` declares the one it requires, and neither package may
import the other.

Enforcement is one funnel. `_resolve`, `_get_or_404` and `_adapter_for` take
`requires` as a keyword argument with no default, so a route added later cannot
reach a source without saying what it needs — the call does not type-check
otherwise. No standing at all answers 404, the same as a connector that does
not exist, so ids are not an oracle for what other people hold; a standing
below what the route needs answers 403.

**401 and 403 say different things, and now it matters.** Authentication
answers 401 with `WWW-Authenticate: Bearer` — an unusable token, an unknown
subject, an account switched off. Authorization answers 403. They were
interchangeable while no level was ever refused, and `get_current_user`
answered 403; the client signs a user out on an authentication failure, so
under the old status the first grant too low for an action would have ended the
session. Covered by `tests/users/test_deps.py`.

An action declares its own level on the class beside `destructive`, defaulting
to `write`. Listing the actions of a node filters by what the caller may run
rather than offering what running would refuse — the same rule as D2d.
`ConnectorPublic` carries `access` for the same reason: a screen that hid a
button by knowing the rules would be a second place the rules live.

`Connector.tab_color` is optional presentation metadata, separate from adapter
options. Create and update accept a six-digit `#RRGGBB` color or null; an omitted
update preserves the color and an explicit null clears it. It is included in
the public connection for every grantee, and only the owner may change it,
under the same rule as the name. Existing connections default to no color.

A refusal is also stated in the answer where the answer already had a place
for it, rather than only as a status the client must interpret. A caller below
`write` gets a page whose columns are not editable and whose insert and delete
are unsupported, with a reason (`as_read_only`); a caller below `structure`
gets a relation that says its columns cannot be changed and why
(`without_column_changes`). Both reuse fields the source already fills in for
what *it* cannot do, so no screen learned a rule.

Consequences kept deliberately:

- A file connector's root stays the **owner's** personal directory, so sharing
  one shares that directory at the granted level. D8 is unchanged.
- A page download is written to the **caller's** own storage.
- An original-content or preview ticket re-checks the caller's current grant
  when it is redeemed; it carries no bearer token or server path.
- Cache keys already carry the caller's id, so sharing a connection does not
  share cache entries.

Known deviation:

- **Groups do not exist.** The old application had them. A grant is resolved
  by `crud.access_of`, so a second source of grants is an addition there rather
  than a change to any route.
- **Nothing is logged.** Who opened what is not recorded; that is a separate
  concern with its own retention question.

Spec: [Sharing a connection](../superpowers/specs/2026-08-29-connector-sharing-design.md)

## D34. An administrator has rights over accounts, not over data

`is_superuser` used to bypass the owner check, which put every connection of
every user into an administrator's list and every data route within their
reach. It no longer does: creating, deactivating and deleting users stays
theirs, and reading somebody's rows needs a grant like anyone else's.

Connector credentials are encrypted precisely so that holding the database does
not mean holding the sources. An unconditional bypass handed back through the
API what the encryption was protecting.

What follows for the two places a superuser was special: `crud.get_with_access`
knows nothing about the flag, and the connector list is what the caller owns
plus what has been granted to them, for everyone alike.

Spec: [Sharing a connection](../superpowers/specs/2026-08-29-connector-sharing-design.md)
