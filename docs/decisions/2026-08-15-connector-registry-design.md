# Connector registry and adapter contract

Date: 2026-08-15
Status: agreed, ready for planning

## Goal

The first slice of moving DataPlayer to the new application. When it is done
the user can create a PostgreSQL connection through a form, press "Test
connection" and see the result. Credentials are stored encrypted and are not
returned.

The slice is deliberately narrow. Its job is to settle the decisions that are
most expensive to change later: the connector data model, the shape of the
adapter contract, the way secrets are stored, the module layout.

## Context

The old application (`dbwebtool` + `myquasar`) works, but was written as a
student project: without types and without clear boundaries between layers.
We port ideas, not code.

What DataPlayer got right and is ported:

- the split between "source type" and "concrete connection";
- a small adapter contract: `check_connection`, `get_catalog`,
  `refresh_model`, `fetch`, `close`, `is_active`, `compile_connection_string`;
- asynchrony on every I/O path;
- encryption of credentials at rest.

What is not ported and why:

| What | Why |
| --- | --- |
| `common_option_adapter.py`, 3685 lines | Option schemas of all adapters in one file. A schema should live next to the driver that uses it |
| `Adapter.driver` as a class name in the database + `class_by_name()` | Dynamic import strips typing from both the backend and the frontend |
| Password in a separate config file (`get_password_from_config`) | A secret outside the transaction of the record it belongs to is a source of desynchronisation |
| `database_adapter_cache` — a global dictionary of live connections | No TTL and no account of several uvicorn workers |
| The inheritance chain `base_adaptor_base → base_adaptor → base_adaptor_nosql` | Drags a driver into other drivers' decisions |
| `serverAPI.ts` as the single request layer for the whole application | Replaced by the generated client and hooks inside a feature |
| Hand-written caches in Pinia stores (`TableDataCacheClass`, `catalogStoreHelper`) | Home-made invalidation. Replaced by vue-query |

## Decisions

### R1. The template is not a constraint

`full-stack-fastapi-template` is a starting point. Any part of it can be
rewritten or removed.

### R2. The registry of adapter types lives in code

Each source type is a driver class with a Pydantic options schema next to it.
There is no separate table of adapter types: the source type is a string key
of the registry, stored in the `Connector.adapter_type` field.

The alternative "type in the database, as in DataPlayer" is rejected: it
reproduces exactly the problem the rewrite is undertaken for. For fifty
adapters pluggability means a pip package and a deployment anyway, so dynamic
import gives no real flexibility but takes away all typing.

A hybrid (registry in code plus a table to enable and disable types) can be
added later on top of the registry without breaking anything.

### R3. The backend is asynchronous

`AsyncSession`, `async def` in endpoints, asynchronous adapters. The
template's tests and endpoints are rewritten to async in the same pass.

No new dependencies are needed: `psycopg` 3 is already in the project and
supports async, and `create_async_engine("postgresql+psycopg://…")` runs on it
as well. The first adapter uses the same driver.

Reasoning: the application is by definition busy with network I/O to dozens
of external systems. A synchronous version is bounded by the threadpool size
and would require rewriting every adapter once streaming arrives
(subprojects 4 and 7).

### R4. Secrets are stored in the database encrypted

Non-secret fields go to `Connector.config` (jsonb), secret ones to
`Connector.secrets` (bytea), encrypted with AES-GCM.

The split is made by the schema, not by hand: secret fields are declared as
`pydantic.SecretStr`, and the service sorts values by field type. There is no
list of "which fields are secret", so a field cannot be forgotten. In OpenAPI
`SecretStr` gives `format: password`, and the frontend draws the right input
without extra markup.

The encryption key is a separate variable `CONNECTOR_SECRET_KEY`; the JWT
`SECRET_KEY` is not reused. They have different rotation costs: changing the
JWT key logs everyone out, changing the encryption key is a data migration.
Coupling them yields an operation that cannot be performed.

An external secret store (Vault) is rejected at this stage as unnecessary
infrastructure. The encryption layer is isolated in `core/crypto.py`, so Vault
can be plugged in later without changing the models.

### R5. New code goes in modules; restructuring existing code is deferred

New functionality lives in `app/adapters/` and `app/connectors/`. The
template's flat `app/models.py`, `app/crud.py` and `app/api/routes/` stay as
they are.

