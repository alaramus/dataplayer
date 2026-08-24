# Data sources

What a source type is, what it must implement, and what the two existing types
do. Read this before adding a source type or changing the adapter contract.

Decisions here: D1, D2, D2a, D2b, D2c, D2d, D8, D9, D10, D13, D15, D16, D17,
D20.

## What exists today

Two source types.

**PostgreSQL** — schemas, relations, server-side paging and sorting, a
connection string composed by the driver and parsed back from a pasted one, two
ways of connecting (`user_password` and `no_auth`), and connections that outlive
a request in a pool.

**File** — the personal directory every user owns. The catalog is directories
and files; a delimited file becomes columns, anything else readable becomes
numbered lines. Four actions: create a folder, rename, delete, upload. No
sorting and no filtering, because a file has no index. No connection string.

```
backend/app/adapters/
├── protocol.py      DataAdapter, SupportsCatalog, SupportsFetch,
│                    SupportsConnectionString, ParsesConnectionString,
│                    AdapterError
├── options.py       the one seam over an options schema, model or union:
│                    json_schema / validate / variants / secret_field_names
├── layout.py        where a field goes in the window that edits it
├── catalog.py       CatalogNode: a union discriminated by kind; NodeKind
├── fetch.py         FetchRequest, FetchResult, closed set of predicates
├── actions.py       Action, ActionSet, SupportsActions, ActionType,
│                    DeclaresActions, transports, refusals
├── resources.py     ResourceStore: what outlives a request; Pooling
├── registry.py      type registry, AdapterContext, Category, Capability,
│                    capabilities_of
├── routes.py        GET /adapter-types
├── postgres/        options.py (a union by auth_method), session.py, pool.py,
│                    catalog.py, fetch.py, adapter.py (facade)
└── file/            session.py (root and containment), catalog.py, fetch.py,
                     readers.py, actions.py, adapter.py (facade)
```

## D1. The adapter type registry lives in code, not in the database

A source type is a driver class plus a Pydantic options schema next to it,
registered by a decorator. There is no `adapter` table; `Connector.adapter_type`
is a plain string key. Adding a source type needs no migration.

The old application stored a driver class name in a row and resolved it
dynamically. That is why it has no typing and a 3685-line options file.

## D2. The adapter contract is a Protocol, and capabilities are optional

`DataAdapter` requires only `check_connection()`. Everything else is a separate
`runtime_checkable` protocol — `SupportsCatalog`, `SupportsFetch`,
`SupportsActions`, `SupportsConnectionString`, `ParsesConnectionString` — that a
route checks before using. An adapter that lacks the capability answers 501
instead of faking it.

A queue has no columns and an object store has no SQL, so a contract demanding
everything would force meaningless implementations.

Known deviations:

- **SSRF in `check-draft`.** The endpoint opens a TCP connection to an address
  supplied by the client, which lets an authenticated user map the internal
  network by response timing and error kind. Mitigated by a hard timeout and
  uniform error messages; a host allow-list is the remaining fix.
- **A source that has no catalog has not been seen.** Both types implement every
  capability, so nothing has yet had to say "this one has nothing to browse".
  The mechanism does not stand in the way — such a source opens no panel of that
  role and the middle column does not appear — but the branch is untested and
  there is no wording for it.

## D2a. Sources differ by node kind, not by source family

`list_children()` walks a tree one level at a time, which suits an SQL database
and an object store equally. What varies is the node, and `CatalogNode` is a
discriminated union: only `id`, `name` and `has_children` are shared, so a key
cannot pick up a second meaning. In the old application `schema` held a database
schema name for PostgreSQL and the literal `"directory"` for S3.

Grouping sources into families was rejected: the boundary is arbitrary for
ClickHouse, Kafka, Sheets or parquet-on-S3, and misclassifying a source is
exactly what broke before. One source may contain nodes of several kinds.

Adding a kind means adding a class to the union. `list_children()` raises
`AdapterError` rather than returning an empty list on failure: an empty node and
a broken query must stay distinguishable.

Known deviation:

