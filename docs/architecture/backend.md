# Backend

How the application is divided, how it talks to the database, how secrets are
handled, and what the API is. Read this before adding a module, a route or a
migration.

Decisions here: D3, D4, D5, D33, D34, D124, D184.

## What exists today

FastAPI, SQLModel over async SQLAlchemy, PostgreSQL, Alembic. A user signs in,
registers connections, checks them, browses their catalogs and reads rows.
Credentials are encrypted at rest and never leave the server. Every user owns a
personal directory, created with the user.

A connection is identified by its id and by nothing else. Names are a label the
user writes for themselves, and two connections of one owner may share one:
staging and production side by side is the normal case, not a mistake to prevent.
The unique constraint that used to sit on `(owner_id, name)` was never caught
anywhere either — a duplicate reached the client as a 500 out of psycopg — so
removing it took a failure mode with it (`b8c4d2e91a57`). Nothing may therefore
address a connection by name: the API takes ids, and a screen showing a list
shows the name but acts on the id.

```
backend/app/
├── adapters/            source types — see sources/README.md
├── guide/               the user's guide as Markdown pages, and /guide — see D183
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
│   ├── preferences.py   what a user chose for themselves, and the defaults
│   │                    everyone who never chose gets
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
├── system/              operational routes: readiness, cache health, test email,
│                        the server's log (D184)
├── metrics/             agents, the metrics store, collection and history —
│                        see dashboards.md
├── ai/                  the agent: models, keys, conversations, answers — see ai.md
├── seed_database.py     dev tool: rebuilds the demo_lab PostgreSQL fixtures
├── seed_storage.py      dev tool: sample files into a personal directory
├── core/                depends on nothing else in the app
│   ├── access.py        the ordered scale of what a user may do
│   ├── crypto.py        AES-GCM, under the key each purpose names
│   ├── db.py            async engine, session, SessionDep, loop_factory
│   ├── schemas.py       Message, get_datetime_utc
│   ├── email.py         sending and templating
│   ├── config.py        settings
│   ├── logs.py          where each process logs, masking, refs (D184)
│   ├── failures.py      RecordFailures: the request named, a stray exception answered
│   └── security.py      passwords and JWT
├── api/main.py          router aggregation only
└── main.py              application assembly; the lifespan owns the store
```

## Two ways to start it, in three presets

The one entry point is the setup command, which runs the wizard in a
container and starts the stack on the host:

```bash
docker compose --profile setup run --build --rm setup && docker compose up -d --build
```

With no flags it asks every first-run question step by step, and with flags
(after the service name) it runs silently. Either way it fills the generated
secrets in `.env` where the `changethis` placeholder still stands, aligns
the file with the preset and the mode, and starts the stack with a bare
`docker compose up -d --build`. Files and profiles come
from `.env` itself — `COMPOSE_FILE` carries the mode, `COMPOSE_PROFILES` the
preset — so every later compose command follows them without flags. A secret
once chosen is never overwritten, nothing is written before the final
confirmation, and a backup lands in `.env.bak`.

A host with Docker alone runs the same wizard in the `setup` service, which
is behind its own profile so a plain `up` never starts it: the container
writes `.env` on the mounted checkout and never starts anything itself
(`SETUP_CONTAINER`), and the stack is started on the host afterwards with a
bare `docker compose up -d --build` — one pasted line with `&&` between the
two, since declining the wizard exits non-zero and stops the chain.

- **`minimal`** — no compose profile: `db`, `prestart`, the backend,
  `metrics` and `search-keeper`. The read cache is the process-local memory
  one, and `EMBEDDINGS_URL` stays empty, so search by meaning is off.
- **`standard`** — adds `--profile cache`: the shared Redis read cache, and
  `DATA_CACHE_BACKEND=redis` with both cache secrets filled in (D103).
- **`full`** — adds `--profile cache --profile meaning`: the local model the
  search finds meaning with, and `EMBEDDINGS_URL` pointing at it (D220).

`COMPOSE_FILE` in `.env` still names the files `docker compose` reads, so
bare commands follow the mode the setup chose; the setup passes the same
files with `-f` when it starts the stack itself:

- **`compose.yml,compose.override.yml`** — development: `fastapi dev`, sample
  data from `prestart-dev.sh`, the Docker socket, the interface from the Vite
  dev server. A bare `up` starts only what the interface talks to; Adminer,
  Mailcatcher, a test Redis and SSH server and the E2E runner stay behind the
  `tools`/`e2e` profiles and start on request
  (`docker compose --profile tools up -d`, or by naming the service). The
  default preset is `full`, so everything the presets cover runs at once.
