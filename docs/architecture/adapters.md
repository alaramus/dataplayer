# Data sources

What a source type is, what it must implement, and what the two existing types
do. Read this before adding a source type or changing the adapter contract.

Decisions here: D1, D2, D2a, D2b, D2c, D2d, D8, D9, D10, D13, D15, D16, D17,
D20, D21, D22, D23, D25, D26.

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
├── protocol.py      DataAdapter, SupportsCatalog, SupportsNodePath,
│                    SupportsFetch, SupportsRelationModel,
│                    SupportsConnectionString,
│                    ParsesConnectionString, AdapterError, NodeNotFound
├── options.py       the one seam over an options schema, model or union:
│                    json_schema / validate / variants / secret_field_names
├── layout.py        where a field goes in the window that edits it
├── catalog.py       CatalogNode: a union discriminated by kind; NodeKind
├── fetch.py         FetchRequest, FetchResult, closed set of predicates
├── relation.py      relation, column, constraint and index models
├── actions.py       Action, ActionSet, SupportsActions, ActionType,
│                    DeclaresActions, transports, refusals
├── resources.py     ResourceStore: what outlives a request; Pooling
├── registry.py      type registry, AdapterContext, Category, Capability,
│                    capabilities_of
├── routes.py        GET /adapter-types
├── postgres/        options.py (a union by auth_method), session.py, pool.py,
│                    catalog.py, fetch.py, relation.py, adapter.py (facade)
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

Every `FetchColumn` carries `sortable` and its exact ordered list of
`filter_operators`. A file has no index to order by, so its columns answer
`false` and `[]` and the driver refuses a request that asks for either. The grid
learns this from the first answer and stops offering what the source cannot do,
without branching on the source type. The same covers the missing row estimate:
a file has none, so the grid pages by `has_more` alone.

Sorting a page in memory and calling it sorted was rejected — the order would
depend on where the reader stopped. Reading the whole file up to a size ceiling
was rejected too: the answer would depend on the size of the file.

Known deviation:

- **A deep offset over a file costs a full scan.** Paging a file means skipping
  `offset` lines every time. Bounded by the limit ceiling, acceptable while pages
  are read in order.

## D21. A source says where a node lives, and the client never takes an id apart

`SupportsNodePath.path_to(node_id)` answers with every node from the root of
the connector down to that node, the node itself last. `GET
/connectors/{id}/catalog/path?node_id=…` exposes it; a source that lacks the
capability answers 501, and an id that names nothing answers 404.

A node id is the source's own string — PostgreSQL encodes `public.users`, the
file source encodes a path — so the party that built it is the only one able to
read it back. Before this, going to a table from its open tab could only mark a
row that happened to be on the level already: the alternative was to split the
id on the client, which would put a rule about PostgreSQL ids into the screen
and break on the third source type.

Making it part of `SupportsCatalog` was rejected. A source whose ids are opaque
handles from someone else's API may have no way back up at all, and would be
left to either invent one or give up having a catalog — the forcing that D2
exists to prevent. `NodeNotFound` is a class of its own rather than an
`AdapterError` for the same kind of reason: `AdapterError` means the source
failed and is answered with 502, while "there is no such node" is an answer.

Consequences:

- **Identity is a pair, and it already was.** A node is named by its connector
  and its id together — `(connectorId, nodeId)` — which is what panel ids and
  cache keys have always used, so two tables of the same name in two
  connections were never confused. What was missing was not a key but a way
  back up. A single string form of that pair, for a caller that needs one
  handle, stays an encoding the server can add later without touching an
  adapter.
- **The last node of the path answers "what is this".** Full `CatalogNode`s
  rather than a lighter pair of id and name, so nothing needs a second model of
  a node and the same call serves a caller that holds a reference and wants to
  know what it points at.
- **A path is not a trail of crumbs.** A schema is a step of the path and a
  grouping on the screen; a directory is a step of both. The screen translates
  one into the other by node role, in `locationOf` — the same table that lets
  the catalog never ask what type of source it is looking at.

Known deviation:

- **A path is confirmed level by level.** PostgreSQL asks the server once per
  step to be sure each one is really there. Two round trips for a relation is
  nothing next to being told a table exists when it does not, but a source with
  deep trees would want one query for the whole chain.

## D22. A source describes a relation in full, and a column type is an object

`SupportsRelationModel.relation_model(node_id)` returns one `RelationModel`:
columns, constraints, indexes and partitioning together with the relation's
identity and metadata. It is separate from `SupportsCatalog`: an object store
can have a catalog without having relations, so the file source answers 501
rather than inventing a model. PostgreSQL composes this capability beside its
catalog and fetch modules, and `GET /connectors/{id}/relation-model` exposes it.

A type name cannot do three jobs safely. `ColumnType.sql` is PostgreSQL's
`format_type(atttypid, atttypmod)`, which can be written back into DDL;
`category` tells the grid how values behave; the remaining fields carry parsed
facts such as an array element, dimensions, enum labels, length, precision and
scale. `pg_type.typname` is deliberately absent: it says `_int4` for
`integer[]`, while another common spelling drops the `(50)` from `varchar(50)`.
The integration test builds a new table from every returned `type.sql` and
describes it again, so both failures are exercised by a real DDL round trip.

A constraint is one top-level discriminated object with its columns in key
order. It is not copied onto every column: doing that split a composite foreign
key into independent one-column links in the old application. Foreign keys
carry the target's adapter-produced `node_id`, so D21 still holds. The screen
derives per-column badges from these relation-level objects and can show the
same structure tab beside the relation's rows.

