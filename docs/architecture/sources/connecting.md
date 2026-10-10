# Connecting, and what outlives a request

For changing how a connection is described, composed or parsed, and for anything
holding connections or cached answers between requests.

Decisions here: D16, D15, D17, D10, D31, D100, D101, D102, D103, D104, D105.

## D16. A way of connecting is a variant of the options

One model with optional fields was rejected: it would put the decision about
which of them matter in the form.

- `PostgresOptions` is `Annotated[PostgresUserPassword | PostgresNoAuth,
  Field(discriminator="auth_method")]`.
- Two variants rather than one, because a pick list of one is scenery: `trust`
  and `peer` in `pg_hba.conf` are real, and a server that wants no password is
  sent none rather than an empty one.
- `Annotated[A | B, ...]` has neither `model_json_schema` nor `model_fields`, so
  `app/adapters/options.py` answers for both through a `TypeAdapter` and every
  consumer goes through it. `secret_field_names` lives there and reads every
  variant: a field declared `SecretStr` by one variant alone must still reach
  the encrypted blob. That is the one place where D4 either holds or breaks
  without a word.
- The union is flat. A sub-object would make `config` two levels deep, and with
  it the secret split, which cuts by top-level name.
- `readSchema` marks a schema as plain or as variants and answers with each
  variant's fields in declaration order. A base class's fields come first, so
  `_PostgresBase` holds the address alone. The choice itself is built from the
  discriminator `mapping`, because Pydantic emits the property as a `const`,
  which would render as a text box.
- Existing rows needed a data migration: Pydantic rejects an object naming no
  variant, so every connector saved before this would have stopped opening at
  the first request. One alembic revision, data only, with the statement as a
  named constant and a test that runs it against an old row.

Known deviations:

- **`no_auth` has never reached a server that accepts it.** The compose database
  requires a password, so the tests prove only that none is sent and that such a
  server refuses the attempt. Proving the other half needs a server configured
  with `trust`.
- **Field order is declaration order.** Enough to put the choice of method under
  the address, but a field that had to sit between two of its own model's would
  need an ordinal, and there is none.
- **The mechanism has been exercised on the narrowest union.** Two variants, one
  source type.

Spec: [Ways of connecting](../../decisions/2026-08-23-connection-variants-design.md)

## D15. The connection string is composed by the driver

The rule for building a DSN belongs to the driver. A client that composed
`postgresql://` itself disagreed with the server within a day, over
`encodeURIComponent` leaving `(` alone where `quote` does not.

- `SupportsConnectionString`, answered through `POST /connectors/describe-draft`,
  which opens nothing. A personal directory is not addressed by a URL, so the
  file source does not implement it, the route answers 501 and the row is absent.
- The password is never in it, and identifiers go through `quote`, so a user
  named `ann@corp` cannot move the host.
- `DescribesDraft` answers from whatever the form holds, unvalidated, and
  `describe-draft` falls back to it when the options do not validate yet — a
  classmethod, for the reason D17 is one: there is no valid options object at
  the moment it is asked.
- `compose_url` writes the grammar once, so the finished address and the draft
  cannot drift apart in the quoting. `None` means "not enough yet" and reaches
  the client as an empty string; a source with no address at all is the 501.
- **Every source type that has an address writes its own.** PostgreSQL leans on
  libpq; Redis has no library call to lean on — redis-py parses a URL and will
  not write one — so `adapters/redis/url.py` states the grammar once and its
  tests exercise both directions against each other. SSH writes the passwordless
  `ssh://user@host:port` endpoint accepted by OpenSSH, both for a draft and a
  stored connection.
- **One composer keeps the password, and it is named for it.**
  `ComposesSecretUrl.connection_url_with_password` exists for the window that
  shows a started service's credentials once
  ([D89](../services.md)), and has exactly that one caller. Two methods rather
  than a flag, so "does this string carry a secret" is answered by which one
  was called.

Known deviations:

- **The connection string costs a request per edit.** Delayed, and it opens no
  connection, but it is a round trip whenever the values change — including
  edits that do not yet compose a full address.
- **The box is no longer empty when a new form opens.** An address pasted into
  it replaces a selection rather than filling an empty field.