- **`compose.yml,compose.prod.yml`** — running it for use: the image's own
  `fastapi run`, `prestart.sh` alone, the built interface served by the backend
  on `APP_PORT`, `restart: unless-stopped`, and no helpers. `FASTAPI_ENV` is
  unset, so a placeholder secret stops the start and the private routes do not
  exist. The default preset is `minimal`.

Managed services belong to no preset. `--enable-services` turns them on
deliberately (D82, D86): in development the socket is already mounted by the
override, while a running installation additionally reads
`compose.services.yml`, which mounts the Docker socket into the backend.
The development helpers (Adminer, Mailcatcher, the test Redis and SSH
server, the E2E runner) belong to no preset either: the `tools`/`e2e`
profiles start them on request.

What development adds lives only in the override; `compose.prod.yml` adds
what running needs rather than undoing anything. `FRONTEND_HOST` reaches every
backend container, because e-mail links and the one CORS origin are made from
it.

## API

```
POST   /api/v1/login/access-token
GET    /api/v1/utils/health-check/
GET    /api/v1/utils/cache-health/
GET    /api/v1/utils/server-info
GET    /api/v1/users/directory
GET    /api/v1/users/me/preferences
PATCH  /api/v1/users/me/preferences
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
POST   /api/v1/connectors/server-key
GET    /api/v1/connectors/{connector_id}/catalog?refresh=false
GET    /api/v1/connectors/{connector_id}/features
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
POST   /api/v1/connectors/{connector_id}/references
GET    /api/v1/declared-references?connector_id=&node_id=
POST   /api/v1/declared-references
DELETE /api/v1/declared-references/{reference_id}
GET    /api/v1/ssh-keys/                 and the rest of /ssh-keys, see sources/ssh.md
WS     /api/v1/terminals                 one socket per terminal, see terminals.md
```

A declared reference is addressed on its own and not under a connection: it has
two ends and belongs to neither of them ([D106](sources/declared.md)).

After changing a route or a schema, regenerate the typed client:
`bash scripts/generate-client.sh`.

## Tests and the servers they need

The suite talks to real servers, and each one is named once, in
`tests/utils/services.py`: where its address comes from and the command that
starts it.

- **The application database is the base.** Without it nothing runs, so a run
  stops at once with one line saying how to start it.
- **Every other server belongs to the tests of one piece** — Redis to the redis
  adapter and the shared cache, a TimescaleDB to the metrics store. A test gets
  the address from `require()`, and when nothing answers there it is skipped
  with the start command. Working on one piece never needs another piece's
  server, and `pytest tests/metrics` runs what it can with what is up.
- **CI passes `--require-services`.** A missing server then stops the run
  before any test: the full suite is the gate, and a pipeline green over
  skipped tests would pass a server it never had.
- A server's address has a default that works on a developer machine, and an
  environment variable CI sets (`TEST_REDIS_URL`, `TEST_METRICS_STORE_URL`).

A piece that needs a server of its own — MySQL for an adapter, say — adds an
entry to `SERVERS`, a service to `compose.override.yml` or its own compose file,
and the same service with its variable to the backend job of
`.github/workflows/ci.yml`. Forgetting the workflow is what
`--require-services` catches.

**Enforced:** `tests/test_services.py` fails when any test module other than the
registry reads the environment, so an address cannot be found around it; and it
checks the skip, the stopped run and the required mode against a real socket.
That a test reaches a server only through an address it got that way — rather
than a literal `localhost` — rests on review.

## Rehearsing the pipeline locally

Settings name `../.env`, so a run started from `backend/` reads whatever the
developer keeps there — `FASTAPI_ENV`, `SMTP_HOST`, `EMAILS_FROM_EMAIL` — and
silently fills gaps that CI, which has no such file, will not. Three pipelines
went red on variables a local run appeared to prove present.

The commonest of those is now a test rather than a procedure:
`tests/core/test_settings.py` fails locally when a setting with no default is
missing from the backend job of `.github/workflows/ci.yml` or from
`.env.example`. Checked by taking the
variable out again.

That leaves what a list of names cannot cover — a value CI sets to something
different, a service alias, a step order. Rehearse those from a checkout without
`.env`, on Linux:

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

Spec: [The connector registry and the adapter contract](../decisions/2026-08-15-connector-registry-design.md)

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

Spec: [The connector registry and the adapter contract](../decisions/2026-08-15-connector-registry-design.md)

## D5. Everything lives in feature modules, and dependencies point one way