- **Catalog children are not paginated.** Fine for PostgreSQL, where the count
  is bounded. A directory is not, so the file source refuses to list one holding
  more than 2000 entries rather than truncating silently. Adding a cursor
  changes the contract for every adapter.

## D2b. A driver is a session plus capability modules, composed

`postgres/session.py` knows how to reach the server and nothing else;
`postgres/catalog.py` knows what to ask and nothing about connections;
`postgres/adapter.py` is a thin facade. A new capability is a new module, not
more lines in one class.

Inheritance was rejected on the evidence of the old application: it split that
way, moved backups, monitoring, extensions, replication and the producer into
their own files, and `postgres_extended_adaptor.py` still reached 1243 lines.
One cut cannot absorb growth that happens along many capability axes at once.

Known deviation:

- **It rests on review.** Nothing checks that a capability module keeps out of
  connection handling.

## D2c. A query is never built from client strings

Filters are a closed set of predicates. Column names are validated against the
relation before anything is assembled, identifiers go through
`psycopg.sql.Identifier`, values through placeholders. `limit` has a default and
a ceiling.

The old application formatted a template with client input, additionally
accepted a raw SQL fragment guarded only by a blacklist, and defaulted to
`limit=-1`.

Paging reports `has_more` by reading one row past the page rather than running
`COUNT(*)`; the approximate total arrives on the catalog node. The old
application smuggled an exact count in as a pseudo-column named
`____total_count____` that clients had to know to discard.

## D2d. What a source cannot do is stated in the answer

`FetchResult` carries `sortable` and `filterable`. A file has no index to order
by and the columns of a CSV have no types, so the file source answers `false`
and refuses a request that asks for either. The grid learns from the first
answer and stops offering what the source cannot do, without ever branching on
the type of the source. The same covers the missing row estimate: a file has
none, so the grid pages by `has_more` alone.

Sorting a page in memory and calling it sorted was rejected — the order would
depend on where the reader stopped. Reading the whole file up to a size ceiling
was rejected too: the answer would depend on the size of the file.

Known deviation:

- **A deep offset over a file costs a full scan.** Paging a file means skipping
  `offset` lines every time. Bounded by the limit ceiling, acceptable while pages
  are read in order.

## D8. Every user owns one directory, and a file connector cannot leave it

`USER_STORAGE_ROOT / <user_id>` is created when the user is created. The root of
a file connector is composed by the server from the owner of the connector; the
only option is a folder inside it. A client can name a path but never a root, and
every path is checked against the root before anything is opened — one rule, in
one place.

The old application checked containment in one branch of one method, and the
check let through any ancestor of the root, so the tree could be walked up to
`/`.

Known deviations:

- **A home can outlive its user by a failure.** `crud.delete_user` removes the
  row, commits, then removes the files, so a user is never left able to log in
  with their files gone. If that last step fails the directory stays, and nothing
  in a deployment sweeps it up — `app.seed_storage` does, but it is a development
  tool.
- **Personal storage has no quota.** Nothing counts what a user has stored; only
  a single upload is bounded, by `MAX_UPLOAD_BYTES`.

## D9. An action is one object, and the declaration is the callable

A name, a title, the kinds of node it applies to, a Pydantic model of its
parameters and the implementation live in one class. A driver hands out those
objects and a route calls them. Nothing that is not in the set resolves.

The old application dispatched `getattr(connector, action)(**request_body)`
guarded only by `hasattr`, so every public method of a driver was callable by
name from a client. Its 765-line table of supported actions took no part in the
guard.

Consequences:

- **What a set of nodes admits is asked of the server, in one call.**
  `POST /connectors/{id}/actions` with a list of node ids; the answer is
  everything the source can do, with `applicable` saying which of it every one of
  them admits. The same call decides what the client offers and what the server
  allows, so the two cannot drift — running an action asks `available` again, so
  being listed permits nothing. A flag rather than a shorter list, because a menu
  that lost its entries as the user walked the catalog would teach nobody what
  the source can do. Applicability depends on state as well as kind: the root of
  a connector is an ordinary directory that may not be renamed or removed.