- **A `rediss://` address is refused rather than connected to.** This source
  has no TLS options, and a scheme quietly read as plaintext would be worse
  than a sentence saying it is not supported yet.

Spec: [Ways of connecting](../../decisions/2026-08-23-connection-variants-design.md)

## D17. The driver takes a pasted address apart

A real "URL only" mode was rejected: a DSN may carry a password, so by D4 the
whole string becomes a `SecretStr` and never comes back, and changing one port
would mean retyping the entire string.

- `ParsesConnectionString` is a classmethod protocol answered by the class, as
  `action_types` is: an adapter cannot be built until there are options, and
  parsing is what produces them.
- `POST /connectors/parse-url` opens nothing; a source with no such address
  answers 501.
- The driver names the way of connecting: a string with a password is
  `user_password`, one without is `no_auth`.
- What is typed goes to the driver, the driver produces fields, and the fields
  compose the string that comes back, so a password typed into the box lands in
  the password field and leaves the box.
- An SSH URL changes its host, port and user. Authentication, the browsing root
  and the pinned server key are separate connection choices and stay as they
  were; a password in an SSH URL is refused because OpenSSH does not take one
  there.
- Nothing composed is written into the box while it has focus: every prefix of
  an address parses as some address, so a slow typist would have it rewritten
  under the cursor between keystrokes.
- A source that genuinely has no parts — a REST endpoint, a queue at an address
  — declares one `url` field and needs no variant at all.
- Every field of a connection tells the browser not to fill it, and a secret
  says `new-password` rather than `off`: with nothing said, Chrome read the
  user and password fields as a login form and filled a saved address and
  password into a form for connecting to a database, which then looked ready to
  test and save with somebody else's credentials (U03). What a browser does
  with a form is the browser's to decide, so this is an intent stated and not a
  prevention claimed; `new-password` is the one a browser is least willing to
  disregard.

Known deviations:

- **Reading a string guesses the way of connecting.** A URL without a password
  comes back as `no_auth` even when the password was left out on purpose. Said
  in the interface rather than worked around.
- **A parsed string travels through the server with its password.** The client
  sent that string a moment ago, so nothing new is disclosed, but it passes
  through a request body and comes back in a response, and no check keeps it out
  of a log.

Spec: [Ways of connecting](../../decisions/2026-08-23-connection-variants-design.md)

## D10. What outlives a request belongs to the application

An adapter is built per request and cannot own a connection pool. A module-level
dictionary inside the driver was rejected: the application would reach for it
rather than be handed it, and closing it at shutdown would make application
assembly name one driver by hand.

- `adapters/resources.py` is a container of long-lived objects that names no
  driver, created and closed by the lifespan and handed to drivers through
  `AdapterContext.pooling`. `postgres/pool.py` holds every psycopg decision
  about pooling.
- The key is the connector plus a hash of its options, so editing a password
  produces a different pool by itself. An invalidation step elsewhere is a step
  that can be forgotten.
- A pool loses the reason it could not connect and reports only that it had
  nothing to hand out, which would turn a wrong password into "could not reach
  the server". On the failure path, and only there, the session connects once
  directly to learn the real reason.
- Checks are never pooled: a check is meant to exercise the credentials, and a
  draft has no identity to key anything by.

Known deviations:

- **A broken connector can wait two timeouts.** The successful path pays
  nothing; a broken one may wait up to twice the connection timeout.
- **A pool outlives the connector it belonged to.** Editing the options or
  deleting the connector leaves the old pool holding open connections until it
  ages out, up to `POOL_MAX_IDLE_SECONDS`. Nothing can be read through it,
  because reaching it needs a key nobody composes any more.
- **Pools are per process and per connector.** The backend is one process
  (D124); a deployment running several would multiply `POOL_MAX_SIZE` by their
  number, and nothing coordinates them. There is no limit on how many requests
  one user may have in flight.
- **Nothing reports on the pools.** How many exist, how busy they are and what
  was evicted is invisible; `application_name` in `pg_stat_activity` is the only
  way to see them from outside.

Spec: [The connection pool](../../decisions/2026-08-21-connection-pool-design.md)

