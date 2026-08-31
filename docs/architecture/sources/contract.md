# The source contract

For adding a source type, or changing what every source must answer. What the
two existing types are and where their code sits: [README.md](README.md).

## D1. A source type is registered in code

A driver class plus a Pydantic options schema next to it, registered by a
decorator. Storing a driver class name in a row is what left the old
application with no typing and a 3685-line options file.

- There is no `adapter` table; `Connector.adapter_type` is a plain string key.
- Adding a source type needs no migration.

Spec: [The connector registry and the adapter contract](../../superpowers/specs/2026-08-15-connector-registry-design.md)

## D13. A source type describes itself

`GET /adapter-types` answers from the class, before any connector exists, so a
capability list cannot drift from what the driver implements.

- `@register` takes a category — a `Literal`, so a typo does not compile — and
  a description.
- `capabilities_of` derives capabilities by `issubclass` against the capability
  protocols and from the titles of the action classes the driver declares.
  Nothing lists them by hand.
- `DeclaresActions` is a classmethod, not a `ClassVar`: a protocol holding data
  cannot be used with `issubclass`, and reaching for the attribute with
  `getattr` would be the `hasattr` dispatch [D9](actions.md) removed.
- The type catalog and the connection form are two windows rather than two
  steps, so editing an existing connection opens its form with no choice of
  type behind it.

Known deviations:

- **A capability is coarser than what a source does.** "Read rows" is true of
  PostgreSQL and of a file and says nothing about the file having no index to
  sort by. The finer answer is in `FetchResult`, which belongs to a connection
  rather than to a type.
- **A capability describes a type, not a node.** The file driver declares
  `Delete`, and the root of a connector may not be deleted.
- **A type's description is unchecked free text.** An empty string passes.
- **The catalog search knows no morphology.** Substring matching over name,
  category, description and capability titles, so "migrations" does not find
  "migration" and a Russian word finds nothing.
- **Two categories make for a thin sidebar.** One type each, built for the
  registry D1 anticipates.

Spec: [The catalog of source types, and creating a connection](../../superpowers/specs/2026-08-23-adapter-catalog-design.md)

## D2. Capabilities are optional protocols

A queue has no columns and an object store has no SQL, so a contract demanding
everything would force meaningless implementations.

- `DataAdapter` requires only `check_connection()`.
- Everything else is a separate `runtime_checkable` protocol — `SupportsCatalog`,
  `SupportsContent`, `SupportsFetch`, `SupportsActions`,
  `SupportsConnectionString`, `ParsesConnectionString` — that a route checks
  before using.
- An adapter that lacks a capability answers 501 instead of faking it.

Known deviations:

- **SSRF in `check-draft`.** The endpoint opens a TCP connection to an address
  supplied by the client, which lets an authenticated user map the internal
  network by response timing and error kind. Mitigated by a hard timeout and
  uniform error messages; a host allow-list is the remaining fix.
- **A source that has no catalog has not been seen.** Both types implement every
  capability, so nothing has yet had to say "this one has nothing to browse".
  The mechanism does not stand in the way, but the branch is untested and there
  is no wording for it.

Spec: [The connector registry and the adapter contract](../../superpowers/specs/2026-08-15-connector-registry-design.md)

## D2b. A driver is composed of capability modules

The old application split by inheritance, moved backups, monitoring, extensions,
replication and the producer into their own files, and
`postgres_extended_adaptor.py` still reached 1243 lines. One cut cannot absorb
growth along many capability axes at once.

- `postgres/session.py` knows how to reach the server and nothing else;
  `postgres/catalog.py` knows what to ask and nothing about connections;
  `postgres/adapter.py` is a thin facade.
- A new capability is a new module, not more lines in one class.

Known deviations:

- **It rests on review.** Nothing checks that a capability module keeps out of
  connection handling.

Spec: [The connector registry and the adapter contract](../../superpowers/specs/2026-08-15-connector-registry-design.md)

## D2a. Nodes differ by kind, not by source family

Grouping sources into families was rejected: the boundary is arbitrary for
ClickHouse, Kafka, Sheets or parquet-on-S3, and misclassifying a source is what
broke before. One source may hold nodes of several kinds.

- `list_children()` walks a tree one level at a time.
- `CatalogNode` is a discriminated union; only `id`, `name` and `has_children`
  are shared, so a key cannot pick up a second meaning. The old application's
  `schema` held a PostgreSQL schema name and the literal `"directory"` for S3.
- Adding a kind means adding a class to the union.
- `list_children()` raises `AdapterError` rather than returning an empty list on
  failure: an empty node and a broken query must stay distinguishable.

Known deviations:

- **Catalog children are not paginated.** Bounded for PostgreSQL. A directory is
  not, so the file source refuses to list one holding more than 2000 entries
  rather than truncating silently. Adding a cursor changes the contract for
  every adapter.

Spec: [The catalog of a data source](../../superpowers/specs/2026-08-15-catalog-design.md)

## D21. The source answers where a node lives

