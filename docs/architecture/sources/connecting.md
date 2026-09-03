# Connecting, and what outlives a request

For changing how a connection is described, composed or parsed, and for anything
holding connections or cached answers between requests.

## D16. A way of connecting is a variant of the options

One model with optional fields would put the decision about which of them matter
in the form, which is where the old application's options file started.

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

Spec: [Ways of connecting](../../superpowers/specs/2026-08-23-connection-variants-design.md)

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
  tests exercise both directions against each other.
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

Spec: [Ways of connecting](../../superpowers/specs/2026-08-23-connection-variants-design.md)

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
- Nothing composed is written into the box while it has focus: every prefix of
  an address parses as some address, so a slow typist would have it rewritten
  under the cursor between keystrokes.
- A source that genuinely has no parts — a REST endpoint, a queue at an address
  — declares one `url` field and needs no variant at all.

Known deviations:

- **Reading a string guesses the way of connecting.** A URL without a password
  comes back as `no_auth` even when the password was left out on purpose. Said
  in the interface rather than worked around.
- **A parsed string travels through the server with its password.** The client
  sent that string a moment ago, so nothing new is disclosed, but it passes
  through a request body and comes back in a response, and no check keeps it out
  of a log.

Spec: [Ways of connecting](../../superpowers/specs/2026-08-23-connection-variants-design.md)

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
- **Pools are per process and per connector.** Four workers may hold four times
  `POOL_MAX_SIZE` connections to the same database, and nothing coordinates
  them. There is no limit on how many requests one user may have in flight.
- **Nothing reports on the pools.** How many exist, how busy they are and what
  was evicted is invisible; `application_name` in `pg_stat_activity` is the only
  way to see them from outside.

Spec: [The connection pool](../../superpowers/specs/2026-08-21-connection-pool-design.md)

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

- **The cache is process-local.** Multiple backend workers do not share entries
  or invalidation. TTL bounds the inconsistency until a distributed cache and
  invalidation channel are justified.
- **Invalidation knows connector identity, not upstream identity.** Two saved
  connectors pointing at the same database do not invalidate one another, and
  changes made outside DataPlayer are visible after TTL or explicit Reload.
- **Entries are bounded by count, not bytes.** Fetch itself is bounded to 1000
  rows, but wide values make entry sizes unequal.

Spec: [The catalog and fetch read cache](../../superpowers/specs/2026-08-29-read-cache-design.md)
