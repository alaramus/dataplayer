# Data sources

What a source type is, what it must implement, and what the two existing types
do. Read this before adding a source type or changing the adapter contract.

Decisions here: D1, D2, D2a, D2b, D2c, D2d, D8, D9, D10, D13, D15, D16, D17,
D20, D21, D22, D23, D25, D26, D27, D29, D30, D31, D32, D36, D37, D38, D39,
D40, D41, D42, D43, D44, D45, D46, D47, D48, D49, D51, D52, D53.

## What exists today

Two source types.

**PostgreSQL** — schemas, relations, server-side paging and sorting, streaming
whole-relation export, a
connection string composed by the driver and parsed back from a pasted one, two
ways of connecting (`user_password` and `no_auth`), and connections that outlive
a request in a pool.

**File** — the personal directory every user owns. The catalog is directories
and files, and every leaf declares its ordered representations: delimited data
opens as a table, JSON and JSONL as structured content, Markdown as a rendered
document, and plain files as text. Supported files may also be projected into a
table by an explicit request. Delimited files expose atomic row and header
changes while keeping every column text. A Parquet file and each sheet of a workbook are
datasets: they state their own columns, so they are read as rows and described
like a relation, and a workbook is walked into rather than opened. Five
actions: create a folder, upload, download, rename and delete. Download returns
one file unchanged or archives a directory or selection. No sorting and no filtering,
because a file has no index. No connection string.

```
backend/app/adapters/
├── protocol.py      DataAdapter, SupportsCatalog, SupportsNodePath,
│                    SupportsContent, SupportsFetch, SupportsRelationModel,
│                    SupportsExport,
│                    SupportsConnectionString,
│                    ParsesConnectionString, AdapterError, NodeNotFound
├── options.py       the one seam over an options schema, model or union:
│                    json_schema / validate / variants / secret_field_names
├── layout.py        where a field goes in the window that edits it
├── catalog.py       CatalogNode: a union discriminated by kind; NodeKind
├── cells.py         the canonical text of one value, shared by every source
├── content.py       ordered node representations and bounded content results
├── dataset.py       what only a file format knows about the dataset in it
├── fetch.py         FetchRequest, FetchResult, closed set of predicates
├── export.py        ExportRequest and bounded ExportBatch
├── relation.py      relation, column, constraint and index models
├── actions.py       Action, ActionSet, SupportsActions, ActionType,
│                    DeclaresActions, transports, refusals
├── resources.py     ResourceStore: what outlives a request; Pooling
├── cache.py         bounded read cache, coalescing and connector invalidation
├── registry.py      type registry, AdapterContext, Category, Capability,
│                    capabilities_of
├── routes.py        GET /adapter-types
├── postgres/        options.py (a union by auth_method), session.py, pool.py,
│                    catalog.py, fetch.py, export.py, relation.py, actions.py,
│                    adapter.py (facade)
└── file/            session.py (root and containment), catalog.py, formats.py,
                     members.py (a node inside a file), content.py, download.py,
                     fetch.py, readers.py, records.py, parquet.py, workbook.py,
                     relation.py, actions.py, adapter.py (facade)
```

## D1. The adapter type registry lives in code, not in the database

A source type is a driver class plus a Pydantic options schema next to it,
registered by a decorator. There is no `adapter` table; `Connector.adapter_type`
is a plain string key. Adding a source type needs no migration.

The old application stored a driver class name in a row and resolved it
dynamically. That is why it has no typing and a 3685-line options file.

## D2. The adapter contract is a Protocol, and capabilities are optional

`DataAdapter` requires only `check_connection()`. Everything else is a separate
`runtime_checkable` protocol — `SupportsCatalog`, `SupportsContent`,
`SupportsFetch`, `SupportsActions`, `SupportsConnectionString`,
`ParsesConnectionString` — that a route checks before using. An adapter that
lacks the capability answers 501 instead of faking it.

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

## D27. A source publishes column type choices and alone turns them into DDL

Adding and dropping columns are independent adapter capabilities. Relation
metadata states whether this exact relation supports them, why not, and the
source-owned `ColumnTypeOption` vocabulary. PostgreSQL permits ordinary and
partitioned parent tables; views are not tables, and a child partition directs
the user to its parent so its inherited shape cannot be changed accidentally.

An add request carries a column name, an opaque type code and nullability. The
code is never SQL: PostgreSQL validates it against a closed registry and maps it
to a fixed `psycopg.sql.SQL` fragment. Relation and column names always go
through `Identifier`; metadata is reread before DDL to reject a duplicate or
unknown column, and PostgreSQL's 63-byte identifier ceiling is checked before
the server can silently truncate a name. This preserves D2c even though a type
must become syntax rather than a bound value.

Drop names exactly one current column and uses PostgreSQL's default `RESTRICT`,
never an implicit `CASCADE`. PostgreSQL removes indexes and constraints owned by
that column as part of dropping it, which the destructive confirmation says;
dependencies outside the table block the operation. Both commands invalidate
the relation model and every open row query for the connector, since a schema
change makes both cached shapes stale.

Known deviations:

- **The first type vocabulary is deliberately small.** It covers common scalar
  PostgreSQL types, without length, precision, arrays, domains or user-defined
  types. Expanding it needs typed option parameters, not a raw SQL escape hatch.
- **Add has no inline default.** A non-null column can therefore be added only
  where existing rows permit it. A literal default can be assigned afterward;
  source expressions remain outside the boundary.
- **Columns cannot yet be altered.** Type conversion and default expressions
  need explicit value/expression and `USING` semantics.

## D29. Renaming a column preserves its source identity and lets the source maintain dependencies

Rename is its own optional capability, not add followed by drop. The request
names one current column and one new name; fresh relation metadata rejects a
missing source, a duplicate target and an unchanged name. Both identifiers go
through the driver's identifier composer, and PostgreSQL's 63-byte ceiling is
checked before the server can truncate the target silently.

PostgreSQL performs `ALTER TABLE … RENAME COLUMN … TO …` without `CASCADE`.
The column keeps its identity and data, while PostgreSQL updates constraints,
indexes and other catalog dependencies that refer to that identity. Objects
whose own exposed column name is independent — a view output, for example —
keep their own name. Structure and rows are invalidated after success because
both cached projections name the old column.

## D30. A column default entered by a user is a literal value, never a source expression

Changing a default is an optional adapter capability with two closed actions:
set one text value or drop the default. The text crosses the boundary as data,
not SQL. PostgreSQL quotes it as a literal and asks the target column type to
coerce it; an invalid value is rejected by the source without storing anything.
This preserves empty strings and safely handles quotes while deliberately making
functions, casts and other expressions impossible to enter through the form.

Generated columns are rejected explicitly. After success, relation metadata and
rows are invalidated: metadata exposes the new expression and inserts may now
produce different rows when that column is omitted.

Known deviations:

- **Source expressions are not supported.** Values such as `now()` are stored as
  the literal text `now()` where the column type accepts text. Expressions need
  a separate, source-owned vocabulary rather than a raw SQL field.

## D37. Changing nullability counts the rows in the way, and the count is the answer

Nullability is its own optional capability, not add-and-drop with the data
thrown away and not a variant of the default command. The request names one
relation, one column and the state asked for.