A node id is the source's own string, so the party that built it is the only one
able to read it back. Splitting an id on the client would put a rule about
PostgreSQL ids into the screen and break on the third source type.

- `SupportsNodePath.path_to(node_id)` answers with every node from the root of
  the connector down to that node, the node itself last. `GET
  /connectors/{id}/catalog/path?node_id=…` exposes it.
- A source that lacks the capability answers 501; an id that names nothing
  answers 404. It is not part of `SupportsCatalog`: a source whose ids are
  opaque handles from someone else's API may have no way back up at all.
- `NodeNotFound` is a class of its own rather than an `AdapterError`, which
  means the source failed and is answered with 502.
- The path carries full `CatalogNode`s, so the same call serves a caller holding
  a reference that wants to know what it points at.
- Identity is the pair `(connectorId, nodeId)`, which panel ids and cache keys
  already used. A single string form of that pair stays an encoding the server
  can add later without touching an adapter.
- A path step is not a crumb: a schema is a step and a grouping, a directory is
  both. The screen translates one into the other by node role, in `locationOf`.

Known deviations:

- **A path is confirmed level by level.** PostgreSQL asks the server once per
  step. Two round trips for a relation is nothing next to being told a table
  exists when it does not, but a source with deep trees would want one query.

Spec: [A source says for itself where a node lives](../../superpowers/specs/2026-08-24-node-path-design.md)

## D2c. A query is never built from client strings

The old application formatted a template with client input, accepted a raw SQL
fragment guarded only by a blacklist, and defaulted to `limit=-1`.

- Filters are a closed set of predicates.
- Column names are validated against the relation before anything is assembled,
  identifiers go through `psycopg.sql.Identifier`, values through placeholders.
- `limit` has a default and a ceiling.
- Paging reports `has_more` by reading one row past the page rather than running
  `COUNT(*)`; the approximate total arrives on the catalog node. The old
  application smuggled an exact count in as a pseudo-column named
  `____total_count____` that clients had to know to discard.

Spec: [Reading data](../../superpowers/specs/2026-08-15-fetch-design.md)

## D8. One directory per user, and no way out of it

The same rule as D2c for a source made of paths. The old application checked
containment in one branch of one method, and the check let through any ancestor
of the root, so the tree could be walked up to `/`.

- `USER_STORAGE_ROOT / <user_id>` is created when the user is created.
- The root of a file connector is composed by the server from the connector's
  owner; the only option is a folder inside it. A client can name a path but
  never a root.
- Every path is checked against the root before anything is opened — one rule,
  in one place. A segment must be a plain name by the rules of both platforms,
  and symlinks are followed before the check. A name typed into a form, a
  filename inside a multipart upload and an archive entry name ([D53](content.md))
  all go through it.

Known deviations:

- **A home can outlive its user by a failure.** `crud.delete_user` removes the
  row, commits, then removes the files, so a user is never left able to log in
  with their files gone. If that last step fails the directory stays, and
  nothing in a deployment sweeps it up — `app.seed_storage` does, but it is a
  development tool.
- **Personal storage has no quota.** Nothing counts what a user has stored; only
  a single upload is bounded, by `MAX_UPLOAD_BYTES`.

Spec: [The file source](../../superpowers/specs/2026-08-21-file-explorer-design.md)

## D2d. A source states what it cannot do

Sorting a page in memory would make the order depend on where the reader
stopped; reading a whole file up to a size ceiling would make the answer depend
on the size of the file. So the refusal travels in the answer instead.

- Every `FetchColumn` carries `sortable` and its exact ordered list of
  `filter_operators`. A file answers `false` and `[]`, and the driver refuses a
  request that asks for either.
- The grid learns this from the first answer and stops offering what the source
  cannot do, without branching on the source type. A missing row estimate works
  the same way: a file has none, so the grid pages by `has_more` alone.
- A well-formed request that the data refuses is a 200 answer of its own kind,
  not an error. `NoReferencedRows` ([D36](relations.md)) and
  `NullabilityBlocked` ([D37](ddl.md)) are the same shape.

Known deviations:

- **A deep offset over a file costs a full scan.** Paging a file means skipping
  `offset` lines every time. Bounded by the limit ceiling, acceptable while
  pages are read in order.

Spec: [The file source](../../superpowers/specs/2026-08-21-file-explorer-design.md)

## D20. A switched-off connection is not a source

Switching off is not deleting: the connector stays in the list, readable and
editable, but the application will not connect to it.

- No catalog, no rows, no action, not even a manual check, and the health
  monitor leaves it out of its round.
- The refusal is written in `_adapter_for`, the one place a stored connector
  becomes a live adapter, so a route added later cannot forget to ask. Reading
  and editing go through `_get_or_404` and are untouched.
- The answer is 409. Not 404, because the connector exists and the list it came
  from says so; not 403, because it is the caller's own and rights are not what
  is missing.
- `enabled` is one field of a connector, edited where the others are, rather
  than a `/{id}/disable` route.

Spec: [The socket, health and a switched-off connector](../../superpowers/specs/2026-08-24-realtime-and-connector-health-design.md)
