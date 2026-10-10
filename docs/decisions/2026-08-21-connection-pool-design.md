# Connection pool

Date: 2026-08-21
Status: agreed
Subproject: 4b

## Goal

Today every request opens its own connection and closes it: a catalog page, a
grid page, a check. For PostgreSQL that is a TCP handshake, authentication and
starting a backend process on every click in the tree.

The subproject removes this without turning the pool into a mechanism on top of
all adapters.

## A premise inherited from subproject 6

A file source has no connection at all. So a "connection pool" cannot be a
shared layer over adapters: what is pooled is not the adapter but the session
of a specific driver. Only one thing can be shared — **a place where a
long-lived object outlives the request**, because an adapter is created anew
for every request and cannot outlive it by construction.

Hence the split: the container knows nothing about connections, and the pool
knows nothing about where it is stored.

## Decisions

### R1. The resource store belongs to the application, not to a module

`app/adapters/resources.py`, without a single driver import:

```python
class Closeable(Protocol):
    async def close(self) -> None: ...


class ResourceStore:
    async def get_or_create[T: Closeable](
        self, key: str, kind: type[T], create: Callable[[], Awaitable[T]]
    ) -> T: ...
    async def aclose(self) -> None: ...
```

It is created in the application's `lifespan` and closed there too. A
module-level dictionary inside `postgres/pool.py` is rejected: ENGINEERING.md
requires passing a dependency rather than reaching for it through a global, and
such a dictionary would have to be closed by a call from `main.py` — the
application assembly would start naming PostgreSQL. With the store, `main.py`
names no driver at all, and a test gets its own instance instead of cleaning up
shared state.

`kind` in the signature is not decoration: it narrows the type without `cast`,
and it also turns "keys of different drivers do not collide" from an
assumption into a check.

### R2. The context gets one field, not two

```python
@dataclass(frozen=True)
class Pooling:
    store: ResourceStore
    connector_id: uuid.UUID


@dataclass(frozen=True)
class AdapterContext:
    home_dir: Path
    pooling: Pooling | None = None
```

The store and the connector identity are only needed together, so this is one
optional field: they have nowhere to diverge — a store without a connector or
the other way round. The absence of `pooling` means a draft: it has no
identity, and so no key. This is the same technique as `home_dir` in decision
D8 — the server puts into the context what the client cannot name — and the
generalisation is made on the second use.

### R3. The key contains both the connector and a fingerprint of the options

`postgres:{connector_id}:{sha256(conninfo)}`.

Editing the password or the host changes the fingerprint and thereby the key —
the old pool is no longer found and leaves through idleness. No separate place
appears that has to remember to reset on PATCH and DELETE; a forgotten reset
would mean working with old credentials.

A key by fingerprint alone is rejected: two users with identical credentials
would share connections, and nothing in the interface would show it.

The fingerprint is a hash, not the string itself: `conninfo` holds the
password, and the key ends up in structures that are natural to log one day.

### R4. The pool is bounded on both sides

- `min_size=0` — an idle connector holds nothing;
- `max_size` — the ceiling of connections per connector;
- a ceiling on the number of pools in the store, above which the least recently
  used one is evicted;
- eviction by idleness, so that a forgotten connector releases its connections;
- checking a connection when it is handed out: one extra round trip to the
  server instead of a random error after the database restarts.

Settings: `POOL_MAX_SIZE`, `POOL_MAX_POOLS`, `POOL_MAX_IDLE_SECONDS`.

Eviction closes a pool that may have a connection handed out. Closing a pool in
psycopg\_pool does not cut a connection already handed out: it is closed when
returned, so a running query lives to the end. This is checked by a test, not
taken on faith.

### R5. The cause of a failure must not be lost

The least obvious place in the subproject. With `min_size=0` a pool on a wrong
password gives `PoolTimeout`, and the original driver error is lost: a
connector with a typo would start answering "could not reach the server"
instead of "authentication error". Today this distinction is checked by tests,
and it must not be lost.

So **on the failure path and only there** the session makes one direct
connection to learn the real cause, and classifies that. The success path pays
nothing extra; a broken connector at worst waits two timeouts instead of one.
This is recorded among the known deviations rather than left unsaid.

### R6. The connection check does not use the pool

`check()` stays a direct connection. The point of the check is to try the
credentials, not to report that the pool is alive; and after a successful check
the pool has nothing to show. `check-draft` has no connector at all, and there
is nothing to build a key from.

## What changes in the code

```
app/
├── adapters/
│   ├── resources.py          new: Closeable, ResourceStore, Pooling
│   ├── registry.py           AdapterContext gets pooling
│   └── postgres/
│       ├── pool.py           new: pool creation and the key
│       └── session.py        query() takes a connection from the pool, if there is one
├── connectors/routes.py      the context is built with pooling for a saved
│                             connector and without it for a draft
├── core/config.py            POOL_*
└── main.py                   lifespan: create the store and close it
```

`PostgresSession` gets an optional pool source. Without it — a direct
connection, as today: that is how the draft, the check and a test that builds
the session itself work.

The import contract is extended: `psycopg_pool` is forbidden everywhere
`psycopg` already is. It is a separate package, so a rule that does not name it
explicitly would not fire.

### Found during implementation

**A pool belongs to the event loop it was created in.** The application has one
loop per process, so in operation this means nothing, but pytest by default gave
each test its own loop, and a pool created in one test turned out unusable in
the next — the failure came from the driver's internal futures, not from the
code. The tests were moved to a shared loop
(`asyncio_default_test_loop_scope = "session"`), that is, to the same model as
the application.

**Connections became visible from outside, and they need a label.** Since a
connection now outlives the request, it hangs in `pg_stat_activity` like a
stranger. `application_name` was added to the connection string, so it is
visible whose connections they are — and that is also exactly how it was
checked that the pool works in the live application, not only in tests.

## How it is checked

Store:

- one object per key; different keys — different objects;
- concurrent requests for one key create exactly one object;
- above the ceiling the least recently used one is evicted, and it is closed;
- an entry idle longer than the limit is closed;
- `aclose()` closes everything and empties the store.

Driver:

- two consecutive queries go through one `pg_backend_pid()`, and without a pool
  through different ones;
- a different options fingerprint gives a different pool;
- a wrong password through the pool still gives `auth`, an unreachable host —
  `network` or `timeout`, and the password is not in the error text;
- closing the pool while a connection is handed out does not cut a running
  query.

Routes:

- two catalog requests for one connector leave one entry in the store;
- `check-draft` creates none;
- a file connector creates none;
- `mypy --strict`, `ruff`, `lint-imports` are clean.

## Not in this subproject

- a pool for anything other than PostgreSQL — there is no second source with a
  connection yet;
- sharing pools between processes: each worker has its own;
- limiting the number of a user's concurrent queries;
- pool metrics and telemetry;
- reusing a connection between steps of one scenario (transactions).