Requiring a value is a question about the rows, so the source asks it first:
before any lock is taken it counts the rows that hold no value in that column,
and answers `NullabilityBlocked` with that count rather than issuing DDL that
would fail. The count stops at 1000 and reports whether it stopped, because an
unbounded scan is not run here any more than it is run for a page of rows. It
is not what makes the change safe — PostgreSQL's verification scan under
`ACCESS EXCLUSIVE` is still the authority, and a row that gains a null in
between comes back as the ordinary safe rejection. It is what makes the refusal
useful: the driver's own message names row data and cannot be passed on.

Allowing no value is a question about the shape, and the shape is already in
the relation model that was read to validate the request. A column in the
primary key and an identity column always have a value, and each is named as
such instead of being sent to the server to be refused. Everything else,
including a partitioned parent whose partition still requires the value, is
left to PostgreSQL.

`NullabilityBlocked` is a 200 answer beside `NullabilityChanged`, discriminated
by `kind`, for the reason `NoReferencedRows` is (D2d): the request was
well-formed and the source is reporting a fact about the data. A count that has
to be read out of a sentence is a count a screen has to parse. Requests that
are wrong about the relation rather than about its rows — an unknown column, a
relation that cannot change columns, a column that already says what is being
asked — stay 422. A `changed` answer invalidates the relation model and the
connector's row queries; a `blocked` answer changed nothing and invalidates
nothing.

Known deviations:

- **Empty rows are not offered a value.** Filling them is a change to every row
  of the table and belongs to a data round with its own confirmation, under the
  literal-value rule of D30.
- **The verification scan is never skipped.** PostgreSQL can validate a
  `NOT VALID` check separately and then adopt it, which is how large tables get
  a `NOT NULL` without a long exclusive lock. That needs a vocabulary for a
  two-step constraint, which this round does not have.
- **One column at a time.** A relation-wide nullability edit would need a
  partial-failure answer, and there is no shape for one.

## D38. A type change is composed by the source, and the way is checked before the table is locked

Changing a column's type is its own optional capability, and it adds no
vocabulary: the target is a code from the `ColumnTypeOption` list D27 already
publishes. The statement is always `ALTER COLUMN … TYPE <target> USING
<column>::<target>`, with the column through `Identifier` and the target from
the closed registry. `USING` is written by the source and never read from a
request — a `USING` field would be a general-purpose SQL channel — but it is
written, because without it PostgreSQL uses assignment casts only and the
commonest change people want fails with advice to supply exactly that
expression.

Three kinds of obstacle are distinguished. Whether a conversion exists at all is
asked of PostgreSQL rather than restated here: `SELECT <column>::<target> FROM
<relation> WHERE false` reads no row, takes no lock, and fails at parse time
when there is no pathway. Whether the rows can be read as the target is
answered exactly by `pg_input_is_valid` when the column is a string type, which
is when the conversion is PostgreSQL's own input function; the source then
counts the rows that would fail, bounded and reported as in D37. Where the
conversion is a cast function there is no non-throwing way to try it, so no
count is offered. Everything that only surfaces from the attempt — a default
that cannot be cast, a view or rule on the column, a value out of range or too
long — is reduced to a sentence by SQLSTATE rather than by driver text, which
quotes the data.

Nothing dependent is dropped to make the change possible, the rule D27 set for
`DROP COLUMN`. PostgreSQL rebuilds indexes and revalidates checks itself; a
default that blocks the change is removed by the user with the command D30 gave
them. `ColumnTypeChanged` and `ColumnTypeBlocked` are one discriminated union
as in D37, and everything that is a fact about the request rather than about
the data is 422.

Known deviations:

- **A lossy conversion is not distinguished from a lossless one.** `numeric` to
  `integer` rounds silently. The screen says once that a type change rewrites
  every value and can lose information; there is no per-pair classification,
  which would be a second implementation of PostgreSQL's cast semantics.
- **A count exists only for string columns.** Elsewhere the failure is named by
  kind. PostgreSQL has no `TRY_CAST`, and running the conversion to find out
  would mean doing the thing being asked about.
- **The target vocabulary carries no parameters.** No `varchar(n)`,
  `numeric(p,s)`, arrays, enums or domains, exactly as for a new column.

## D39. The source names an index, and the method's limits are read from the server

Creating and dropping an index is one capability rather than two: a source that
could make an index and not unmake it would let a user build something they
cannot remove. The gate is its own — a view cannot be indexed and a
materialized view can — so `RelationModel` carries `index_changes_supported`
and its reason beside the column ones, and a caller without a structure grant
loses both at once.

The request carries columns of this relation in index order, a method code and
whether the index is unique, and nothing else. A name is deliberately absent:
an index has no meaning to a user beyond the columns it covers, and PostgreSQL
already derives one and uniquifies it against the schema. Since `CREATE INDEX`
reports nothing, the answer names the index by reading the relation again and
taking the one that was not there before whose columns, method and uniqueness
are the ones asked for. A predicate, an expression, an operator class, sort or
nulls ordering and `INCLUDE` are all out: the first two are the expressions
D2c refuses, the rest need a vocabulary of their own.

The offered methods are a closed registry, but their limits are not restated
here: `pg_indexam_has_property` answers `can_unique` and `can_multi_col`, and
both travel with each method so a screen can grey out an impossible
combination and the source can refuse it without asking the server to fail.
Whether a method suits a column's type is left to the server, because it
depends on installed operator classes, and comes back as a refusal named by
SQLSTATE.

A unique index is the third command the data can stop, after D37 and D38, and
the rows in the way are the groups that repeat. They are counted before
anything is created, bounded and reported as in D37, and the count excludes
groups holding a null because PostgreSQL's default is `NULLS DISTINCT`.
Dropping issues no `CASCADE`, the rule D27 set for a column, and the indexes
behind a primary key or a unique constraint are refused by name from the model
rather than relayed as a code.

Known deviations:

- **The request waits for the build.** `CREATE INDEX CONCURRENTLY` cannot run
  in a transaction block and can leave an invalid index behind, and returning
  before the work is done needs the durable jobs of Phase 4. The model reports
  `valid`, so an invalid index is at least visible.
- **A unique index is not a unique constraint.** They are different objects and
  constraint creation is a separate round.
- **No reindex or rebuild**, and no storage parameters or tablespace.

## D40. A relation publishes what may point at it, and a constraint is a promise the data can refuse

Two constraint kinds are reachable: unique and foreign key. A check constraint
is not, and will not be — its body is an expression, which is what D2c refuses.
Creating and dropping are one capability, for the reason D39 gives, and the
gate is its own third one: a materialized view is indexable and holds no
constraints, a child partition holds its own even though its columns belong to
its parent, so one flag could only be wrong about two of them.

The name is the source's, as in D39, and the answer reads back which constraint
appeared. What a foreign key may point at is published rather than inferred:
`RelationModel.candidate_keys` lists the column sets that carry a unique key —
a primary key, a unique constraint or a bare unique index, but never a partial
one — each named by whatever provides it. The screen offers those and the
adapter checks against those, so a target with no matching key is named instead
of being handed SQLSTATE 42830. The target itself is a catalog node id handed
back as it was given (D21), and the screen finds the candidates through two
ordinary catalog calls rather than by composing an id.

Behaviour on update and delete is the closed `RefAction` set the relation model
already reports. `validated` now travels with every foreign key and check,
because a constraint added `NOT VALID` promises nothing about the rows that
were already there and showing it as enforced is a lie the reader cannot catch.

