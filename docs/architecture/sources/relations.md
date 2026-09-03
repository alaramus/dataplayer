# Describing, reading and changing rows

For anything that reads a relation or changes the rows in it. Changing its
structure is [ddl.md](ddl.md).

## D22. A source describes a relation in full

A type name cannot do three jobs safely, and a constraint copied onto every
column splits a composite foreign key into independent one-column links, which
is what the old application did.

- `SupportsRelationModel.relation_model(node_id)` returns one `RelationModel`:
  columns, constraints, indexes and partitioning together with the relation's
  identity and metadata. `GET /connectors/{id}/relation-model` exposes it.
- It is separate from `SupportsCatalog`: an object store can have a catalog
  without having relations, so the file source answers 501 rather than inventing
  a model.
- `ColumnType.sql` is PostgreSQL's `format_type(atttypid, atttypmod)`, which can
  be written back into DDL; `category` tells the grid how values behave; the
  remaining fields carry parsed facts — array element, dimensions, enum labels,
  length, precision, scale. `pg_type.typname` is deliberately absent: it says
  `_int4` for `integer[]`, and another common spelling drops the `(50)` from
  `varchar(50)`. The integration test builds a new table from every returned
  `type.sql` and describes it again, so both failures are exercised by a real
  DDL round trip.
- A constraint is one top-level discriminated object with its columns in key
  order. Foreign keys carry the target's adapter-produced `node_id`, so
  [D21](contract.md) still holds. The screen derives per-column badges from
  these relation-level objects.
- PostgreSQL reads four sets in sequence — relations, columns, constraints,
  indexes. Each query is written over a whole schema with the relation name as
  an optional value predicate, so schema-wide loading is a caller change rather
  than a query rewrite, and every client value stays in a placeholder.
- The catalog does not descend into a relation: tables and views are leaves, and
  the relation model is the single description of their columns.

Known deviations:

- **Only one relation is exposed at a time.** The private PostgreSQL query path
  already accepts no relation predicate, but no public schema-wide response or
  cache uses that form yet.

Spec: [The relation model](../../superpowers/specs/2026-08-24-relation-model-design.md)

## D23. A cell crosses the boundary as lossless text

Capabilities belong to a column rather than to a whole result: a source may
expose a complex value while allowing only null checks on it.

- `FetchColumn` is the complete contract for one displayed column: `name`, the
  same structured `ColumnType` D22 uses, `sortable`, and an ordered list of
  `filter_operators`. The file source describes its string and number columns
  but declares no sorting or filtering; the client never names either adapter.
- `FetchResult.rows` is `list[list[str | None]]`. `bigint` and `numeric` never
  pass through a JavaScript number, date and time keep ISO 8601, boolean is
  `true` or `false`, binary is uppercase hex with a `0x` prefix, and JSON is
  compacted without parsing numeric tokens as floats. `None` stays distinct from
  an empty string.
- PostgreSQL casts server-text types in the `SELECT`; typed columns stay typed
  for filtering and sorting, and the frontend uses the full original string for
  the viewer and clipboard.
- Filters are a discriminated union rather than a partly filled object. Null
  checks have no value, `in` requires a non-empty list, scalar operators require
  one text value. Before building the statement PostgreSQL verifies the column,
  verifies that the column declares the operator, converts the value to the
  driver's native type and rejects invalid input. Fixed operator fragments come
  from a closed table and every condition is joined with `AND`.
- The offered operations are deliberately conservative: number, string and
  supported date/time compare; string also contains and starts with; boolean,
  UUID and enum have equality and `in`; every type has null checks. Extending
  that set is an adapter change arriving in `FetchColumn`, not new frontend
  knowledge.
- `encode_cell` lives in `adapters/cells.py`: the canonical text of a boolean, a
  timestamp or a byte string is not a property of one driver.

Known deviations:

- **Not every canonical text has a specialised editor.** PostgreSQL remains the
  final parser for complex values; the first UI gives them a technical text
  field rather than duplicating every server type in the browser.
- **Filtering has no `OR` or grouping.** The flat request means `AND`; adding
  parentheses needs a recursive expression contract and a matching editor.

Spec: [The data exploration grid](../../superpowers/specs/2026-08-27-data-grid-design.md)

## D42. Row identity and page order are stated

Two defects had one cause: neither identity nor order was stated, so both were
whatever the plan produced. Editing a cell sent its row to the end of the page,
and `LIMIT`/`OFFSET` could not promise that page two omits page one.