## D31. A source opts into bounded read caching

Freshness rules belong to the source, so a source whose rules are unknown is
read directly rather than cached on a guess.

- `DataCache` belongs to the application lifespan beside the resource store. Its
  key names the owner, connector, operation and exact normalized request, so two
  users, connectors, catalog levels, pages, filters or ordered sorts cannot
  share an answer accidentally.
- `SupportsReadCache` chooses a TTL separately for catalog and fetch. PostgreSQL
  keeps catalog levels for 30 seconds and bounded fetch pages for 10.
- A hard entry ceiling evicts the least recently used answer. TTL controls
  staleness, not memory, so neither can replace the other. Errors are never
  stored.
- Identical reads already in flight share one task, which prevents a burst of
  clients from multiplying the same expensive upstream call.
- `X-Data-Cache` reports `hit`, `miss`, `coalesced`, `refreshed` or `bypass`
  without changing the source's response model.
- Every successful row edit, structural change, adapter action, connector update
  or deletion invalidates the entire connector — its entries and its loads in
  flight. Forgetting the flight does the work twice over: a call begun after the
  mutation cannot coalesce with an older read, and the older read can no longer
  store what it returns, because a load stores only while the flight table still
  names it. A failed mutation changes nothing.
- Explicit Reload sends `refresh=true`, skips a live entry and replaces it with
  a source read. Downloads read the source directly, because D28 promises a
  fresh copy.

Known deviations:

- **The default cache is process-local.** That is sufficient because the backend
  is one process (D124). Several processes on the memory default would not share
  entries or invalidation; D102's Redis backend shares both.
- **Invalidation knows connector identity, not upstream identity.** Two saved
  connectors pointing at the same database do not invalidate one another, and
  changes made outside DataPlayer are visible after TTL or explicit Reload.
- **Entries are bounded by count, not bytes.** Fetch itself is bounded to 1000
  rows, but wide values make entry sizes unequal.

Spec: [The catalog and fetch read cache](../../decisions/2026-08-29-read-cache-design.md)

## D100. Read-cache behaviour is independent of its backend

`DataCache` is the protocol used by routes, query execution and the application
lifespan, including cache outcome observation and health. `MemoryDataCache` is
the default implementation. Replacing storage
does not replace D31: an implementation must preserve the exact owner,
connector, area and normalized-request key; source-owned TTL; explicit refresh;
one in-flight load per exact key; and connector-wide invalidation that prevents
an older load from restoring stale data.

The protocol is deliberately the complete operation rather than a dictionary
of values. If callers performed `get`, `load` and `set` themselves, every
backend would expose the race D31 already closed and every route would have to
remember the same invalidation rules.

Spec: [A replaceable read-cache backend](../../decisions/2026-09-04-cache-backend-contract-design.md)

## D101. Shared cache values have one encrypted, versioned wire format

A shared key is namespaced by deployment, wire version, user, connector,
generation and cache area. The exact normalized request is represented by its
SHA-256 digest in the Redis key and repeated in authenticated data with the
complete namespace. A digest collision therefore fails authentication instead
of returning another request's answer. Connector generation is intentionally
outside the user namespace: one mutation invalidates entries belonging to the
owner and every grantee.

The value begins with a DataPlayer marker and a one-byte format version, then
contains JSON validated against the closed Pydantic response type supplied by
the caller. An unknown version or invalid shape is a miss, never guessed or
unpickled. Every value stored outside the backend process is encrypted with
AES-GCM under a cache-only key. Catalog names and arbitrary fetched cells can
both be sensitive, and no reliable field-level classifier exists; TLS and Redis
authentication control access but do not replace encryption at rest.

Spec: [The shared-cache wire format](../../decisions/2026-09-04-shared-cache-wire-design.md)

## D102. Redis accelerates reads but never carries their correctness

The optional `RedisDataCache` keeps completed encrypted entries in Redis and
in-flight tasks in each worker. A connector generation is read before an entry
or flight is chosen and incremented after every successful mutation. Value keys
include that generation. An older load rechecks it before storing, so a late
answer can neither be joined by a post-mutation read nor become visible again.
The deployment shares one LRU index: reads touch it, writes atomically add the
value and evict its oldest members above `DATA_CACHE_MAX_ENTRIES`, and Redis TTL
still expires every value independently.