This is the fourth command the data can stop, so the shape is one module:
`counting.py` holds a bounded count and whether it is the whole truth, and
D37's, D38's, D39's and this one's counts all go through it. A unique
constraint is stopped by values that repeat; a foreign key by rows whose key
names nothing, counted under MATCH SIMPLE so a row with a null in its key is
not counted. The two answers stay separate — `RepeatingValues` and
`UnmatchedRows` — because they lead to different work. A count can itself be
refused, when the two column lists cannot be compared, and the SQLSTATE mapping
therefore travels with the count as well as with the change.

Dropping issues no `CASCADE`, and a primary key is refused outright: without
one a relation's rows cannot be edited at all, since the versioned handle of
D25 is built from the key.

Known deviations:

- **No `NOT VALID` and no `VALIDATE CONSTRAINT`.** A two-step constraint is a
  second state and a second command; the count already says what a validation
  scan would find.
- **No deferrability, `MATCH FULL` or `NULLS NOT DISTINCT`**, and no check or
  exclusion constraints.
- **The request waits for the scan**, as it waits for an index build in D39.
- **No cross-connector references.** The target is a node of the same source.

## D41. A block of cells is one versioned, all-or-nothing edit, and unreadable values are named before anything is written

Pasting travels as rows rather than as cells: D25 versions a row, so a handle
carries the key and the `xmin` it was fetched with, and the cells being changed
hang off it. Every row must still hold that version or nothing is written, and
the answer is the conflict a single-cell edit already gives. The request is
bounded at 500 rows, 100 cells in a row and 2000 cells altogether.

This is the mirror of D37 through D40. There the source counts what is already
in it that contradicts the request; here the rows are fine and the arriving
values may not be readable. Before anything is written, one query checks every
value against its column's type with `pg_input_is_valid` — the function D38
uses — and the cells that fail come back named by request row and column rather
than counted, because the reader is looking at those values and there are at
most two thousand of them. Nothing is written if any cell is rejected. The
query carries the same SQLSTATE mapping the area uses, so a type whose input
function still raises degrades to one honest sentence instead of a 502.

All-or-nothing is a transaction. D26 got it out of a single statement with a
CTE because the session could run only one statement; setting different values
in different rows cannot be done that way without composing per-column casts
into the statement, so `PostgresSession` gained a transaction that runs several
statements on one connection and rolls back unless all of them did what they
said. Each row is one `UPDATE … WHERE key = … AND xmin = …`; a row that matches
nothing is a conflict.

The block lands from the top-left of the selection and is refused before it is
sent if it would run past the loaded rows or the visible columns, or across a
column the source calls uneditable. Nothing is truncated and no row is
invented.

The TSV the grid writes is now lossless: an unquoted empty field means null and
a quoted one means the empty string, in both directions, so the grid's own copy
and paste round-trip exactly.

A copied line also fills the row being inserted, which is how a row is
duplicated. Positional, and exactly so rather than by luck: the grid and the
insert row are built from the same ordered list of visible columns, so the nth
value belongs to the nth field. Values landing on a column the source fills
itself — an identity, a generated column — are left out and named, because a
copied row always carries those and refusing over them would make the gesture
useless. One line at a time: inserting several rows at once is a command this
does not have.

Known deviations:

- **No fill, no new rows in a block paste, no file.** A block taller than what
  is loaded is refused rather than appended; inserting is D26 and importing a
  file is the next slice.
- **The single-cell route stays separate.** It now shares the type check, so
  its refusal names the type, but merging the two paths is a tidy-up.

## D42. A source names a row by whatever it can version, and the order of a page is part of the answer

Two defects had one cause: neither identity nor order was stated, so both were
whatever the plan produced.

The fetch used to add `ORDER BY` only when the user chose a sort. Without one
PostgreSQL returns rows in plan order, and because an `UPDATE` writes a new
version rather than changing one in place, editing a cell sent its row to the
end of the page. The same gap made `LIMIT`/`OFFSET` paging unable to promise
that page two omits page one. So every fetch now ends with a deterministic
tiebreaker appended after the user's own sort: the primary key ascending where
there is one, `tableoid, ctid` where there is not.

The handle of D25 no longer requires a primary key. `ctid` names a tuple's
physical position and is not stable, but it does not need to be: the handle
carries `xmin` and every operation checks it, so `ctid + xmin` says "this exact
version of this row" at least as precisely as `key + xmin` does. Anything that
moves the row changes both, the handle then matches nothing, and the answer is
the conflict it already was — what cannot happen is a write to the wrong row.
On a partitioned parent `ctid` alone is ambiguous, since two rows in different
partitions share one, so the physical identity is `tableoid` and `ctid`
together.

The key is still preferred where the relation has one, because a ctid handle is
fragile in a way the reader cannot see: `VACUUM FULL`, `CLUSTER` or a repack
move every row and invalidate every open page's handles at once, and the reader
is told their row changed when it did not.

Known deviations:

- **A keyless relation still cannot hold its place.** Its rows are ordered
  physically, so editing one moves it. There is nothing stable to order by, and
  the same fact is what makes its handle fragile.
- **Paging stays `LIMIT`/`OFFSET`.** A stable order makes it correct, not fast;
  keyset paging is a separate contract.
- **`ctid` never leaves the handle.** It is not offered as a column to filter
  or sort by.

## D43. Rows move between two sources through the platform, bounded, and all or none

The first command that names two connectors: the relation being written and the
node being read. It lives in the `connectors` module rather than in an adapter,
because an adapter knows itself and nothing else, and asking one to read
another would be the first crack in that. Two connectors mean two permissions,
checked separately against the grants of D33 — writing rows into the target,
reading the node in the source. Neither implies the other.

It is not an import of a file. The file source is one readable source among
several and the relation is one writable target among several; everything
between them — a bounded read, a mapping of names, a lossless text cell (D23),
an all-or-nothing write — belongs to neither.

The read has a ceiling of 5000 rows and pages the source at its own limit to
reach it. More than that is not refused, since that would make the command
useless for what it exists for, but the answer says the rows were cut off.
Anything larger is a durable job with progress and cancellation, which is
Phase 4; raising the number would only move where the request times out.

Columns are paired explicitly, a source column to a target column, and both
sides are validated against what each says it has before anything is read.
Matching by position or by equal names would turn a wrong import into one that
looks right.

The target checks every value against its column's type before writing — the
same pass D41 makes — and answers with the cells that cannot be read: row,
column and the value itself, cut short. The value is echoed because it is the
reader's own file content and because naming a cell without it sends them
hunting. Then one transaction. A partial import is impossible, which is why
there is no downloadable error report: a report of what went wrong part-way
only means something where part-way exists.

`preview` reads the first rows through the same mapping and hands them back. It
answers "have I paired these columns correctly", which is the mistake that
actually happens; it deliberately does not validate against the target, since
the import does that and writes nothing when it fails.

The same bounded read can prepare a relation that does not exist yet. The
connector route first asks the target container's `SupportsCreateRelation`
capability for its type vocabulary, then accepts an explicit source/name/type
mapping and passes the mapped rows to `create_relation`. The source still only
knows how to read itself and the target still only knows how to create itself.
Unlike importing into an existing relation, creation refuses a source beyond
the 5000-row ceiling: silently making a new table from only its first part would
give that table a false identity. The target's transaction keeps its DDL and
first rows all-or-none.

Known deviations:

- **No transformation.** A value crosses as the text the source gave or it does
  not cross. Trimming, date formats and decimal separators need a vocabulary.
- **No upsert and no key matching.** Existing targets receive inserts; a new
  target receives plain columns and rows, with constraints left to D40.

## D45. A CSV is loaded as a table by an action of the source, and the table arrives with its rows or not at all