- **An action says what it changes.** `acts_on` is `"node"` for what is done to
  the ticked rows and `"children"` for what is made inside the current level.
  Without it the screen would read the difference off the names of actions. It is
  also what keeps a folder from being deleted by being stood in.
- **Whether one filled form may be applied to many is the action's own
  business.** `Action.bulk`; `Delete` says yes, `Rename` cannot. The flag never
  leaves the server: when more than one node is asked about, the server leaves
  out what did not declare it.
- **The transport is a protocol, not a flag.** An action that carries a file
  satisfies `TakesFile`; `takes_file` in the API answer is an `isinstance` check.
  There are two routes because HTTP has two shapes of body, and each refuses an
  action of the other transport with 415.
- **What to re-read is in the answer.** `ActionResult.reload_node_id` names the
  branch that changed, rather than the client inferring it from the action name.

Known deviations:

- **A file can be uploaded but not downloaded.** Reading bytes back out is
  sub-project 7, so a picture in personal storage can be listed and deleted but
  not opened.
- **Nothing moves or copies.** An action works inside one node of one connector;
  moving a file to another folder means downloading and uploading it again.
- **A conflict is detected, then acted upon.** `create_folder`, `rename` and
  `upload` check that a name is free and then use it; another writer in that gap
  wins. The window is small and the directory belongs to one user.
- **An upload gives no progress and cannot be resumed.** A large file is one
  request that either finishes or leaves nothing behind.
- **Nothing records what was done.** No audit trail, no history of deletions.
- **A set is acted on one call at a time.** Deleting five files is five requests
  run in order; a refusal in the middle is collected and reported rather than
  stopping the rest. Nothing is transactional: four of five may be gone.
- **Applicability costs a call per node.** Ticking a thousand files means a
  thousand filesystem checks behind one request. Bounded by a ceiling of a
  thousand node ids and by the 2000-entry listing refusal.
- **The menu of actions costs two calls.** One about the level being looked at,
  which carries the vocabulary, and one about what is ticked. They could be one
  call taking two sets of nodes, at the price of a request body that says two
  different things.

## D10. What outlives a request belongs to the application

An adapter is built per request and cannot own a connection pool.
`adapters/resources.py` is a container of long-lived objects that names no
driver, created and closed by the lifespan and handed to drivers through
`AdapterContext.pooling`. `postgres/pool.py` holds every psycopg decision about
pooling.

A module-level dictionary inside the driver was rejected: the application would
reach for it rather than be handed it, and closing it at shutdown would make
application assembly name one driver by hand. Pooling above all adapters was
rejected earlier — a file source has no connection at all.

- **The key is the connector plus a hash of its options**, so editing a password
  produces a different pool by itself. An invalidation step elsewhere is a step
  that can be forgotten.
- **A pool loses the reason it could not connect.** It reports only that it had
  nothing to hand out, which would turn a wrong password into "could not reach
  the server". On the failure path, and only there, the session connects once
  directly to learn the real reason.
- **Checks are never pooled.** A check is meant to exercise the credentials, and
  a draft has no identity to key anything by.

Known deviations:

- **A broken connector can wait two timeouts.** The successful path pays nothing;
  a broken one may wait up to twice the connection timeout.
- **A pool outlives the connector it belonged to.** Editing the options or
  deleting the connector leaves the old pool holding open connections until it
  ages out — up to `POOL_MAX_IDLE_SECONDS`. Nothing can be read through it,
  because reaching it needs a key nobody composes any more.
- **Pools are per process and per connector.** Four workers may hold four times
  `POOL_MAX_SIZE` connections to the same database, and nothing coordinates them.
  There is no limit on how many requests one user may have in flight.
- **Nothing reports on the pools.** How many exist, how busy they are and what
  was evicted is invisible; `application_name` in `pg_stat_activity` is the only
  way to see them from outside.

## D20. A switched-off connection is not a source

A connector carries `enabled`. Switched off it stays in the list, stays
readable and stays editable — this is not deleting — but it stops being
something the application will connect to: no catalog, no rows, no action, not
even a manual check, and the health monitor leaves it out of its round.