- Every fetch ends with a deterministic tiebreaker appended after the user's own
  sort: the primary key ascending where there is one, `tableoid, ctid` where
  there is not.
- A row handle no longer requires a primary key. `ctid + xmin` says "this exact
  version of this row" at least as precisely as `key + xmin`: anything that
  moves the row changes both, the handle then matches nothing, and the answer is
  the conflict it already was. On a partitioned parent the physical identity is
  `tableoid` and `ctid` together.
- The key is still preferred where the relation has one, because a ctid handle
  is fragile in a way the reader cannot see: `VACUUM FULL`, `CLUSTER` or a
  repack invalidate every open page's handles at once.

Known deviations:

- **A keyless relation still cannot hold its place.** Its rows are ordered
  physically, so editing one moves it.
- **Paging stays `LIMIT`/`OFFSET`.** A stable order makes it correct, not fast;
  keyset paging is a separate contract.
- **`ctid` never leaves the handle.** It is not offered as a column to filter or
  sort by.

Spec: [What identifies a row, and what order rows arrive in](../../superpowers/specs/2026-08-30-row-identity-and-order-design.md)

## D25. A source issues a versioned row handle

The old application preferred a special row-id column, then fell back to every
non-null cell — a predicate that could match several duplicate rows, ignored
nulls, guessed value types in the browser and had no version check.

- An editable fetched row carries an opaque handle beside its canonical values.
  The client returns that handle unchanged with one column name and one new
  canonical value; it never constructs a predicate, takes a node id apart or
  decides what identifies a row.
- The adapter validates the column against current metadata and builds every
  identifier with the driver's composition API.
- PostgreSQL's handle holds the fetched key values and `xmin`; an update matches
  both and returns the complete canonical row with a new handle. No match is a
  409, so a second tab cannot silently overwrite a row changed or deleted since
  it was read.
- Generated columns are explicitly non-editable; views, files and keyless tables
  state in the fetch result why their rows are read-only.
- An update is one cell and one transaction, but the full returned row matters:
  triggers and generated columns may change other cells, and a changed filter or
  sort value may move the row out of the page. The grid invalidates and rereads
  the server page rather than pretending a local patch preserves server order.

Known deviations:

- **`xmin` is PostgreSQL-specific and finite.** It stays behind the opaque
  handle and is sufficient for the interval between reading and saving; an
  adapter with an explicit revision column can issue a different handle.

Spec: [Editing data](../../superpowers/specs/2026-08-27-data-editing-design.md)

## D26. Insert names columns, and bulk delete is atomic

A selection is one destructive user action, so a half-applied delete would leave
the grid unable to say what still needs consent.

- Insert and delete are independent capabilities beside update. Relation-level
  support and its reason arrive in `FetchResult`. PostgreSQL inserts into
  tables including keyless ones, and deletes only from tables with a primary
  key. Views and files keep the commands visible but disabled with the source's
  explanation.
- An insert request is a list of `{column, value}` objects, not a dictionary and
  not a complete row. Absence means "let the source use its default", an object
  whose value is null means SQL `NULL`, and text remains canonical boundary text.
- Metadata marks columns `insertable`, `insert_required` and `has_default`, so
  the form omits identity, generated and defaulted fields without copying
  PostgreSQL rules. The adapter rereads metadata, rejects unknown or
  non-insertable identifiers, and uses `DEFAULT VALUES` when the list is empty.
  `RETURNING` produces the same canonical row and handle as fetch.
- Delete accepts one to 500 opaque handles and is one statement. PostgreSQL
  counts rows matching every key plus fetched `xmin` and runs the `DELETE` only
  when that count equals the requested count, so one stale row produces 409 and
  removes nothing. Duplicate handles are rejected, so the equality cannot be
  satisfied accidentally.

Known deviations:

- **Insert is one row at a time.** Multi-row insert needs row-local validation
  and a deliberate choice between atomic and partial success.
- **Delete is limited to loaded rows.** Selection stops at the current page;
  deleting a server-side filter needs a separate previewable command.

Spec: [Inserting and deleting rows](../../superpowers/specs/2026-08-27-row-insert-delete-design.md)

## D41. A pasted block is one atomic edit

The mirror of the DDL commands in [ddl.md](ddl.md): there the source counts what
is already in it that contradicts the request, here the rows are fine and the
arriving values may not be readable.

- Pasting travels as rows, not as cells: a handle carries the key and the `xmin`
  it was fetched with, and the changed cells hang off it. Every row must still
  hold that version or nothing is written.