D43 moves rows into a relation that already exists, which is the half of "load
this file" that a reader rarely has. This is the other half, and it is a
catalog action rather than a route of its own: the button appears in the
catalog menu, and its parameter schema declares the reusable
`file-to-relation` workflow. Nothing on the screen learned anything about
PostgreSQL — that it takes a file, which nodes admit it and what level it needs
are all read off the declaration (D9, D13); the workflow asks the source for
schemas through its catalog and submits the source-declared action. A source
that gains the same workflow tomorrow needs no client change either.

**A relation is created through a capability, not by the action's own SQL.**
`SupportsCreateRelation` has two methods, and it is one capability because
either alone is useless: `new_relation_options` says what a container will
accept a new relation with — `supported`, a `reason` when not, and D27's
`ColumnTypeOption` list — and `create_relation` makes it. Asking a *container*
rather than a relation is what lets a schema the server owns say why it admits
nothing, which is D2d one step earlier than usual; the action reads the same
answer to decide whether to offer itself at all, so the gate is stated once.

**The rows travel with the request.** That is what makes `create_relation` do
two things, and it is deliberate: with a separate create and insert, a value
the column could not take would leave behind an empty relation nobody asked
for, and this platform has no way to drop one. Only the source can put the DDL
and the rows in one transaction — PostgreSQL rolls DDL back like anything else
— so either the table arrives with its rows or nothing is made. Every value is
checked first by the same `pg_input_is_valid` pass D41 and D43 make, and the
rejected cells come back in `ValuesRejected`, the model an insert answers with.
`Transaction` gained `schema_change` for this: `change` fetches, and a
statement returning no rows would fail inside the cursor.

**Every column is text.** A delimited file states no types, and one read off
its rows would depend on how many of them were looked at — the same reason the
file source gives for typing nothing it reads. A column takes another type
afterwards through D38, which counts the rows in the way before it locks
anything. Guessing here and being wrong on row 4001 would be a failed load
instead of a change the reader can make deliberately.

**The reading of a delimited file is shared, not copied.** `adapters/delimited`
holds the delimiter rule, the naming of a header written by hand and the
fitting of a short row; the file source pages a file through it and this action
takes a whole one. Neither adapter imports the other.

**Both ceilings refuse rather than truncate.** At most 5000 rows and 16 MB, and
a file over either is refused with what the limit is. D43 truncates and says so
because it samples a live source; here the reader handed over a whole file, and
a part of one arriving would go unnoticed. Anything larger is the durable job
of Phase 4.

**The destination and columns are explicit.** The schema being looked at is the
initial destination, not a hidden constraint. The workflow lists the existing
schemas and can instead request a new one; PostgreSQL remains the authority and
may refuse creation when the connection lacks that privilege. The table name
starts as the uploaded filename without its extension. Every header column is
selected initially, and the reader may omit or rename columns before the file
is sent. Delimited columns remain text for the reason above.

Known deviations:

- **No inferred structure beyond names.** Columns may be omitted or renamed,
  but there is no inferred type, NOT NULL, default, key or index. Each has a
  command of its own against an existing relation and answers with what stands
  in its way (D37, D38, D39, D40).
- **A taken name is refused, never replaced.** Removing a relation is D46.
- **The file is held whole in memory** while it is parsed, which is what the
  16 MB ceiling is for. Staging it on disk would buy a larger ceiling and no
  new capability.

## D46. An action can be asked what it would do, and a drop answers by doing it and rolling it back

Dropping a relation is the destructive round every earlier one deferred, and
what makes it safe is not a confirmation box. It is knowing what goes with it.

**Asking is a capability of the action, checked the way `TakesFile` is.**
`Previews` is a `runtime_checkable` Protocol with one method, and `ActionInfo`
derives `previews` from an `isinstance` rather than from a declared flag, so
what the API says cannot drift from what the action does. Most actions have
nothing worth previewing — a folder about to be created is described entirely
by the name in the form — and those answer 501.

The answer is an `ActionPreview`: one summary, a list of lines, and `blocked`.
Every part of it is the source's own words; the dialog renders a sentence and a
list and knows nothing about what is being previewed, which is what lets one
generic form show the consequences of a cascade without any part of the client
learning what a cascade is. It is asked again whenever the form changes, since
the whole point is that ticking a box changes the answer, and it needs the
level the action itself needs: reading what a drop would destroy is not a
lesser thing than the drop for anyone deciding whether it is safe.

**The preview is the drop, rolled back.** What a cascade reaches is written in
`pg_depend`, and restating those rules here would be a second implementation of
them — wrong the first time an extension adds a kind of dependency, and wrong
in the worst place, since somebody reads the answer while deciding whether to
destroy something. So `PostgresSession.rehearse` runs the statement inside a
transaction psycopg is told to roll back whatever happens, keeps what the
server said about it, and returns that. What it lists cannot disagree with what
the drop does, because it is the drop.

Two kinds of answer are kept, and the difference matters. A successful
rehearsal raises notices — `drop cascades to view …` — which are the server
describing what it did. A refused one carries the list of what stands in the
way in the DETAIL field of `2BP01`, and only that field is passed on: the text
of an exception is what carries the connection string, so nothing else of a
failure crosses the boundary. Neither is read for meaning; both are shown.

A rehearsal takes the locks the real statement would, so it is held to a two
second `lock_timeout`. A question about what would happen must not become an
outage, and a rehearsal that cannot get the lock says so, which is itself worth
knowing before pressing the button.

`blocked` closes the loop: without a cascade, a relation something is built on
refuses, the preview says so with the list, and the dialog turns the button
off. The kind of relation comes from the catalog's own description of the node,
because `DROP TABLE` does not drop a view and PostgreSQL's complaint about that
names neither.

Known deviations:

- **One relation at a time.** `bulk` is false, unlike deleting files: one list
  of consequences cannot be told apart into five relations' worth by whoever
  reads it.
- **The preview is a moment, not a promise.** Something can come to depend on
  the relation between the question and the answer; the drop is what decides,
  and it refuses on its own terms.
- **A preview is asked for one node.** A form applied to several would come
  back as several answers, and nothing on the client knows what to call each of
  them. No action offered for a set previews today.
- **An open tab outlives what it shows.** A dropped relation leaves its data
  tab in place, to fail on its next read like any node that has gone; the
  workspace can follow a renamed node (D32) and has no word yet for one that
  is not there at all.

## D44. A whole export is a source-owned row stream, never an unbounded fetch

The current-page download of D28 repeats one bounded `FetchRequest`; an export
of every matching row does not. `SupportsExport` takes the node, committed
filters, ordered sort and visible columns, and yields `ExportBatch` objects of
at most 500 rows. There is no limit or offset in that request. A source either
has a real streaming read or does not implement the capability; paging
`SupportsFetch` until it stops would make a changing source several snapshots
and would put offset cost in the platform rather than in the driver.

PostgreSQL is the first implementation. One validated query stays open through
a server-side cursor and each batch crosses the adapter boundary as D23's
lossless text cells. The requested sort keeps its source-owned stable
tie-breaker, filters and identifiers go through the same validation and safe
composition as a page, and only the requested visible columns are selected.
The file source deliberately does not opt in: D49's node download action and
exporting a tabular interpretation are different operations.

CSV remains outside the adapter. The connector layer encodes one batch at a
time with D28's null and quoting rules and writes a `.part` under the caller's
personal `downloads/<connector-id>` directory. A clean end atomically renames
it; failure or cancellation removes it. The request then returns only a row
count, filename and one-minute signed ticket for that exact stored path. A
normal browser download follows the ticket without assembling a whole Blob in
JavaScript, so both sides of the HTTP boundary remain bounded in memory.