The refusal is written in `_adapter_for`, the one place a stored connector
becomes a live adapter. Every route that reaches a source goes through it, so
the rule is stated once and a route added later cannot forget to ask; reading
and editing go through `_get_or_404` and are untouched.

The answer is 409. Not 404, because the connector exists and the client knows
it — the list it came from says so. Not 403, because it is the caller's own
and rights are not what is missing.

Rejected: a route of its own, `/{id}/disable`. It is one field of a connector
and it is edited where the others are.

## D13. A source type describes itself, and what it can do is derived

`@register` takes a category — a `Literal`, so a typo does not compile — and a
description. `GET /adapter-types` answers with both plus a list of capabilities.
Nothing lists those capabilities: `capabilities_of` reads them off the driver
class, by `issubclass` against the capability protocols and by the titles of the
action classes it declares. `FILE_ACTION_TYPES` has two readers and no copy.

The old application kept 105 capability names by hand on the client, in a
931-line file, and called that deliberate duplication.

Consequences:

- **A class answers, not an instance.** The question is about a type of source,
  asked before any connector exists, so there are no options and no session. That
  is why `DeclaresActions` is a classmethod rather than a `ClassVar`: a protocol
  holding data cannot be used with `issubclass`, and reaching for the attribute
  with `getattr` would be the `hasattr` dispatch D9 removed.
- **The catalog and the form are two windows, not two steps.** A grid needs 900px
  and a form 520, and one component changing width between them would carry two
  roles. It is also what lets editing an existing connection open its form
  directly, with no step behind it, so the form never offers a choice of type.

Known deviations:

- **A capability is coarser than what a source actually does.** "Read rows" is
  true of PostgreSQL and of a file, and says nothing about the file having no
  index to sort by. The finer answer exists in `FetchResult.sortable` /
  `filterable`, but it belongs to a connection rather than to a type.
- **A capability describes a type, not a node.** The file driver declares
  `Delete`, and the root of a connector may not be deleted. The catalog promises
  slightly more than any particular node allows.
- **A type's description is unchecked free text.** An empty string passes.
- **The catalog search knows no morphology.** Substring matching over name,
  category, description and capability titles, so "migrations" does not find
  "migration" and a Russian word finds nothing.
- **Two categories make for a thin sidebar.** "All", "SQL Databases" and
  "Files & Storage", one type each. Built for the registry D1 anticipates.

## D15. The connection string is a capability, and it is only shown

`SupportsConnectionString`, answered through `POST /connectors/describe-draft`,
which opens nothing. A personal directory is not addressed by a URL, so the file
source does not implement it, the route answers 501 and the row is absent. The
password is never in it, and identifiers go through `quote`, so a user named
`ann@corp` cannot move the host.

Composed on the server rather than from a template on the client, at the price of
a request while the form is typed into: the rule for building a DSN belongs to
the driver.

That holds while the form is still being filled in, too. Defaults put a host and
a port in it before anything is typed, and that is already an address worth
showing — so `DescribesDraft` answers from whatever the form holds, unvalidated,
and `describe-draft` falls back to it when the options do not validate yet. A
classmethod, and for the same reason `ParsesConnectionString` is one: there is no
valid options object at that moment, which is precisely the moment it is asked.
`compose_url` writes the grammar once and both the finished address and the draft
go through it, so the two cannot drift apart in the quoting. None means "not
enough yet", and it reaches the client as an empty string — a source with no
address at all is still the 501, which is a different answer.

This is the shape a capability takes when it has something to say about an
incomplete request, and it was written after the alternative was tried: a client
that composed `postgresql://` itself. That version disagreed with the server
within a day, over `encodeURIComponent` leaving `(` alone where `quote` does not.

Known deviations:

- **The connection string costs a request per edit.** Delayed, and it opens no
  connection, but it is a round trip whenever the values change — now including
  the edits that do not yet compose a full address.