- Bounded at 500 rows, 100 cells in a row and 2000 cells altogether.
- Before anything is written, one query checks every value against its column's
  type with `pg_input_is_valid`, and failing cells come back named by request row
  and column rather than counted — the reader is looking at those values and
  there are at most two thousand. The query carries the area's SQLSTATE mapping,
  so a type whose input function still raises degrades to one honest sentence
  instead of a 502.
- All-or-nothing is a transaction. `PostgresSession` gained one that runs several
  statements on one connection and rolls back unless all of them did what they
  said; each row is one `UPDATE … WHERE key = … AND xmin = …`.
- The block lands from the top-left of the selection and is refused before it is
  sent if it would run past the loaded rows or the visible columns, or across a
  column the source calls uneditable. Nothing is truncated and no row invented.
- The grid's TSV is lossless: an unquoted empty field means null and a quoted one
  means the empty string, in both directions.
- A copied line also fills the row being inserted, positionally and exactly so:
  the grid and the insert row are built from the same ordered list of visible
  columns. Values landing on a column the source fills itself are left out and
  named.

Known deviations:

- **No fill, no new rows in a block paste, no file.** A block taller than what is
  loaded is refused rather than appended; inserting is D26 and importing a file
  is D43.
- **The single-cell route stays separate.** It shares the type check, so its
  refusal names the type, but merging the two paths is a tidy-up.

Spec: [Pasting a block of cells](../../superpowers/specs/2026-08-30-cell-paste-design.md)

## D36. The source issues a reference's target

The client's whole influence on the resulting query is which reference of which
row it pointed at; the pairing of columns is read from the source at the moment
of asking.

- `FetchResult.references` carries, per foreign key, the source's own name for
  it, its columns in key order, and a title for the target. One object per key,
  not a mark on each column, for the reason D22 gives.
- `SupportsReferences.follow_reference` takes back the name of one reference and
  the values one row holds for its columns.
- The answer is a discriminated union. `ReferencedRows` carries the target as a
  whole `CatalogNode` — the model `path_to` answers with ([D21](contract.md)) —
  together with equality filters in the closed vocabulary a typed filter uses.
  `NoReferencedRows` carries a reason: a key with a missing value names no row,
  and a key on a type this source cannot compare cannot be looked up. Both are
  answers about the data, which is [D2d](contract.md).
- A row handle was rejected as the way to name the row: handles exist only where
  the source can version a row, and a keyless table can still hold a foreign key.
  The values travel instead, as canonical text.
- PostgreSQL reads its keys from `pg_constraint` on every page rather than
  remembering them: `confrelid` is an oid, so a target renamed since the page was
  read answers with the name it has now, and a constraint dropped since is
  refused by name rather than turned into a predicate over a vanished key.
- Following a key is a read: the route asks for `read` access and no more, and
  the predicate goes through the target's own fetch validation, not a second path.

Known deviations:

- **Only the forward direction exists.** Going from a row to the rows elsewhere
  that point at it needs a search across a whole schema for arriving keys, and a
  way to say which of several found relations is meant.
- **A page costs one more catalog query.** The keys are read beside the columns
  on every fetch. The read cache ([D31](connecting.md)) absorbs repeated paging,
  and nothing measures the difference yet.

Spec: [Navigating by a foreign key](../../superpowers/specs/2026-08-30-reference-navigation-design.md)

## D43. Rows move between sources through the platform

The first command naming two connectors. It lives in the `connectors` module
rather than in an adapter, because an adapter knows itself and nothing else, and
asking one to read another would be the first crack in that.

- Two connectors mean two permissions, checked separately against the grants of
  D33 — writing rows into the target, reading the node in the source. Neither
  implies the other.
- It is not an import of a file: the file source is one readable source among
  several and the relation one writable target among several.
- The read has a ceiling of 5000 rows and pages the source at its own limit to
  reach it. More is not refused — that would make the command useless — but the
  answer says the rows were cut off.
- Columns are paired explicitly, source column to target column, and both sides
  are validated against what each says it has before anything is read. Matching
  by position or by equal names would turn a wrong import into one that looks
  right.
- The target checks every value against its column's type before writing, the
  same pass D41 makes, and answers with the cells that cannot be read: row,
  column and the value itself, cut short. Then one transaction; a partial import
  is impossible, which is why there is no downloadable error report.
- `preview` reads the first rows through the same mapping and hands them back.
  It answers "have I paired these columns correctly" and deliberately does not
  validate against the target.