Known deviations:

- **It is a long request, not a job.** There is no durable progress, resume or
  background completion. Those need the job lifecycle in Phase 4; an upstream
  timeout or full disk refuses the export rather than returning a truncated
  success.
- **A ticket is reusable until it expires.** It is a bearer capability for one
  already-created file, not a second account session. One-time redemption
  would require shared state across backend processes.

## D31. A source opts into bounded read caching, and a successful mutation drops what it cached

`DataCache` belongs to the application lifespan beside the resource store. Its
key names the owner, connector, operation and exact normalized request, so two
users, connectors, catalog levels, pages, filters or ordered sorts cannot share
an answer accidentally. The source opts in through `SupportsReadCache` and
chooses a TTL separately for catalog and fetch; a source whose freshness rules
are unknown is read directly. PostgreSQL keeps catalog levels for 30 seconds and
bounded fetch pages for 10.

The cache has a hard entry ceiling and evicts the least recently used answer.
TTL controls staleness, not memory, so neither can replace the other. Errors are
never stored. Identical reads already in flight share one task, which prevents a
burst of clients from multiplying the same limited or expensive upstream call.
The `X-Data-Cache` response header reports `hit`, `miss`, `coalesced`,
`refreshed` or `bypass` without changing the source's response model.

Every successful row edit, structural change, adapter action, connector update
or connector deletion invalidates the entire connector. Invalidation removes the
connector's entries and forgets its loads in flight, and forgetting the flight
is what does the work twice over: a call begun after the mutation cannot
coalesce with an older read, and that older read can no longer store what it
returns, because a load stores only while the flight table still names it. So an
older read may finish for the callers that started it and cannot insert its
stale answer after the mutation. A failed mutation changes nothing. Explicit Reload sends
`refresh=true`, skips a live entry and replaces it with a source read; downloads
continue to read the source directly because D28 promises a fresh copy.

Known deviations:

- **The cache is process-local.** Multiple backend workers do not share entries
  or invalidation. TTL bounds the inconsistency until a distributed cache and
  invalidation channel are justified.
- **Invalidation knows connector identity, not upstream identity.** Two saved
  connectors that point to the same database do not invalidate one another,
  and changes made outside DataPlayer are visible after TTL or explicit Reload.
- **Entries are bounded by count, not bytes.** Fetch itself is bounded to 1000
  rows, but wide values make entry sizes unequal. A measured byte budget may
  replace the count ceiling later.

## D32. Renaming a catalog node returns its replacement identity, and open work follows it in place

PostgreSQL exposes relation rename through the same action registry used by the
file source, not through a source-specific route or client branch. The action is
offered for non-system tables, partitioned tables, views and materialized views.
Its parameter schema accepts one exact new name, rejects surrounding whitespace
and PostgreSQL names over 63 bytes, and the adapter checks the fresh schema for
an existing relation before composing identifiers with `psycopg.sql.Identifier`.
The source chooses `ALTER TABLE`, `ALTER VIEW` or `ALTER MATERIALIZED VIEW` from
the catalog node it produced; no kind or SQL fragment comes from the client.

A relation id contains its name, so rename changes identity as well as a label.
`ActionResult.replacement` therefore carries `old_node_id`, `new_node_id` and
the new title. The catalog reloads the source-named parent, while the workspace
replaces rows and structure panel identities in its layout tree without moving
their tabs. The client copies the opaque ids and never constructs the new one.
This replacement shape belongs to the common action boundary so a future file
rename or object-store move can preserve open work by returning the same fact.

Known deviations:

- **Only open rows and structure panels follow the replacement.** Saved grid
  state remains under the old node id, so filters and column layout begin fresh
  under the new identity. Migrating that state needs an explicit ownership and
  expiry rule rather than copying local-storage keys opportunistically.
- **External dependants follow PostgreSQL's own rename semantics.** Objects tied
  to the relation identity continue to work; text outside PostgreSQL's dependency
  graph is not searched or rewritten.

## D36. A source issues the target of a reference, and the client never pairs the columns

A fetched page says which foreign keys the relation has: `FetchResult.references`
carries, for each one, the source's own name for it, its columns in key order,
and a title for the target to put in a tooltip. It is one object per key, not a
mark on each column, for the reason D22 gives: the old application copied a
constraint onto every column it touched and thereby split a composite key into
independent one-column links.

`SupportsReferences.follow_reference` takes back the name of one reference and
the values one row holds for its columns, and answers with a place to go. What
the client never does is the pairing: which of the target's columns each local
one stands for is read from the source at the moment of asking, and so are the
target's identity and what it can be looked up by. The client's whole influence
on the resulting query is which reference of which row it pointed at.

The answer is a discriminated union. `ReferencedRows` carries the target as a
whole `CatalogNode` — the same model `path_to` answers with (D21), so the screen
opens it, names its tab and decides whether it can be described with the tables
it already has — together with equality filters in the same closed vocabulary a
typed filter uses. `NoReferencedRows` carries a reason: a key with a missing
value names no row, and a key standing on a type this source cannot compare
cannot be looked up. Both are answers about the data rather than failures of the
request, which is D2d.

A row handle was rejected as the way to name the row. Handles exist only where
the source can version a row, and a keyless table can still hold a foreign key.
The values travel instead, as canonical text, which is what the page already
holds.

PostgreSQL reads its keys from `pg_constraint` on every page rather than
remembering them: `confrelid` is an oid, so a target renamed since the page was
read answers with the name it has now, and a constraint dropped since is refused
by name rather than turned into a predicate over a key that no longer exists.
The target node comes from `path_to`, so a relation arrived at by following a
key is described exactly as one walked into.

Consequences:

- **Following a key is a read.** The route asks for `read` access and no more:
  it looks at rows the caller may already read.
- **The predicate is a request the fetch route would have accepted anyway.**
  There is no second validation path — the target's own fetch checks the column,
  checks that the column declares the operator, and coerces the value, exactly
  as it does for a filter somebody typed.

Known deviations:

- **Only the forward direction exists.** Going the other way — from a row to the
  rows elsewhere that point at it — needs a search across a whole schema for keys
  arriving at this relation, and a way to say which of several found relations is
  meant. That is a slice of its own.
- **A page costs one more catalog query.** The keys are read beside the columns
  on every fetch. The bounded read cache (D31) absorbs repeated paging, and
  nothing measures the difference yet.

## D47. A node declares its ordered representations, and opening content is not fetching rows

`CatalogNode.representations` is the source's ordered answer to “how may this
node be opened?”. The first entry is preferred; the rest are explicit
alternatives. Each entry has a closed `kind` and source-owned wording. The
client neither infers a viewer from a suffix nor assumes that every readable
leaf has rows. PostgreSQL relations declare `table`; a file may declare `json`,
`jsonl`, `text`, `table`, several of them, or none while its viewer is not yet
implemented.

The boundary deliberately has two operations. `SupportsFetch` answers a
tabular question with columns, rows, sorting and filtering capabilities.
`SupportsContent` answers `ContentRequest` with one bounded native
representation. Asking to open a JSON document therefore cannot silently
flatten it into rows, and asking for a table cannot silently fall back to text.
A viewer unsupported by the node is a 422; a source without content viewers is
the ordinary capability-level 501.