A single models file and a single CRUD file for the whole application is the
start of the path that led `common_option_adapter.py` to 3685 lines, so they
need to be broken up. But that work touches `users`, `login` and their tests,
which noticeably widens the first slice while adding nothing to its result.
It is moved to a separate subproject (2a in the table below).

A consequence accepted deliberately: until 2a is done, two ways of organising
code coexist in the backend — flat for `users` and `items`, modular for
connectors. This is a temporary state, not a pattern to follow: new code is
written in modules.

The move to async (R3) is done in the first slice and touches the same files,
but only their content, without moving them.

### R6. The frontend is Vue 3 with the Quasar UI kit

The template's React is replaced by Vue 3 + TypeScript. The `frontend/`
directory is recreated.

The template's main value is kept: generating a typed client from OpenAPI
through `@hey-api/openapi-ts`, which does not depend on the framework. Vite and
Playwright as the e2e tool are kept too; TanStack Query moves from the React
binding to the official Vue binding `@tanstack/vue-query`.

Quasar is chosen because the point of the rewrite is the backend architecture
and end-to-end typing; the UI kit was not a source of the old application's
problems. Replacing it as well would add off-topic risk and lose the one
resource that ports without loss: the accumulated experience and ready-made
components of myquasar.

The template's Tailwind is removed.

### R7. Server state is in vue-query, Pinia holds only client state

The direct opposite of myquasar, where server data is spread across Pinia
stores by hand, each with its own cache and its own invalidation.

vue-query solves this in one way for the whole application: cache, loading
states, invalidation by key, request deduplication. Pinia keeps what the
server does not have: the token, the theme, the interface state.

## Architecture

### Backend

```
backend/app/
├── core/
│   ├── db.py            async engine + AsyncSession
│   ├── config.py        + CONNECTOR_SECRET_KEY
│   ├── security.py      essentially unchanged
│   └── crypto.py        new: AES-GCM encryption of secrets
├── adapters/
│   ├── protocol.py      Protocol DataAdapter
│   ├── registry.py      type registry, registration decorator
│   └── postgres/
│       ├── options.py   PostgresOptions
│       └── adapter.py   PostgresAdapter
├── connectors/
│   ├── models.py        Connector + Public/Create/Update
│   ├── crud.py          database access only
│   ├── service.py       orchestration: config → adapter → check
│   └── routes.py        HTTP
├── models.py            structure unchanged, rewritten to async
├── crud.py              structure unchanged, rewritten to async
└── api/routes/          users, login, utils — rewritten to async
```

In the first slice the template's flat files are only moved to async. Breaking
them up into modules is subproject 2a, see R5.

### Adapter contract

The contract is a `typing.Protocol`, not a base class. A driver inherits
nothing; conformance is checked structurally by `mypy --strict`.

In the first slice the protocol has **one method** — `check_connection()`. The
other six are added in subprojects 3 and 4, once it is clear what their return
types should be: in DataPlayer `get_catalog` returns a bare `dict`, and that is
exactly what we do not port.

```python
class ConnectionCheckResult(BaseModel):
    ok: bool
    message: str
    latency_ms: int | None
    error_kind: Literal["auth", "network", "timeout", "config", "unknown"] | None
```

The method does not let a driver exception out. Driver messages regularly
contain the connection string with the password — DataPlayer has
`safe_connection_string` for that. Here classification and sanitising are part
of the contract rather than something the author of each driver has to
remember.

The check is bounded by a hard 5-second timeout through `asyncio.wait_for`.

### Registry

```python
@dataclass(frozen=True)
class AdapterType:
    name: str                        # "postgres"
    title: str                       # "PostgreSQL"
    options_schema: type[BaseModel]  # PostgresOptions
    factory: Callable[[BaseModel], DataAdapter]
```

Registration is by a decorator when the driver module is imported. It replaces
both `adaptor_factory.py` and `common_option_adapter.py`.

```python
class PostgresOptions(BaseModel):
    host: str
    port: int = 5432
    database: str
    user: str
    password: SecretStr
```

### Live connections are not cached

For a check the connection is opened, checked and closed. A pool will appear in
subproject 4 together with a real `fetch` and will be designed explicitly,
taking several workers into account.

## Data model

```python
class Connector(SQLModel, table=True):
    id: uuid.UUID
    name: str
    adapter_type: str        # registry key, validated against it on write
    config: dict             # jsonb, non-secret
    secrets: bytes           # AES-GCM
    owner_id: uuid.UUID      # FK user.id, ON DELETE CASCADE
    created_at: datetime
    updated_at: datetime
```