- The same bounded read can prepare a relation that does not exist yet: the
  route asks the target container's `SupportsCreateRelation` for its type
  vocabulary, then passes an explicit mapping to `create_relation`. Creation
  refuses a source beyond the ceiling, because a new table made from only the
  first part of one would carry a false identity.

Known deviations:

- **No transformation.** A value crosses as the text the source gave or it does
  not cross. Trimming, date formats and decimal separators need a vocabulary.
- **No upsert and no key matching.** Existing targets receive inserts; a new
  target receives plain columns and rows, with constraints left to
  [D40](ddl.md).

Spec: [Bringing rows from one source into another](../../superpowers/specs/2026-08-30-row-import-design.md)

## D45. A file becomes a table in one transaction

D43 moves rows into a relation that already exists; this is the half a reader
rarely has. It is a catalog action ([D9](actions.md)) rather than a route of its
own, so nothing on the screen learned anything about PostgreSQL.

- `SupportsCreateRelation` has two methods and is one capability because either
  alone is useless: `new_relation_options` says what a container will accept a
  new relation with — `supported`, a `reason` when not, and D27's
  `ColumnTypeOption` list — and `create_relation` makes it. Asking a *container*
  is what lets a schema the server owns say why it admits nothing.
- The rows travel with the request. With a separate create and insert, a value
  the column could not take would leave behind an empty relation nobody asked
  for, and this platform has no way to drop one. PostgreSQL rolls DDL back like
  anything else, so either the table arrives with its rows or nothing is made.
  `Transaction` gained `schema_change` for this: `change` fetches, and a
  statement returning no rows would fail inside the cursor.
- Every value is checked first by the same `pg_input_is_valid` pass D41 and D43
  make, and rejected cells come back in `ValuesRejected`.
- Every column is text. A delimited file states no types, and one read off its
  rows would depend on how many were looked at. A column takes another type
  afterwards through [D38](ddl.md), which counts the rows in the way first.
- `adapters/delimited` holds the delimiter rule, the naming of a header written
  by hand and the fitting of a short row. The file source pages a file through
  it and this action takes a whole one; neither adapter imports the other.
- Both ceilings refuse rather than truncate: at most 5000 rows and 16 MB. D43
  truncates because it samples a live source; here the reader handed over a whole
  file, and a part of one arriving would go unnoticed.
- The schema being looked at is the initial destination, not a hidden constraint;
  the workflow can request a new one, and PostgreSQL may refuse for privilege.
  The table name starts as the filename without its extension, and columns may
  be omitted or renamed before the file is sent.
- **A source that keeps files takes one too, and it is a delimited file.** A
  folder has no CREATE TABLE and needs none: rows under named columns are a
  CSV. The same capability, the same route and the same form — only the
  container is a folder, the type vocabulary has the single entry a delimited
  file can honestly offer, and the extension is added when the name carries
  none, because `orders` alone opens as a document.
- **Atomic by the means the source has.** The file is built beside its
  destination and linked into place, so a failure leaves nothing half-written
  and a name already taken is refused by the link rather than by a check that
  something could slip past. It is what the transaction is for the database
  half, stated in the only terms a filesystem has.
- **The form is worded by the destination, never by the type of the source.**
  A schema takes a table and a folder takes a file, and the catalog already
  says which of the two a node is; the heading, the labels and the button read
  off that. Which connections are offered at all is read off the capability's
  code, so a source that would answer 501 is not in the list. Where a source
  publishes one column type, the column's type control is not drawn: a list of
  one is a control that does nothing.

Known deviations:

- **No inferred structure beyond names.** No inferred type, NOT NULL, default,
  key or index; each has a command of its own against an existing relation.
- **A taken name is refused, never replaced.** Removing a relation is
  [D46](actions.md).
- **Only the top level of a destination is offered.** Its groupings, or its
  folders and itself — a folder two levels down cannot be chosen yet, and
  walking a destination catalog inside this form is a later slice.
- **A file destination is written at 0600**, as everything this source creates
  through a temporary file is.
- **The file is held whole in memory** while it is parsed, which is what the
  16 MB ceiling is for.

Spec: [Loading a CSV as a new table](../../superpowers/specs/2026-08-30-relation-create-design.md)

## D44. An export is a source-owned row stream

The current-page download of D28 repeats one bounded `FetchRequest`; an export of
every matching row does not. Paging `SupportsFetch` until it stops would make a
changing source several snapshots and put offset cost in the platform rather
than in the driver.