The first content results are a bounded text preview, one JSON value, and a
page of JSONL values. Their shapes are discriminated unions rather than an
untyped payload. JSON objects keep ordered entries, arrays keep nesting, and
scalars keep their kind. Numbers remain lexical text across the boundary so a
JavaScript number cannot round an identifier (D23). An invalid JSON document
stays in the JSON viewer as source text with the parser's position. JSONL is
independent by physical line: one invalid or oversized line is shown and named
without hiding the valid values around it, and paging counts non-blank records
while retaining their physical line numbers.

Bounds belong to the representation. Text reads at most 256 KB. A whole JSON
document is parsed only up to 4 MB because there is no honest partial tree;
above that, the same JSON viewer shows a bounded source preview and the reason.
JSONL pages at most 100 records and 4 MB of source, and reads each physical
line through a 1 MB ceiling. All blocking file work runs in a worker thread.

**View as table** is retained as a useful alternative, not as the meaning of
opening JSON. It uses the existing fetch boundary. The whole JSON/JSONL file
decides its columns before paging, so every page has one stable shape; a
top-level object is one record, an array supplies records, and values without
object keys use one `value` column. The projection is capped at 4 MB and refuses
invalid input with its reason. It is offered by JSON and JSONL, and by CSV and
TSV as their natural representation. A text file does not offer it: numbering
the lines of a source file produced a table with one column and no meaning.

Known deviations:

- **Catalog classification is by filename.** Opening the selected node checks
  its bytes, but listing a directory does not open every file. A file with a
  misleading suffix can therefore advertise a view that it later refuses.
- **Only PNG and JPEG have a binary representation.** Audio, video, PDF,
  archives and other image formats remain visible and can still be selected
  for a source-declared download action, but explain that no viewer exists yet.
- **Whole-document JSON has a 4 MB parse ceiling.** Larger documents have a
  source preview but no structural navigation. Streaming selection inside a
  document is a separate capability, not an unbounded response.
- **Content reads are not cached.** Reopening or paging JSONL reads the file
  again. A file source has not opted into D31; what a save must match is
  versioned by the editor read of D48 instead.
- **The document viewers have no screen.** Image uses `read_content`, while
  text, JSON and JSONL open the D48 editor. Their bounded results remain tested
  because paging a large JSONL file is the one thing the editor's ceiling
  cannot do, and removing them would take that with it.
- **The table projection equates an absent key with JSON null.** Both become the
  grid's `None`; the native JSON viewer preserves the original distinction.

## D48. Editing a document is a capability of its own, and a save must still match the version that was read

`SupportsContentEdit` is separate from `SupportsContent`, and a source may have
either. `read_editor_content` returns the whole source, its filename, an
optional language hint, an optional validation kind and an opaque `version`;
`update_content` takes that version back and replaces the document. A source
without the capability answers 501, as every other optional capability does.

The two reads are kept apart because a viewer is allowed to bound, page and
parse, and none of those results is the document. What `read_editor_content`
returns is exactly what a save is compared against.

The version is a SHA-256 of the bytes read, and the client only carries it.
A mismatch is 409 with nothing written. A modification time was rejected: its
granularity hides a change, and it moves when none happened. A file source has
no transaction to borrow a row version from (D25).

Both sides are bounded at 4 MB. Above it the read returns a prefix with
`writable=false` and the reason; a file that is not valid UTF-8 comes back
unwritable and names the byte that failed, because bytes that had to be guessed
at cannot be written back. Editing needs `write` on the connection (D33), and a
reader holding only `read` gets the document unwritable with that as the reason
rather than a failure at the save.

Before writing, the source validates what the format promises: a `.json`
document must parse, and every non-blank line of a `.jsonl` document must, with
the position of the first failure. The browser lints as well, but the file is
the server's. The write goes to a temporary file in the same directory, is
flushed and synced, takes the original's mode and replaces it with
`os.replace`, so a failure leaves the previous document rather than half of the
new one.

A content tab has one mode. Opening a file opens its source; there is no
viewer/editor switch, and the JSON tree was removed from the screen rather than
kept as a second, unwritable view of the same document.

Known deviations:

- **Nothing watches an open file.** A change underneath is found by the version
  check at save, not before it.
- **Only text, JSON and JSONL are editable.** Everything the file source calls
  binary or opaque is refused, media and PDF included.
- **The document is held whole on both sides.** Above 4 MB the editor is
  read-only; there is no partial or streaming edit.

## D49. Download is a source-declared action over selected nodes, and a preview is bounded and verified

Download is not a property of a file node or its viewer. A source declares an
ordinary action named `download`, and the callable action implements
`ProducesDownload`. The action listing derives `downloads` from that protocol,
as it derives file upload and preview transports, so every adapter uses the
same Actions menu without an adapter-name or action-name branch.

The action receives the whole non-empty selection once. The file source returns
one selected file unchanged. More than one node, or any selected directory,
becomes one recursive ZIP: `<directory>.zip` for one folder and `download.zip`
for a set. Empty directories are retained. ZIP staging runs in a worker thread
and a temporary file, with ceilings of 10,000 entries and 2 GiB of uncompressed
source bytes; symbolic links and ambiguous duplicate top-level names are
refused. The archive is removed after the stream closes.

The authenticated action request issues a signed one-minute ticket containing
the user, connector, action and opaque node ids. Following it with a normal
browser navigation re-checks the user, access, enabled connector, action and
every target before asking the source for `ActionDownload`. A server path never
enters the ticket or the client. This transport is available to every adapter;
the file adapter is only its first implementation.

`image` is the first binary `NodeRepresentation`. The catalog classifies PNG
and JPEG by name because listing must not open every file, while the content
read verifies the bytes with Pillow and returns the verified MIME type, width,
height and byte length. Its dedicated preview ticket returns the verified bytes
inline with `nosniff`; it is not the download action's ticket or transport.

Preview has two independent ceilings: 20 MB of encoded bytes and 40 million
decoded pixels. The verified bytes are the bounded bytes returned, so a file
cannot change between checking and rendering. A single-file action stream is
yielded in 256 KB chunks and never assembled in Python or JavaScript.

The first viewer accepts only PNG and JPEG. GIF and WebP need animation/frame
bounds; SVG needs an active-content decision; TIFF and icons need their own
format behaviour. All can still be selected for Download even while they
declare no viewer.

Known deviations:

- **Tickets may be replayed until they expire.** Every redemption re-checks
  current access, the action and its targets, but the signed token is not
  consumed.
- **Download streams have no byte-range contract.** Images do not require one;
  audio and video will.
- **Archive staging has no per-user or process-wide quota.** Each result has
  hard entry and source-byte bounds, but concurrent staging is not yet pooled.
- **Preview returns the bounded original image, not a thumbnail.** A later
  source-owned thumbnail can reduce transfer without changing the
  representation.
- **The JSON and JSONL bounded viewers remain API-only.** Image makes the
  content boundary visible again, but a large-document fallback still needs a
  screen that does not imply a partial document is editable.

## D52. Bytes a player seeks in are a ranged stream, and a PDF is drawn by the application

D49's preview returns verified bytes whole, which is right for an image and
wrong for a recording: a player asks for the end of an MP4 first, because that
is where its index may be, and a browser that gets no answer to `Range` will
not seek and may not play.