- `adapter_type` is a string, not a foreign key. A side effect: adding a new
  source type needs no Alembic migration.
- A composite uniqueness constraint `(owner_id, name)`.
- Cascade from `User` — as for `Item` in the template.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/adapter-types` | List of types and the JSON Schema of their options |
| POST | `/api/v1/connectors` | Create |
| GET | `/api/v1/connectors` | List: own ones; a superuser sees all |
| GET | `/api/v1/connectors/{id}` | Read |
| PATCH | `/api/v1/connectors/{id}` | Update |
| DELETE | `/api/v1/connectors/{id}` | Delete |
| POST | `/api/v1/connectors/{id}/check` | Check a saved one |
| POST | `/api/v1/connectors/check-draft` | Check from the form, before saving |

`ConnectorPublic` has no `secrets` field at all — not masked, but absent.

`PATCH` without secret fields keeps the previous secrets: the user must be able
to fix the port without entering the password again.

`options` in the request body is declared as `dict[str, Any]` and validated in
the service against the schema from the registry. The alternative — a
discriminated union by `adapter_type` — gives exact types in OpenAPI, but turns
into fifty variants in the public API schema: the same
`common_option_adapter.py`, moved to TypeScript. The frontend form is built
from JSON Schema at runtime anyway.

Validation errors are translated to 422 with paths to the specific fields.

`check-draft` takes an optional `connector_id`. If it is passed and the secret
fields are absent from the body, the missing secrets are taken from the saved
connector. This is needed for the editing scenario: the user fixes the port and
presses "Test" without entering the password again. Values from the request
body are not saved anywhere.

## Security

A foreign connector returns 404, not 403: otherwise enumerating identifiers
reveals which connections other users have.

**Known limitation — SSRF in `check-draft`.** By its nature the endpoint makes
the server open a TCP connection to an arbitrary `host:port` sent by the
client. From the response time and the error kind an authenticated user can
map the internal network they have no direct access to. DataPlayer has this
too, with no restriction at all. It cannot be fully closed in the first slice —
the point of the feature is connecting to arbitrary addresses.

Measures in the first slice: a hard timeout, error messages of uniform shape,
and a single function resolving the address before connecting as an extension
point. An allow/deny list of hosts is a separate backlog task.

## Testing

Backend, pytest with `httpx.AsyncClient`:

- ordinary connector CRUD;
- a secret is not returned in `ConnectorPublic`, is not stored in the database
  in plain text (the raw column value is checked), and decrypts back correctly;
- `PATCH` without secret fields keeps the previous secrets;
- a fake adapter registered in the test — checks the registry and the protocol
  without external services;
- `PostgresAdapter` against the test database from compose — checks that the
  contract can be fulfilled;
- a foreign connector returns 404;
- a leak regression: the password does not get into `message` on a connection
  error;
- `mypy --strict` and `ruff` pass.

Frontend:

- `vue-tsc` without errors;
- Vitest on `jsonSchemaToZod` — a pure function;
- Playwright: log in → create a PostgreSQL connector → test the connection
  with a positive result → delete.

**Slice done criterion:** the Playwright scenario passes on a clean database.

## Not in this slice

- `get_catalog`, `refresh_model`, `fetch`, `close`, `is_active` in the protocol;
- a pool and cache of live connections;
- the registry of supported actions;
- any adapter other than PostgreSQL;
- WebSocket, streaming, terminal;
- the AI subsystem;
- breaking `models.py` and `crud.py` up into modules — subproject 2a;
- migrating data from the old application — connectors are created anew.

## Order of work after the slice

| # | Subproject |
| --- | --- |
| 2a | Breaking `models.py`, `crud.py` and `api/routes/` up into the module `app/users/`; after `Item` is removed, only users and login remain there |
| 3 | Catalog: `get_catalog` and `refresh_model` in typed form |
| 4 | Data fetching: `fetch` with paging, filters, sorting; connection pool |
| 5 | Action registry: what a specific adapter type can do |
| 6 | A second, non-SQL adapter (MongoDB or S3) — checking that the abstraction does not leak |
| 7+ | Realtime, AI, grid |

Each subproject gets its own spec, plan and iteration.

## Removing the sample code

The `Item` entity on the backend (model, endpoints, tests) is removed at the
end of the slice, not at the start: while connectors are being written, it
serves as a live working example at hand.

There is nothing to remove on the frontend: the directory is recreated on Vue
per decision R6, and the `Item` screens are simply not carried into it.
