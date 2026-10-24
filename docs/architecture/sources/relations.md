# Describing, reading and changing rows

For anything that reads a relation or changes the rows in it. Changing its
structure is [ddl.md](ddl.md); moving rows in or out of one is
[transfer.md](transfer.md).

Decisions here: D22, D23, D42, D25, D26, D41, D36, D70, D72, D54, D109, D110, D246.

## D22. A source describes a relation in full

A type name cannot do three jobs safely, and a constraint copied onto every
column splits a composite foreign key into independent one-column links.

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
  indexes. Each query can filter one name or a selected array of names within a
  schema; every client value stays in a placeholder.
- The catalog does not descend into a relation: tables and views are leaves, and
  the relation model is the single description of their columns.

Known deviations:

- **There is no public schema-wide response.** The batch read is restricted to
  the relations the caller selected (D246).

Spec: [The relation model](../../decisions/2026-08-24-relation-model-design.md)

## D246. Selected relation descriptions load together, and keep a short source-owned cache

The graph needs complete models, but asking for one at a time turns each one
into several catalog reads and a separate HTTP request.

- POST /connectors/{id}/relation-models accepts 1–100 unique opaque node ids
  and returns the available models plus a failure for each missing or
  unreadable node. Sources with the SupportsRelationModelBatch capability can
  read a set; other relation sources keep partial failures through at most four
  concurrent single reads.
- PostgreSQL groups selected ids by schema and reads relation, column,
  constraint, index, access-method and Timescale classification metadata inside
  one repeatable-read, read-only inspection transaction. The transaction keeps
  a five-second statement timeout local to the connection. It does not scan
  unrelated relations in the schema. A batch that runs out of that time is
  read again one relation at a time, each with its own five seconds; any other
  failure of the batch is the source failing.
- Single and batch descriptions use the relation area of DataCache. PostgreSQL and
  MySQL own a five-minute TTL; the connector's row/catalog TTL setting does not
  change it. Incomplete batch results are returned but not stored. A DataPlayer
  mutation invalidates the connector's cached descriptions. External PostgreSQL
  schema changes are read after the server entry expires on the next source
  request; explicit Reload on a graph or structure view bypasses the cache.
- Row pages remain in the separate fetch area. The graph places each returned
  model in TanStack's per-relation query cache, so a structure or record view in
  the same browser can reuse it without another request. No relation metadata
  is preloaded at connection startup.

Known deviations:

- A batch's cache key is its exact selected set. Two overlapping sets do not
  share server-side entries; the browser shares individual models between the
  graph and structure views.

Spec: [Batching relation descriptions](../../decisions/2026-10-21-relation-model-batching.md)

## D23. A cell crosses the boundary as lossless text

Capabilities belong to a column rather than to a whole result: a source may
expose a complex value while allowing only null checks on it.