Invalidation also publishes the connector UUID on a deployment-scoped channel.
Every worker forgets matching local flights. Pub/Sub is prompt notification;
the Redis generation is authoritative because messages can be missed during a
restart. Old-generation values are left to their already bounded source TTL,
which avoids an unbounded key scan on every mutation.

Every Redis command is behind a driver boundary that exposes no driver text.
Connection, authentication, timeout, corrupt-value and listener failures are
cache misses: reads call the source directly, mutations keep their successful
answer, and the cache reports itself unavailable. Redis therefore changes
latency and upstream load, not whether source data can be accessed.

Spec: [An optional shared Redis cache](../../decisions/2026-09-04-redis-cache-design.md)

## D103. Shared caching is configured explicitly and reports degradation

`DATA_CACHE_BACKEND` is `memory` unless a deployment chooses `redis`. Redis
selection also requires a `redis://` or TLS `rediss://` URL (which may carry
password or ACL authentication), a
bounded deployment name and a dedicated 32-byte encryption key. The URL is a
`SecretStr`; neither health nor driver errors expose it. Application assembly
chooses the one backend and owns its startup and shutdown.

`GET /utils/cache-health/` reports backend, `healthy` or `degraded`, whether it
is shared and a safe sentence. Redis degradation keeps HTTP 200 and does not
change `/utils/health-check/`: optional acceleration cannot make the server
unready while its database and sources still work. The in-memory backend always
reports healthy.

**That answer is for an operator and asks for one.** What it says — whether the
installation runs a shared cache, whether it is degraded now, and how much this
process has served — describes the deployment rather than the application, so
the route requires a superuser. `/utils/health-check/` stays the anonymous one,
because a readiness probe has no credentials to offer.

The Compose Redis service is disposable, authenticated and has no volume, and
it starts with the stack: the backend waits for it to answer, so the first
reads after a restart are not misses against a cache that is still starting. It
is a local example, not a production TLS terminator. `.env.example` ships
`DATA_CACHE_BACKEND=redis` against it and also shows an external `rediss://` ACL
URL. The code default stays `memory`, and a deployment that removes the service
changes one line rather than failing to start.

Spec: [Selecting and observing the cache backend](../../decisions/2026-09-04-cache-configuration-design.md)

## D104. Infrastructure Redis remains a measured read accelerator

The cache health response reports process-lifetime counts of hits, misses,
coalesced loads, refreshes, bypasses, invalidations and failures. Together with
the per-response `X-Data-Cache` outcome, these are the evidence a deployment
must collect before proposing another shared Redis responsibility. The counters
reset with the worker and are observations, not durable application state.

There is no such deployment evidence in this repository, so there is no
distributed lock, job fan-out or share acceleration. The infrastructure Redis
connection deliberately exposes no lock, queue or durable-record operation,
and an import contract keeps jobs, queries, services and shares away from its
concrete implementation. Job state, share records and access requests remain
PostgreSQL rows; cached reads remain disposable answers rather than snapshots
any durable workflow may cite as truth.

Spec: [Redis stops at measured read caching](../../decisions/2026-09-04-cache-scope-design.md)

## D105. A connection chooses how long its answers are kept, and says how old they are

The source decides whether its answers may be cached at all; the owner of the
connection decides for how long. `Connector.cache_ttl_seconds` is null for the
source's own window — which is what every connection made before the column
existed still means — zero for no caching, and at most one day, because
anything staler than that is a copy rather than a cache.

- A source that never opted into `SupportsReadCache` is read directly whatever
  number its owner typed. A window says how long, never whether.
- The window covers catalog levels and pages of rows: what somebody is looking
  at, and how stale that may be is a judgement about their data. It stops short
  of the editor's `metadata`, which is a description of a whole database re-read
  as one unit. Which areas it reaches is decided in `connector_may_choose`,
  matched over the closed set, so a fourth area fails to type-check until
  somebody says which side of the line it is on. Every route passes the window,
  including the one that will not use it, so no route is a second copy of the
  rule.