The flat layer inherited from the template — `app/models.py`, `app/crud.py`,
`app/utils.py`, `app/api/deps.py`, `app/api/routes/` — is gone. `core` depends on
nothing else in the application, `users` depends on `core`, and `connectors` and
`adapters` depend on `core` and `users`. There are no arrows back.

That is why `init_db` lives in `app/users/bootstrap.py` rather than in
`core/db.py`: creating the first superuser is a users concern, and keeping it in
core would have made core import users.

Enforced by `uv run lint-imports`.

Spec: [Breaking the flat layer up into a users module](../decisions/2026-08-15-users-module-design.md)

## D33. Access to a connection is a grant of an ordered level, and a route states the level it needs

A grant is a row — connector, user, level — and nothing else. The question
"may this user do this here" is a primary key lookup, not a policy to evaluate.

The levels are a total order, and that order is the whole semantics:

| Level | What it admits |
| --- | --- |
| `read` | catalog, relation model, rows, node path, page or whole export, a check of the connection as stored |
| `write` | plus changing rows: cell update, insert, bulk delete |
| `structure` | plus changing shape: add, drop, rename a column, a column default, renaming a relation |
| `own` | plus the connection itself: its options, its credentials — a draft filled in from them included — its grants, deleting it |

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

**Stored secrets fill in a draft for the owner only.** `check-draft` and
`describe-draft` take a connection id so that a secret left empty in the form
is taken from the stored one: the owner changes the port without retyping the
password. Every other option of the draft is the caller's, the host included,
so the same substitution for a grantee would send the owner's password to a
server of the grantee's choosing — a PostgreSQL server may ask for it in clear
text, and a Redis server is sent it with `AUTH`. Both routes ask `own` for the
id. A grantee's form is read-only anyway: it describes what it shows without
the id and checks the connection through `POST /connectors/{id}/check`, which
builds from the stored options and is what `read` admits.

Rejected: substituting for anyone whose draft matches the stored options. The
check is a comparison of option sets that has to track every default and every
field deciding where a connection goes, and the first one it misses hands the
password over. Covered by `tests/connectors/test_grants.py`, against a server
that asks for the password in clear text.

**401 and 403 say different things.** Authentication answers 401 with
`WWW-Authenticate: Bearer` — an unusable token, an unknown subject, an account
switched off — and authorization answers 403. The client signs a user out on an
authentication failure, so while `get_current_user` answered 403 the first grant
too low for an action would have ended the session. Covered by
`tests/users/test_deps.py`.

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

- **Groups do not exist.** A grant is resolved by `crud.access_of`, so a
  second source of grants is an addition there rather than a change to any
  route.
- **Nothing is logged.** Who opened what is not recorded; that is a separate
  concern with its own retention question.

Spec: [Sharing a connection](../decisions/2026-08-29-connector-sharing-design.md)

## D34. An administrator has rights over accounts, not over data

`is_superuser` does not bypass the owner check: creating, deactivating and
deleting users stays an administrator's, and reading somebody's rows needs a
grant like anyone else's. Connector credentials are encrypted precisely so that
holding the database does not mean holding the sources, and an unconditional
bypass handed back through the API what the encryption was protecting.

So `crud.get_with_access` knows nothing about the flag, and the connector list is
what the caller owns plus what has been granted to them, for everyone alike.

Spec: [Sharing a connection](../decisions/2026-08-29-connector-sharing-design.md)

## D124. The backend runs as one process

The image starts `fastapi run --workers 1`; development runs `fastapi dev`, one
reloading process. The count is written out because uvicorn takes it from
`WEB_CONCURRENCY` whenever the flag is absent.

Everything the lifespan builds belongs to the process that built it, and this is
what goes wrong the moment there is a second one:

| What | Decision | Under several processes |
| --- | --- | --- |
| Open transactions | D66 | a statement, Commit or Rollback reaching another process is answered 404 |
| Captured results | D64 | a page, a filter or a download reaching another process is "no longer available" |
| Runs being carried out | D64 | a cancel marks the run `cancelling` without reaching its task, and a query that ran to the end is recorded `cancelled` |
| Jobs being carried out | D81 | a cancel reaching another process is refused with 409 |
| Topics and health monitors | D18, D19 | probing is multiplied; a socket hears only what its own process found out or was told |
| Startup sweeps | D64, D81, D123 | a worker its supervisor restarts ends the live runs and jobs of the others as `interrupted`, marks their source-operation targets unknown and deletes the snapshot a running restore reads |
| Pools and the memory cache | D10, D31 | connections to a source multiply; entries and invalidation are not shared |
| Search answers in flight, shared cells, the search's backoff | D200 | a newer answer does not end an older one in another process; identical cells are asked twice; a dead server is asked again from each process |
| The words and matches of a search inside files | D200 (S7) | a request reaching another process reads `held: false` for a search that is running or held elsewhere |