PostgreSQL reads four sets in sequence: relations, columns, constraints and
indexes. Each query is written over a whole schema, with the relation name as
an optional value predicate. This leaves schema-wide loading as a caller
change, not a query rewrite, while keeping all client values in placeholders.
The catalog no longer descends into a relation: tables and views are leaves,
and the relation model is the single description of their columns.

Known deviations:

- **There is no server-side cache.** Vue Query keeps a model fresh for five
  minutes, but a second client asks PostgreSQL again. Correct invalidation after
  DDL needs measurements and a design of its own.
- **Only one relation is exposed at a time.** The private PostgreSQL query path
  already accepts no relation predicate, but no public schema-wide response or
  cache uses that form yet.

## D23. A fetched column states its type and operations, and a cell crosses the boundary as lossless text

`FetchColumn` is the complete contract for one displayed column: `name`, the
same structured `ColumnType` used by D22, `sortable`, and an ordered list of
`filter_operators`. Capabilities belong to a column rather than to a whole
result: a source may expose a complex value while allowing only null checks on
it. The file source describes its simple string and number columns but declares
no sorting or filtering; the client never names either adapter.

`FetchResult.rows` is `list[list[str | None]]`. Values cross JSON as canonical
text so `bigint` and `numeric` never pass through a JavaScript number, date and
time keep ISO 8601, boolean is `true` or `false`, binary is uppercase hex with a
`0x` prefix, and JSON is compacted without parsing numeric tokens as floats.
`None` remains distinct from an empty string. PostgreSQL casts server-text types
in the `SELECT`; typed columns stay typed for filtering and sorting, and the
frontend uses the full original string for the viewer and clipboard.

Filters are a discriminated union rather than a partly filled object. Null
checks have no value, `in` requires a non-empty list, and scalar operators
require one text value. Before building the statement PostgreSQL verifies the
column, verifies that the column declares the operator, converts the value to
the driver's native type and rejects invalid input. Identifiers use
`sql.Identifier`, values use placeholders, fixed operator fragments come from a
closed table, and the first version joins every condition with `AND`.

PostgreSQL is deliberately conservative. Number, string and supported date/time
columns compare; string also contains and starts with; boolean, UUID and enum
have equality and `in`; every type has null checks. Sorting is limited to
number, string, boolean, supported date/time, UUID and enum. Extending that set
is an adapter change that arrives in `FetchColumn`, not new frontend knowledge.

Known deviations:

- **Not every canonical text has a specialised editor.** PostgreSQL remains the
  final parser for complex values; the first UI gives them a technical text
  field rather than duplicating every server type in the browser.
- **Filtering has no `OR` or grouping.** The flat request means `AND`; adding
  parentheses needs a recursive expression contract and a matching editor.

## D25. A source issues a versioned row handle, and only it can apply an edit

An editable fetched row carries an opaque handle beside its canonical values.
The client returns that handle unchanged with one column name and one new
canonical value. It never constructs a predicate, takes a node id apart or
decides what identifies a row. The adapter validates the column against current
metadata and builds every identifier with the driver's composition API.

PostgreSQL offers editing only for tables with a primary key. Its handle holds
the fetched primary-key values and `xmin`; an update matches both and returns
the complete canonical row with a new handle. No match is a 409 conflict, so a
second tab cannot silently overwrite a row changed or deleted since it was
read. Generated columns are explicitly non-editable and views, files and
keyless tables state why their rows are read-only in the fetch result.

The old application preferred a special row-id column, then fell back to every
non-null cell. That fallback could match several duplicate rows, ignored nulls,
guessed value types in the browser and had no version check. None of those
predicates cross this boundary.

An update is one cell and one transaction. The full returned row matters even
then: triggers and generated columns may change other cells, while a changed
filter or sort value may move the row out of the current page. The grid therefore
invalidates and rereads the server page after success instead of pretending a
local patch preserves server order.

Known deviations:

- **`xmin` is PostgreSQL-specific and finite.** It stays behind the opaque
  adapter handle and is sufficient for the interval between reading and saving;
  an adapter with an explicit revision column can issue a different handle.

## D26. Insert names supplied columns; bulk delete changes every versioned row or none

Insert and delete are independent capabilities beside update. A source may read
rows without implementing either, and relation-level support and its reason
arrive in `FetchResult`. PostgreSQL inserts into tables, including keyless ones;
it deletes only from tables with a primary key because deletion needs stable row
identity. Views and files keep the commands visible but disabled with the
source's explanation.

An insert request is a list of `{column, value}` objects, not a dictionary and
not a complete row. Absence means “let the source use its default”, an object
whose value is null means SQL `NULL`, and text remains canonical boundary text.
Metadata marks columns `insertable`, `insert_required` and `has_default`, so the
form can omit identity, generated and defaulted fields without copying
PostgreSQL rules. The adapter rereads metadata, rejects unknown or non-insertable
identifiers, and uses `DEFAULT VALUES` when the list is empty. `RETURNING`
produces the same canonical row and optional versioned handle as fetch.

Delete accepts one to 500 opaque row handles and is one statement. PostgreSQL
first counts rows matching every primary key plus fetched `xmin`; the `DELETE`
runs only when that count equals the requested count. One stale or missing row
therefore produces 409 and removes nothing. Duplicate handles are rejected, so
the equality cannot be satisfied accidentally. This all-or-nothing boundary was
chosen over per-row results: a selection is one destructive user action, and a
half-applied action would leave the grid unable to say what still needs consent.

Known deviations:

- **Insert is one row at a time.** Multi-row insert needs row-local validation
  and a deliberate decision between atomic and partial success.
- **Delete is limited to loaded rows.** Selection stops at the current page;
  deleting a server-side filter needs a separate previewable command.

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