- Changing the window takes effect at once, because editing a connector already
  invalidates its entries and its loads in flight (D31).
- `X-Data-Cache-Age` travels beside `X-Data-Cache`: the seconds since the source
  was actually read, zero when the reply is the read. Neither end knows this
  alone — the screen knows when the answer arrived, the cache knows how long it
  had been kept first — so a grid can say how old its rows are through a browser
  cache in front of a server cache. Memory stores the moment it wrote the entry;
  the shared backend subtracts the key's remaining life from the window it was
  stored for, in the same round trip as the value, so Redis owns that clock and
  no cache value changed shape.
- The screen says whether what is on it may be stale with a small mark riding
  above the reload — "Live" while the answer is the read, a clock once it is
  one that was kept — in the grid's row of commands and in a catalog's. It sits
  in room of its own beside the button rather than over it, and has one width
  in both states, so nothing is drawn on top of the arrow and nothing in the
  row moves. It used to be a control of its own that re-read the source when
  pressed: the same command twice, in two shapes (D112). **How old it is is not
  drawn.** A control whose width follows the age of a page moves while the row
  is being read, so the age is in what is said on hovering — the mark answers
  how old, while the button says what pressing it does. Whether this may be stale is
  a glance; how stale is a question. "Live" lasts five seconds rather than one,
  because a mark that small has to stay long enough to be caught. Freshness
  travels inside the cached value — `{ page, freshness }`, `{ nodes, freshness }`
  — so there is no second client cache to fall out of step with the first (D7).
- **The mark is drawn only where an answer could be older than the read.** A
  source that never opted in keeps nothing whatever its owner typed, and an
  owner who chose to keep nothing meant it; over either, a mark reads as a
  promise about a cache that is not there. Those panels show the reload alone,
  with no room reserved beside it. Where there is something to report the mark
  keeps its place and only changes what it says, so the row is still. Unknown
  counts as no, because a mark that arrives late is easier to read than one
  that appears and goes away.
- The window is set on the connection window's Options page, which exists for
  this and for what follows it: how a connection behaves is nobody's first
  question, and a form asks how to reach a source before it asks anything else.
- The form states durations rather than naming a policy. Each source type
  publishes what it keeps its own answers for, derived from the driver like its
  capabilities, so the default option reads "As this source decides (rows 10s,
  lists 30s)" instead of a phrase about an inside nobody has seen. A source that
  never opted in publishes nothing, and the field says the source is always read
  live and is switched off — no window typed there would change anything.

Known deviations:

- **A window is not a poll.** It decides whether a stored answer may be reused
  when somebody asks again; an open panel that asks nothing still shows what it
  has. Re-reading on a timer is the grid's auto-refresh, which is per grid and
  holds its tick while a cell is being edited.
- **The window is one number for two areas.** Somebody who wants rows kept
  briefly and catalog levels kept for an hour cannot say so.
- **Age is what the cache knows, not what the source knows.** An answer read
  from a replica is reported as old as the read, not as old as the replication
  lag behind it.

Spec: [The freshness window a connection chooses](../../decisions/2026-09-05-connector-cache-window-design.md)

## A file connection stores its folder as a path

The only option a file source has is the folder it points at, read inside the
personal storage of whoever owns the connection. It is stored the way a path is
written: `/` is the root of that storage, `/reports/2026` is a folder in it.

- One form in the table. The value used to be stripped of its separators, so
  the root was the empty string whether the user typed `/` or left the box
  alone, and a stored option that reads like an unfilled field is one nobody
  can tell apart from a mistake.
- It is also the form the catalog copies out of the path bar, so what is
  copied while browsing one connection can be pasted into the folder of the
  next.
- `FileOptions.below_home` is what the driver joins from, and the only reader
  of the stored string. `Path.joinpath` treats a segment beginning with a
  separator as "start again at the file system root", which would leave
  personal storage entirely — the leading `/` is dropped once, in the model
  that owns it.
- Rows written before this were rewritten by a data migration, statement named
  and tested against an old row. Nothing was broken without it: the driver
  joins from either form, and the migration exists so the table holds one.