- `SupportsExport` takes the node, committed filters, ordered sort and visible
  columns, and yields `ExportBatch` objects of at most 500 rows. There is no
  limit or offset in that request.
- A source either has a real streaming read or does not implement the capability.
- PostgreSQL keeps one validated query open through a server-side cursor; each
  batch crosses as D23's lossless text cells, the sort keeps its source-owned
  tiebreaker, and only requested visible columns are selected.
- The file source deliberately does not opt in: [D49](actions.md)'s node
  download and exporting a tabular interpretation are different operations.
- CSV stays outside the adapter. The connector layer encodes one batch at a time
  with D28's null and quoting rules and writes a `.part` under the caller's
  personal `downloads/<connector-id>` directory; a clean end renames it
  atomically, failure or cancellation removes it. The request returns a row
  count, filename and one-minute signed ticket for that exact stored path, so
  neither side of the HTTP boundary assembles a whole Blob.

Known deviations:

- **It is a long request, not a job.** No durable progress, resume or background
  completion; an upstream timeout or full disk refuses the export rather than
  returning a truncated success.
- **A ticket is reusable until it expires.** It is a bearer capability for one
  already-created file. One-time redemption would require shared state across
  backend processes.

Spec: [Exporting every matching row](../../superpowers/specs/2026-08-30-streaming-export-design.md)

## D70. A relation may declare commands over its own rows

An action is about a catalog node (D9), and a process is not a node. The
Processes report (D55) lists what is connected and what each backend is doing,
and until now there was nothing to do about it: the grid's delete button
belongs to a relation that can be written to, and a report is a subquery with
no row to write back to (D42), while an action with a `pid` field asks somebody
to type in a number that is already on their screen.

So a relation may declare commands of its own, and the grid offers them over
the rows that are ticked.

Consequences:

- **A command names the column that names a row.** `identified_by` is one
  column — `pid` here — and the keys the client sends are the values of that
  column in the selected rows. One column, because that is what every command
  that exists needs; a compound key is a different contract and is not invented
  before somebody has one.
- **Two questions, one driver.** `SupportsRowCommands` answers what a node
  offers and runs one of them, so there is no third place a name could resolve
  differently, and what a client may do is decided by what the node offers
  rather than by the vocabulary existing. The same shape `SupportsActions` has.
- **They travel on the fetch result**, filled in by the route from the composed
  adapter, exactly as `export_supported` is: a capability belongs to the source
  rather than to the module that read the page. They are filtered by the level
  the caller holds, so a command nobody may run is never drawn.
- **The level is the command's own statement**, checked after the name has
  resolved. PostgreSQL's two need `structure`, the strongest level that can be
  given away: stopping somebody else's work is not what "may write rows" was
  granted for.
- **The keys are the source's to read.** Nothing in the route knows what a
  process id is; a key that means nothing to the source is refused by the
  source. A key that is not an integer is refused beside the others rather than
  stopping them.
- **A refusal is an answer.** `pg_cancel_backend` returning false about a pid
  that has gone is reported as a refusal with a count, not raised as a failure
  of the server. The connection carrying the request is skipped, so a request
  cannot kill the connection running it.
- **The client is told what to draw, never what it means.** The buttons carry
  the source's title and its description; an icon per command would be a table
  of names on this side, which is what declaring them on the source avoids.
- **A relation may ask to be re-read.** `refresh_seconds` on the fetch result
  is what the source thinks the relation is worth — five seconds for the
  Processes report, nothing for anything else — and the grid takes it as its
  starting interval only where nobody has chosen for that relation (D67).
- **A command may say it changes more than its page.** Installing an extension
  brings schemas, types and functions with it; cancelling a query brings
  nothing. `changes_structure` is the command's own answer, and the client
  reads it to decide whether the catalog column has to re-read as well (D66) —
  the same nudge a console gives after running DDL.
- **Extensions are installed and removed on the rows that list them.** They
  were a pair of actions whose form asked for a name, standing next to a table
  that already held every name there is: the same value typed a second time,
  and no way to install two at once. Each row is one DDL statement, so each is
  refused for its own reason and the refusals come back per key. The name in a
  ticked row selects a row of `pg_available_extensions` or `pg_extension`, and
  the identifier that reaches the statement is the one that came back.

Known deviations:

- **Only two reports of one source have any.** The vocabulary has now been
  used twice, which is the first evidence that its shape is right; the second
  source to want one is still the real test.