- `FetchColumn` is the complete contract for one displayed column: `name`, the
  same structured `ColumnType` D22 uses, `sortable`, and an ordered list of
  `filter_operators`. The file source describes its string and number columns,
  declares no sorting and declares equality alone ([D109](#d109-the-file-source-looks-a-value-up-by-equality-and-nothing-else));
  the client never names either adapter.
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

Spec: [The data exploration grid](../../decisions/2026-08-27-data-grid-design.md)

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
- **A MySQL table without a usable key is not edited.** MySQL has no row
  address to fall back on, so such a table takes inserted rows only (D234).

Spec: [What identifies a row, and what order rows arrive in](../../decisions/2026-08-30-row-identity-and-order-design.md)

## D25. A source issues a versioned row handle

Rejected: a special row-id column with every non-null cell as the fallback — a
predicate that can match several duplicate rows, ignores nulls, guesses value
types in the browser and has no version check.

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
- **A MySQL handle's version is a digest of the row as shown**, since MySQL
  keeps no version a client can read; it is checked under `FOR UPDATE` (D234).

Spec: [Editing data](../../decisions/2026-08-27-data-editing-design.md)

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

Spec: [Inserting and deleting rows](../../decisions/2026-08-27-row-insert-delete-design.md)

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

Spec: [Pasting a block of cells](../../decisions/2026-08-30-cell-paste-design.md)

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

- **A page costs one more catalog query.** The keys are read beside the columns
  on every fetch. The read cache ([D31](connecting.md)) absorbs repeated paging,
  and nothing measures the difference yet.

The forward direction was the whole of it until [D110](#d110-a-source-says-what-points-at-a-relation-and-following-it-is-the-same-call).

Spec: [Navigating by a foreign key](../../decisions/2026-08-30-reference-navigation-design.md)

## D70. A relation may declare commands over its own rows

An action is about a catalog node (D9), and a process is not a node. The
Processes report (D55) lists what is connected and what each backend is doing,
and until now there was nothing to do about it: the grid's delete button
belongs to a relation that can be written to, and a report is a subquery with
no row to write back to (D42), while an action with a `pid` field asks somebody
to type in a number that is already on their screen.

So a relation may declare commands of its own, and the grid offers each of them
in the corner of the row it is about — the place a row's own way in already
lived ([D111](../grid.md)).

Consequences:

- **A command names the column that names a row.** `identified_by` is one
  column — `pid` here — and the key the client sends is that column's value in
  the row the button was pressed on. One column, because that is what every
  command that exists needs; a compound key is a different contract and is not
  invented before somebody has one.
- **The row is the subject, so nothing is ticked first.** The buttons stood in
  the toolbar and were dead until a row was selected, which made every use of
  them two gestures and put the command a table's width away from the row it
  was about. The pid is on screen; a button that asks for it to be ticked is a
  button asking for what it can already see.
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
- **The client is told what to draw, never what it means.** The corner of a row
  has room for a picture and none for a sentence, so the source names the
  picture as well: `icon` beside `title` and `description`, which become what
  the button says on hover. Choosing the picture on the client would be a table
  of command names on that side — the thing declaring commands on the source
  exists to avoid.
- **A command may belong on some rows only.** An extension is installed or
  removed, never both, and the row already says which; offering the other is
  offering what the server refuses. `applies_when` is one column and one value,
  compared against the cell exactly as the source's own answer spelled it, so
  the client stays ignorant of what `installed` means. A command that says
  nothing belongs on every row it can name.
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
  that already held every name there is: the same value typed a second time.
  Each row is one DDL statement, so each is refused for its own reason and the
  refusals come back per key. The name in the row selects a row of
  `pg_available_extensions` or `pg_extension`, and the identifier that reaches
  the statement is the one that came back.
- **The page is read again where a command ran.** The row the button is drawn
  from is the row that changed, and an extension that has just been installed
  must stop offering to be installed. The Processes report re-read itself
  anyway (D67); the others did not.

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
- **One row at a time.** The request carries a list of keys and the source
  answers per key, so several were once sent together from a selection. The
  corner of a row can send one, and "every idle backend" is now one press per
  row. Bringing a set back means a second gesture beside the per-row one, and
  nothing has been designed for it.

Spec: [Commands over the rows of a relation](../../decisions/2026-09-02-row-commands-design.md)

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

Spec: [What a page is for, said by the source](../../decisions/2026-09-02-page-commands-design.md)

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

Spec: [What the PostgreSQL adapter does beyond the table rounds](../../decisions/2026-08-31-postgres-system-operations-design.md)

## D109. The file source looks a value up, by equality and nothing else

Refusing to sort a file is right: an ordered page needs the whole file ordered.
Refusing to filter one was not, and it is what stopped a reference from pointing
at a CSV ([D106](declared.md)).

- Equality is the whole vocabulary. `filter_operators` on every column of every
  tabular file projection is `["eq"]`, and any other predicate is refused by the
  source rather than approximated.
- It is applied where the rows are read, on the canonical text of D23 that the
  page already carries. A filtered page is an unfiltered one with rows left out:
  no second reader, no typed reinterpretation of a CSV, no ceiling that
  truncates the answer without saying so.
- Paging counts matching rows, and `has_more` means another matching row exists.
- A row handle carries the row's real position in the file rather than its
  position on the page, because a page of matches is not a window into a
  contiguous run and an edit has to land where the row actually is.
- It costs a scan, which is what paging a file already costs: the tenth page of
  a delimited file walks the nine before it.

Known deviations:

- **No `contains` and no null tests.** Searching the text inside files is a
  different request with a different answer shape. An
  empty cell in a delimited file is the ambiguity D45 already decided once, and
  a null test would be answering it a second time for this source alone.
- **Sorting is still refused**, unchanged.

Spec: [A reference the person draws](../../decisions/2026-09-05-declared-references-design.md)

## D110. A source says what points at a relation, and following it is the same call

A relation's own keys are part of its definition and are read on every page
(D36). The keys landing on it are a search of everything else, so they are
asked for separately and by a capability of its own.

- `SupportsArrivingReferences.arriving_references` answers with the mirror of
  `FetchReference`: a name to send back, the columns **of this relation** the
  key lands on, and a title for what points here. What the key is called over
  there, and which of its columns stand for these, stay with the source.
- **The name is a handle the source issues**, not the constraint's own name.
  A forward key can use its own, because a constraint name is unique within the
  relation that carries it; among arriving keys it is not — a partitioned table
  repeats its constraint on every partition, and all of them land here. Three
  menu entries answering to one name would all open the first of them.
- **Asked once for the relation, when its rows are first shown**, and never per
  page: which keys arrive does not change as rows are paged through, and the
  cells that offer the way back cannot be drawn without knowing them. Following
  one is on demand, which is where the cost of reading the far relation sits.
- **The answer has a ceiling of fifty**, applied in the query. A relation that
  everything points at would otherwise answer a menu with a report.
- **`follow_reference` takes a direction**, and both directions answer with the
  same union. It is said rather than guessed: a constraint name is unique
  within the relation that carries it and not within a schema, so the same name
  can mean a key of this relation and a key landing on it.
- Inside a source the two differ by one thing — which column of this relation
  is paired with which column of the far one — and everything after that
  pairing is one piece of code: the missing-value answer, reading the far
  columns now, refusing a type that cannot be compared, and describing the node
  through `path_to`.
- A source that reads its own keys but cannot search for arriving ones keeps
  `SupportsReferences` and answers 501 to this, which is [D2d](contract.md).

Known deviations:

- **No count per arriving key.** The menu says which relations point here, not
  how many rows each holds: that is a query per key against a relation nobody
  has opened, and the answer is one click away.
- **The row view is not part of this.** One row drawn vertically, with both
  directions offered per column, is a screen and is built over these routes
  without changing them.
- **A source that cannot answer is asked anyway**, once per relation, because
  the screen learns that from the 501 rather than from anything it holds. The
  answer is cached for as long as the relation's tab lives.

Spec: [The way back along a key](../../decisions/2026-09-05-arriving-references-design.md)