- **The box is no longer empty when a new form opens.** An address pasted into it
  therefore replaces a selection rather than filling an empty field. Ordinary for
  a text box with content, but it is a change in what the field does.

## D16. A way of connecting is a variant of the options, and the union is flat

`PostgresOptions` is `Annotated[PostgresUserPassword | PostgresNoAuth,
Field(discriminator="auth_method")]`, and what a user fills in follows the
variant. One model with optional fields would put the decision about which of
them matter in the form, which is where the old application's options file
started.

Two ways rather than one, because a pick list of one is scenery: `trust` and
`peer` in `pg_hba.conf` are real, and the difference reaches psycopg — a server
that wants no password is sent none rather than an empty one.

Consequences:

- **A schema is no longer necessarily a model.** `Annotated[A | B, ...]` has
  neither `model_json_schema` nor `model_fields`, so `app/adapters/options.py`
  answers for both through a `TypeAdapter`, and every consumer goes through it.
  `secret_field_names` moved there and reads every variant: a field declared
  `SecretStr` by one variant alone must still reach the encrypted blob. That is
  the one place where D4 either holds or breaks without a word.
- **Flat, not nested.** Putting the varying fields in a sub-object would make
  `config` two levels deep, and with it the secret split, which cuts by top-level
  name. This way exactly one key is added.
- **Existing rows needed a data migration.** Pydantic rejects an object that
  names no variant, so every connector saved before this would have stopped
  opening at the first request, not at startup. One alembic revision, data only;
  the statement is a named constant and a test runs it against an old row.
- **The form is told the shape, not the source type.** `readSchema` marks a
  schema as plain or as variants and answers with the fields of each variant in
  the order its model declared them. Order is a statement the server makes: a
  base class's fields always come first, so `_PostgresBase` holds the address
  alone and every variant declares the choice directly under it. The choice
  itself is built from the `mapping` — Pydantic emits the property as a `const`,
  which would render as a text box — and carries a code and a wording, since
  `no_auth` travels to the server and "No auth" is read by a person.

Known deviations:

- **`no_auth` has never reached a server that accepts it.** The compose database
  requires a password, so the tests prove only that none is sent and that such a
  server refuses the attempt with `auth`. Proving the other half needs a server
  configured with `trust`.
- **The order of fields is the order they are declared in.** It is enough to put
  the choice of method under the address, because a base class's fields come
  first — but a field that had to sit between two of its own model's would need
  an ordinal, and there is none.
- **There are two variants, and both belong to one source type.** The mechanism
  takes a union of any width; it has been exercised on the narrowest one.

## D17. A pasted connection string is taken apart by the driver

`ParsesConnectionString` is a classmethod protocol answered by the class, as
`action_types` is: an adapter cannot be built until there are options, and
parsing is what produces them. `POST /connectors/parse-url` opens nothing; a
source with no such address answers 501.

A real "URL only" mode was rejected. A DSN may carry a password, so by D4 the
whole string becomes a `SecretStr` and never comes back — changing one port would
mean retyping the entire string. And it is a second stored form on top of the
variants, so two independent questions would make four shapes. A source that
genuinely has no parts — a REST endpoint, a queue at an address — declares one
`url` field and needs no variant at all.

Consequences:

- **The driver names the way of connecting, not the form.** A string with a
  password is `user_password`, one without is `no_auth`.
- **The box is typed into as well as read, and it keeps no answer of its own.**
  What is typed goes to the driver, the driver produces fields, and the fields
  compose the string that comes back — so a password typed into the box lands in
  the password field and leaves the box. Nothing composed is written into the box
  while it has focus: every prefix of an address parses as some address, so a
  slow typist would have it rewritten under the cursor between keystrokes.

Known deviations:

- **Reading a string guesses the way of connecting.** A URL without a password
  comes back as `no_auth`, even when the password was left out on purpose. Said
  in the interface rather than worked around: the method can be switched back by
  hand.
- **A parsed string travels through the server with its password.** The client
  sent that string a moment ago, so nothing new is disclosed, but it passes
  through a request body and comes back in a response, and no check keeps it out
  of a log.