The first two rows fail at random, by whichever process a request happens to
reach, and development — one process — never shows them. One process is
enough for what the application is: network-I/O bound and asynchronous
throughout (D3), with blocking work on threads.

Rejected: keeping four workers and recording the table as deviations. A
transaction that forgets itself depending on which process a statement reaches is
a broken feature, not a limitation to document. Rejected for now: making every row
multi-process — a shared channel for topics, routing a transaction or a result to
the process holding it, cancellation carried by the row, recovery run once per
deployment. Each is a design of its own, and D104 asks for a measured need before
Redis carries more than the read cache. Scaling out is therefore a design change
and not a setting: every row above is answered first.

**Enforced:** `tests/test_deployment.py` fails when the image names any count
but one, or a compose file names a count at all. Both were checked by putting
`--workers 4` back in the image and `WEB_CONCURRENCY` into a compose file.

Known deviation:

- **Nothing checks at runtime.** A deployment that replaces the command, or
  runs two containers behind one balancer, starts several processes and nothing
  notices. The test holds the files in this repository, not what somebody runs.

Spec: [The backend runs as one process](../decisions/2026-09-13-one-backend-process-design.md)

## D184. The server writes down what went wrong, whole, and a superuser reads it

The log was standard output alone, gone with every rebuild of the container;
the one `basicConfig` that set its level ran as a side effect of importing the
mail module. Worse, a source failure the driver could not name became "Query
failed" and nothing else: the exception was dropped with `from None` and
written nowhere, so neither the person nor anybody else could learn why.

- **One configuration per process**, `core.logs.configure`, called before the
  application is built, by the metrics collector and by the search keeper
  (D214). Standard output keeps its text; with `LOG_DIR` set, each process also
  writes `<process>.log` as JSON lines, rotated by size (`LOG_FILE_MAX_BYTES`,
  `LOG_FILE_COUNT`). Compose puts every process's file on the `app-logs`
  volume, so a rebuild keeps them.
  Uvicorn's own loggers are taken over, so requests and tracebacks reach the
  file. The health check Docker asks every ten seconds, and the panel reading
  the log every three while it follows it, are not written down.
- **Nothing written carries a secret.** Both formats pass `redact`: a password
  in an address, `password=`, `token=`, `ticket=`, `api_key=` in any spelling
  and a bearer token are replaced by `***`.
- **A failure nobody expected is written whole and answered with a ref.**
  `record_failure` logs it at ERROR with its traceback and a six-character ref,
  and the sentence the person sees ends in `· ref K7Q3PD`. That covers an
  exception reaching `RecordFailures` (a 500 that now carries CORS headers and
  a sentence), a driver failure `classify` and the Redis and SSH reducers
  cannot name, a job that raised, a query run that broke and an agent or quick
  chat answer no sentence explains. An expected failure — a refused password,
  an unreachable host, a server refusing a command — is an answer about the
  source and gets no ref.
- **Private text stays out.** A query run and an agent's answer are logged by
  type and frames only (`private=True`): the statement somebody ran and what a
  provider echoed back of a conversation are theirs, not the operator's.
- **Every entry names its request**, method and path without the query string,
  through a context variable `RecordFailures` sets. Uvicorn's own access line
  drops it too: the words of a search travel there (D63), and so does a
  download ticket.
- **The panel is a superuser's.** `GET /logs/` reads the files newest first
  across rotation, filtered by level, process and words, at most 500 entries and
  32 MB read per process per request; `before` pages back and `after` follows.
  **Logs** stands on the rail beside Services, Terminals and Queries for a
  superuser only (a block marked `superuserOnly`), and opens in the panel at the
  foot of the screen (D143).

Known deviations:

- **The prestart container writes to standard output alone.** It runs once per
  start and its failures stop the stack, where `docker compose logs prestart`
  shows them.
- **An access line is written at INFO whatever it answered.** The panel colours
  a 4xx and a 5xx by their status instead of by their level.
- **The reloading parent of `fastapi dev` is not configured.** It only watches
  files; what it says stays on standard output.
- **A ref is not stored with the entity it concerns.** It lives in the sentence
  and in the log, so a log rotated away takes the detail with it.

Spec: [The server's log](../decisions/2026-09-28-server-log-design.md)