`SupportsContentStream` is the capability for that: `open_content_stream`
answers with the verified media type, the filename, the exact size and a reader
over an inclusive byte range. It is separate from `SupportsContentPreview`, and
a source may have either. The HTTP belongs to the route — one `Range` parsed,
`206` with `Content-Range`, `200` for no range or a multi-range request, `416`
with `bytes */size` for a range outside the file, and `Accept-Ranges: bytes`
always. Nothing about ranges reaches the adapter and nothing about files
reaches the route. Authority is D49's ticket, because a media element cannot
send a header, and the ticket now names the representation it was minted for,
so one for a sound file cannot be redeemed for a video.

The media type is what the container proves, never what the suffix suggests.
Verification is a bounded header read with no third-party decoder: an ID3 tag
or frame sync for MP3; `RIFF`/`WAVE` with the `fmt ` and `data` chunks for WAV,
which give channels, sample rate and an exact duration; `fLaC` with STREAMINFO,
which gives an exact duration too; `OggS` for Ogg; `ftyp` for ISO base media,
whose top-level boxes are walked by their sizes until `moov`, where `mvhd`
states the duration and `tkhd` the picture size; the EBML header read to its
`DocType` for Matroska; and `%PDF-` within the first kilobyte for PDF. What a
container does not state is absent rather than guessed, and whether a browser
can play the codecs inside is the browser's answer, shown when it fails.

A PDF is rendered by the application with `pdf.js` — pages to a canvas, no
annotation layer, no forms and no scripting manager wired — and not handed to
the browser's own viewer, which understands all of those. The one
thing besides pixels that reaches the DOM is the text layer, which is text
nodes positioned over the page, so selection and the browser's find work
without markup crossing. Pages render as they are scrolled to, and `pdf.js`
reads the file through the same ranged route.

Known deviations:

- **A stream has no byte ceiling.** It is ranged and chunked, so what is held
  is one chunk; a ceiling would forbid what costs nothing to serve. Concurrent
  streams are not pooled per user, as archive staging is not (D49).
- **Codecs are not verified, only containers.** A file whose container is
  sound and whose codec this browser lacks fails in the player, and the panel
  shows that failure rather than predicting it.
- **Duration is absent for Matroska and Ogg.** Both keep it where a demuxer
  reads, not in a header this slice parses.
- **No posters, waveforms, captions or chapters**, and no transcoding: each is
  a decode or a second contract between two nodes.
- **AVI has no viewer.** No browser plays it; it stays downloadable, like every
  other opaque file.
- **A PDF shows no annotations, links or forms.** They are the active part of
  the format, and drawing them is a decision of its own.

## D51. A file that states its own schema is a dataset, and a workbook is a container of them

Parquet and XLSX are not text with a table read out of it. Parquet declares its
columns, their types and its exact row count; a workbook declares nothing at
all as a whole, because it holds several sheets and one of them has to be
chosen before rows exist.

The choice is made in the catalog rather than in the request. An `.xlsx` or
`.xlsm` file has children: listing it opens the workbook once and answers with
one node per worksheet, in workbook order, each declaring the `table`
representation. `FetchRequest` keeps its single opaque `node_id`, and no
generic contract learns that one file can hold several tables — which is what
the old `sheet_title` parameter and its `sheets_names` reply did to every
caller.

`dataset` is the node kind for a tabular member of a container file. It is
deliberately not a `file`: it has no bytes of its own, and rename, delete and
download are ruled out by the kind their `applies_to` already names, without a
second rule. Its id is the workbook's id plus the sheet's one-based position
among the worksheets — a position, because a sheet title is written by a person
and need not survive the containment rule of D8, which judges every segment of
a node id. A node id is split at most once, and only when the whole of it names
nothing on disk, so a directory named `book.xlsx` holding a file named `1`
keeps its ordinary meaning.

A Parquet file is one dataset in one file, so it stays a `file` node that
declares `table`.

A CSV or TSV still states no source types, but its header is addressable and
its on-disk representation is safely rewritable within the upload-size bound.
It therefore declares editable, insertable and deletable rows with versioned
row handles. Each rewrite stages a complete replacement beside the file and
publishes it atomically; a handle names the row position and the file version,
so an external edit makes a stale write conflict instead of overwriting it.
Its relation model offers only the structural operations the format can mean:
add, rename and drop a text column. Defaults, nullability rules, type changes,
indexes and constraints remain unsupported rather than simulated.

Both answer `relation-model` with their declared columns, and what only their
format knows travels typed in `RelationModel.dataset`: a discriminated union
whose Parquet member states rows, row groups, compression codecs, writer and
format version, and whose worksheet member states the sheet's title, position,
sibling count, hidden state and declared used range. Which node can be
described is now said by the source in `CatalogNode.describable` instead of
being decided by the client from the node's kind. Four fields of the relation
model are relational vocabulary a file does not have — `schema_name`, `owner`,
`persistence` and `Column.storage` — and they are absent rather than filled
with something plausible; `RelationKind` gains `dataset`.

Nothing reads a whole file to answer a bounded question. A Parquet page is read
from the row groups it falls in, located through the footer, so groups before
the offset are never decompressed. A worksheet streams through the read-only
iterator and stops one row past the page. Because XLSX is a zip, the central
directory is read before anything else and a workbook declaring more
uncompressed bytes than the ceiling is refused before a byte is inflated:
64 MB encoded, 512 MB declared, 10,000 entries, and 1024 columns for either
format.

Values cross the boundary through the same `encode_cell` PostgreSQL rows use,
which moved to `adapters/cells.py`: the canonical text of a boolean, a
timestamp or a byte string is not a property of one driver. Parquet columns
keep their declared types; worksheet columns are text for the reason a CSV's
are — Excel types cells, not columns, so a type read off one page would change
with the page.

Known deviations:

- **A formula cell shows the value the spreadsheet last saved.** The workbook
  is opened with `data_only=True`; a file written by a program that never
  evaluated its formulas has empty cells there, and no formula engine is run to
  fill them.
- **Paging deep into a sheet walks the rows before it.** XLSX has no row index,
  so the tenth page costs ten pages of iteration.
- **`.xls` is not read.** The legacy binary format is a different container and
  needs a different library; it stays opaque and downloadable.
- **A sheet's node id follows its position, not its title.** Reordering the
  sheets of an open workbook changes what a reopened tab shows.
- **Merged ranges, formatting and formulas are not carried.** The grid shows
  rows; a spreadsheet viewer is a different screen.
- **A directory of Parquet part files is a directory.** One dataset over many
  files needs a decision about schema unification that this slice does not
  take.
- **The page reads every column.** Parquet can prune columns, but the grid's
  visible-column choice does not yet reach the reader.

## D53. An archive is a container of entries, and an entry name is judged by the rule every path is judged by

A `.zip` is a directory that happens to be one file, so it is a container in
the sense D51 gave the word: it has children, walking into it lists them, and
each entry is a node whose id is the archive's id plus the entry's path.

**Containment.** An entry name is written by whoever built the archive, and
zip-slip is an entry called `../../etc/passwd`. It goes through the rule in
`FileSession` that every other path goes through — a relative path whose every
segment is a plain name by the rules of both platforms — because a name typed
into a form, a filename inside a multipart upload and an entry name are the
same kind of string and the whole value of that rule is that there is one of
it. An archive holding a name that fails it is refused whole, with the name in
the message: listing the rest would be a second rule, "mostly contained", and
a reader could not tell that what they see is not what the file holds. A node
id may therefore carry the entry path, and resolution splits an id at the
longest prefix naming a container file on disk, so a directory called
`backup.zip` keeps its ordinary meaning.