- **An extension is installed with a cascade and removed without one.**
  `CREATE EXTENSION … CASCADE` adds what the chosen extension is built on,
  which is what a person asking for it wants; a cascading drop would reach
  whatever anyone ever built on its types, so the server refuses instead and
  says what is in the way.
- **The rehearsal is gone with the form.** The action could ask the server
  what installing or removing would do and show the answer before doing it; a
  row command has no form to show it in, and nothing has been designed to
  replace it.
- **A command acts on a page.** Ticking is per row of what is on screen, so
  "every backend of this database" means paging through and ticking.
- **Nothing says what a command did to each row.** The count and the refusals
  come back; which of the ticked rows the count refers to does not.
- **A command acts on what is on screen, and nothing says so.** The buttons
  read the same whether the page holds every process or the first hundred.

Spec: [Commands over the rows of a relation](../../superpowers/specs/2026-09-02-row-commands-design.md)

## D72. What a page is for is the source's statement, not the grid's guess

The Processes report arrived with the whole grid toolbar over it: download
this page, chart it, share a link to it, make a table out of it, open it as a
query. All of them work, and for a while all five were withdrawn on the
grounds that a picture of what a database is doing this second is not
somebody's data.

That was one step too far. A page of a report is still a page: a list of
settings is downloaded to be compared with another server's, a link to what is
running is exactly what one sends a colleague, and a table of sizes is worth a
chart. What is genuinely not there is a copy — a table made out of a report is
a moment nobody can refresh — so that is the one command a report withdraws.

`FetchResult.page_commands` names which of `download`, `chart`, `share`,
`create_relation` and `query` a relation offers. A source that says nothing
offers all five: a page is ordinarily somebody's own data, and only the source
knows when it is not.

Consequences:

- **One list rather than five flags.** `update_supported` and its family
  answer five different questions about writing; this answers one — what is
  this page for — and a source withdrawing one of these usually withdraws
  several. PostgreSQL's reports withdraw one of the five in a line.
- **The client learns no names of its own.** The vocabulary is the server's,
  the type is derived from the generated client rather than written out again,
  and the grid asks whether a command is offered without learning what a
  report is.
- **What is left over a report is what looking at it needs**, plus what taking
  it away with you needs: filtering, sorting, columns, copying, paging,
  auto-refresh, download, share, chart and opening it as a query. Writing was
  already withdrawn by
  [D54](#d54-a-server-owned-relation-is-read-never-changed), so the rest of the
  toolbar is the controls for finding a row and the commands for acting on it
  ([D70](#d70-a-relation-may-declare-commands-over-its-own-rows)).

Known deviations:

- **A withdrawal has no reason attached.** `update_reason` explains a disabled
  button; an absent one asks no question, so nothing is said.
- **It is per class of relation, not per relation.** Every report withdraws the
  same one; there is no way to say that one particular table should not be
  charted.

Spec: [What a page is for, said by the source](../../superpowers/specs/2026-09-02-page-commands-design.md)

## D54. A server-owned relation is read, never changed

Every catalog stored as a real table has `relkind = 'r'`, so the only question
fetch asked — "is this a table?" — answered yes, and the grid offered to edit
cells, insert rows and delete them. A superuser can in fact write
`pg_catalog.pg_tablespace`, and this tool connects as an administrator more often
than not.

- The predicate already existed: creating a table in `pg_catalog` has been
  refused since D45 with the words `"pg_catalog" belongs to the server`.
  `is_system_schema` is public in `postgres/catalog.py` and imported by fetch and
  by the relation model rather than restated in each.
- The refusal is the source's, not the route's, and it is a capability rather
  than an error: `update_supported`, `insert_supported`, `delete_supported`,
  `column_changes_supported`, `index_changes_supported` and
  `constraint_changes_supported` all become false with a reason. Per-column
  `editable` and `insertable` derive from those, so nothing else had to learn the
  rule.
- Reading is untouched: paging, sorting, filtering, charts and export over
  `pg_stat_activity` or `pg_settings` work exactly as before.
- The predicate is the schema's name — `pg_%` and `information_schema` — not a
  privilege check. Where a catalog lives is stable; what this connection is
  allowed to do is not.

Known deviations:

- **A user's own table inside a schema named `pg_something` is refused too.** The
  name is reserved by PostgreSQL for exactly this reason, and a rule that asked
  the server instead would be a query per relation.
- **`pg_temp` and `pg_toast` are not listed at all**, so the rule never reaches
  them.

Spec: [What the old PostgreSQL adapter does beyond the table rounds](../../superpowers/specs/2026-08-31-postgres-system-operations-design.md)