**Limits.** Listing reads the central directory, which is metadata, so nothing
is inflated to build the tree and the only bound listing needs is the entry
count — 10,000, the number D49 refuses to archive past. Reading one entry
expands it into a temporary file bounded at 32 MB, and the viewer that asked
reads that file under its own ceiling. Both ends are checked: the declared size
before anything is read, and the bytes as they are written. The second bound is
this module's own — `zipfile` stops at the declared size itself, and an entry
holding more than it admits to fails its checksum there, which is reported as a
damaged entry — but a ceiling should rest on something this module can see. Expanding
rather than streaming is deliberate — every reader here reads a path, and one
bounded temporary file lets text, Markdown, JSON, JSONL, the image viewer and
the table projection all work inside an archive with no second implementation.
It costs one write per open, and paging a CSV inside an archive expands it once
per page.

**Symbolic links.** A zip entry can say it is a link whose content is a path.
It is listed, because it is in the archive, and it declares no viewer and
cannot be read: a source that will not follow a link out of its root on disk
does not follow one written inside a file either. An encrypted entry is listed
the same way and refused for the same shape of reason.

`entry` joins `dataset` as a kind of member, with `has_children` telling a
directory inside the archive from a file inside it. Rename, delete, new folder
and upload name `file` and `directory`, so an entry is out of all four without
a rule of its own; download names `entry` too and streams one entry's
decompressed bytes.

Known deviations:

- **Only ZIP.** A tar has no index, so listing means reading it end to end and
  every entry read means reading it again — a different contract.
- **Parquet, workbooks, media and PDF have no viewer inside an archive.** The
  first two seek around their own bytes and the others are streamed by range
  (D52); expansion answers neither. They are listed with their size and no
  viewer, as any file with no viewer is.
- **A nested archive is not walked into.** It is an entry with no viewer; a
  reader inside a reader is not this slice.
- **Nothing is written into an archive**, and nothing is extracted out of one
  into the personal directory: unpacking is an action with its own containment
  story and belongs beside upload. An entry still opens in the editor, as an
  unwritable document carrying the reason — the same channel a file too large
  to edit and a read-only connection already use (D48) — because refusing it
  would take the reading away with the writing.
- **A directory inside an archive cannot be downloaded.** Building a zip out of
  a zip is a different result, and the action refuses rather than guessing.
- **An archive claims children by its name.** Listing must not open every file,
  so bytes that are not an archive under a `.zip` name are found when the node
  is walked into, as D47 already says of every misleading suffix.

## D54. A relation the server owns is described but never changed

`pg_catalog` and `information_schema` are listed like any other schema, and
their relations are read like any other relation. What they are not is
writable, and until this decision they were: `pg_tablespace`, `pg_extension`
and every other catalog stored as a real table has `relkind = 'r'`, so the only
question fetch asked — "is this a table?" — answered yes, and the grid offered
to edit cells, insert rows and delete them.

That is not theoretical. This tool connects as an administrator more often than
not, and PostgreSQL lets a superuser write a system catalog:

    BEGIN;
    UPDATE pg_catalog.pg_tablespace SET spcname = 'x' WHERE spcname = 'pg_default';
    -- UPDATE 1

DDL is refused by the server — `ALTER TABLE pg_catalog.pg_tablespace ADD COLUMN`
and `CREATE INDEX` on one both answer "permission denied: it is a system
catalog" — so the structure commands were never a corruption path. They were
still wrong in a smaller way: the command was offered, and the answer came back
as a driver message.

**The rule is the one that already existed.** Creating a table in `pg_catalog`
has been refused since D45, with the words `"pg_catalog" belongs to the server`.
Rows and structure now give the same answer, from the same predicate, which is
why `is_system_schema` is public in `postgres/catalog.py` and imported by fetch
and by the relation model rather than restated in each.

The refusal is the source's, not the route's, and it is a capability rather than
an error: `update_supported`, `insert_supported`, `delete_supported`,
`column_changes_supported`, `index_changes_supported` and
`constraint_changes_supported` all become false with a reason, so the screen
stops offering the command instead of showing what happened after it was tried.
Because per-column `editable` and `insertable` are derived from those flags,
nothing else had to learn the rule.

Consequences:

- **Reading is untouched.** Paging, sorting, filtering, charts and export over
  `pg_stat_activity` or `pg_settings` work exactly as before, which is what
  makes most of the old application's PostgreSQL "system objects" screens
  unnecessary rather than unported.
- **The predicate is the schema's name, not a privilege check.** `pg_%` and
  `information_schema`. A catalog is identified by where it lives, which is
  stable, rather than by what this connection happens to be allowed to do,
  which is not.

Known deviations:

- **A user's own table inside a schema named `pg_something` is refused too.**
  The name is reserved by PostgreSQL for exactly this reason, and a rule that
  asked the server instead would be a query per relation.
- **`pg_temp` and `pg_toast` are not listed at all**, so the rule never reaches
  them.

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
  being listed permits nothing. A flag rather than a shorter API answer keeps
  the source vocabulary and the answer about one selection distinct; the
  catalog keeps the permitted vocabulary visible and disables what is not
  applicable to the current place or selection. Applicability depends on state
  as well as kind: the root of a connector is an ordinary directory that may
  not be renamed or removed.
- **An action says what it changes.** `acts_on` is `"node"` for what is done to
  the ticked rows and `"children"` for what is made inside the current level.
  Without it the screen would read the difference off the names of actions. It is
  also what keeps a folder from being deleted by being stood in.
- **Whether one filled form may be applied to many is the action's own
  business.** `Action.bulk`; `Delete` says yes, `Rename` cannot. The flag never
  leaves the server: when more than one node is asked about, the server leaves
  out what did not declare it.
- **Whether it may carry several files is the action's own business too.**
  `Action.many_files`; `Upload` says yes, loading a table from a CSV cannot,
  because a second file there would be a second table. This one does leave the
  server, as `takes_many_files` in the listing: the transport is one file per
  request either way, so what the declaration decides is whether the client
  offers to choose a set — and a client left to guess would offer it for every
  action that takes a file at all.
- **The transport is a protocol, not a flag.** An action that carries a file
  satisfies `TakesFile`; `takes_file` in the API answer is an `isinstance` check.
  There are two routes because HTTP has two shapes of body, and each refuses an
  action of the other transport with 415.
- **What to re-read is in the answer.** `ActionResult.reload_node_id` names the
  branch that changed, rather than the client inferring it from the action name.
- **Personal-file defaults are resolved by the source.** A folder submitted
  unchanged becomes `new folder`, then `new folder (1)` and so on. Deleting a
  directory removes its contents after the action's one destructive
  confirmation; there is no second recursive parameter. Upload first refuses a
  taken name, then accepts an explicit retry to replace it or to publish the
  first free `name (n).ext` without overwriting a file that appeared meanwhile.

Known deviations:

- **Nothing moves or copies.** An action works inside one node of one connector;
  moving a file to another folder means downloading and uploading it again.
- **Folder creation and rename can still race another writer.** Upload retries
  through no-overwrite publication, but the other two use ordinary filesystem
  operations after choosing their target. The directory belongs to one user.
- **An upload gives no progress and cannot be resumed.** A large file is one
  request that either finishes or leaves nothing behind.
- **Nothing records what was done.** No audit trail, no history of deletions.
- **A set is acted on one call at a time.** Deleting five files is five requests
  run in order, and uploading five is five in the same way; a refusal in the
  middle is collected and reported rather than stopping the rest. Nothing is
  transactional: four of five may be gone, or four of five may have arrived.
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
