# Migration roadmap

Last updated: 2026-08-31.

This is the persistent order for moving useful behaviour from `dbwebtool` and
`myquasar` into DataPlayer. It is a route, not a promise to reproduce every old
screen. The old projects are evidence about workflows and edge cases; their
files are never copied into the rewrite.

## How to use this file

At the start of a migration session:

1. Read `AGENTS.md`, `ENGINEERING.md`, this file and the architecture file for
   the area being changed.
2. Continue the first unfinished item in the first unfinished phase. Do not ask
   which feature comes next unless an external decision genuinely blocks it.
3. Inspect the named old sources before designing the slice. Port the useful
   behaviour, not its API, state management or component structure.
4. If the slice introduces a lasting contract, write the decision, architecture
   statement and spec before implementation.
5. Implement tests with the change. Run validation only after the user approves
   the exact commands, as required by `AGENTS.md`.
6. Update the checkboxes, the date above and the "Next session" section when a
   slice is complete or deliberately reordered.

Legend:

- `[x]` implemented and validated;
- `[~]` implementation is written but validation is still pending;
- `[ ]` queued;
- `[?]` discovery is required before the implementation boundary is known.

## Priority order at a glance

| Order | Phase | Relative size | Why it is here |
| --- | --- | --- | --- |
| 0 | Stabilise bounded-page charts | Small | Finish the slice already in the working tree before starting another one |
| 1 | Complete PostgreSQL, files and table workflows | Large, incremental | Every later feature consumes the same catalog, relation and bounded-fetch contracts |
| 2 | Share a bounded fetched snapshot | Medium | High user value and already expressible without raw SQL or a new adapter |
| 3 | Query editor | Large | Supplies an explicit query capability and a reusable result surface before AI is allowed to call it |
| 4 | Managed Docker services in connector creation | Very large | Adds a safe service lifecycle before service-backed adapters multiply |
| 5 | Optional Redis infrastructure | Medium | Needed only when multiple backend processes must share cache or coordination state |
| 6 | Add adapter families deliberately | Ongoing | Breadth is useful only after one complete adapter can exercise each contract family |
| 7 | Charts and dashboards, second slice | Large | Whole-source aggregation and saved layouts require contracts absent from the bounded chart |
| 8 | User-configured AI agent | Very large | Must reuse safe tools, permissions, confirmations and disclosure rules built earlier |

## Phase 0 — stabilise the current chart slice

Status: validated on 2026-08-30.

- [x] A grid page opens as a line, bar or pie chart using the exact bounded
  `FetchRequest` and visible-column order.
- [x] Numeric text in a file page is labelled as numeric only on that page.
- [x] Chart choice persists per exact view and follows a renamed relation.
- [x] Chart tabs use their own `insert_chart` icon rather than the connector
  icon.
- [x] Run the user-approved frontend unit tests, type check, lint, build,
  documentation check and `tests/charts.spec.ts` browser scenario.
- [x] No chart defect was reported by those checks; the four implementation
  markers above are complete.

Exit condition: the chart slice is validated and the working tree contains no
known chart regression.

## Phase 1 — complete the existing adapters and table workflow

This phase comes before new adapter breadth. PostgreSQL and the personal file
source are the reference implementations for relational and filesystem
contracts. A capability is not mature merely because a third adapter can be
registered.

Old sources to inspect:

- PostgreSQL: `dbwebtool/webdb/data_adapter/postgre/`;
- files: `dbwebtool/webdb/data_adapter/file_explorer/`;
- table commands: `myquasar/src/myapp/components/MasterViewer/`;
- row and relationship presentation:
  `myquasar/src/myapp/components/RowTableDetailsView/`;
- old grid behaviour: `myquasar/src/components/XTable/`.

### 1.1 Relationship navigation — first feature after chart validation

- [x] Let a source issue a navigable target for a foreign key. The client must
  not compose or parse a catalog node id (D21).
- [x] From a foreign-key value, open the referenced relation with a safe equality
  filter; cover composite keys, nulls, missing grants and renamed relations.
- [x] Keep the relation model as the source of truth. Do not restore the old
  client-side "weak link" registry in this slice.

D36 settles the contract: `FetchResult.references` says which keys a page has,
`SupportsReferences.follow_reference` answers with the target node and the
predicate, and both nulls and unlookupable target types are answers rather than
errors. Only the forward direction is in this slice; incoming references need a
schema-wide search and a screen of their own.

Validated on 2026-08-30: backend suite, mypy, ruff, import contracts, frontend
type check, lint, unit tests, the documentation check and the whole end-to-end
suite, `tests/references.spec.ts` included.

Exit condition: a user can move from a PostgreSQL row to the referenced rows,
and every identifier and predicate is source-validated.

### 1.2 Safe PostgreSQL structure editing rounds

- [x] Specify and implement changing nullability.
- [x] Specify a safe type-change vocabulary, including what conversions are
  refused and how dependent defaults, indexes and constraints behave.
- [x] Add source-owned index creation and removal.
- [x] Add unique and foreign-key creation/removal only after dependency and
  lock behaviour is explicit.
- [x] Consider relation creation and drop as a separate destructive round; do
  not mix it into a column change. It was one: D45 makes a table out of an
  uploaded CSV, D46 drops one after the source has said what a cascade would
  take with it.

D37 settles the first bullet: `SupportsColumnNullability` takes one relation,
one column and the state asked for, and answers either `NullabilityChanged` or
`NullabilityBlocked`. Rows that contradict a requested `NOT NULL` are counted —
to a ceiling of 1000 — before anything is locked, and the count is a 200 answer
rather than an error, because the driver's own refusal names the offending row
and cannot be passed on. Dropping the requirement is checked against the shape
instead: a primary-key column and an identity column are named as such. Filling
the empty rows is deliberately out of the round; it is a change to every row of
a table and belongs to a data slice.

Validated on 2026-08-30: the whole backend suite, mypy, ruff, import contracts,
frontend type check, lint, unit tests, the documentation check and the whole
end-to-end suite, `tests/structure.spec.ts` included.

D38 settles the second: the target is a code from the same published list a
new column is given, the conversion is composed by the source and never read
from a request, and whether the two types convert at all is asked of PostgreSQL
by a statement that reads no row. Where the column is a string the rows that
the target cannot read are counted, as in D37; elsewhere there is no
non-throwing way to try a cast, so the failure is named by its SQLSTATE
instead — a default that cannot be cast, a view built on the column, a value
out of range. Nothing dependent is dropped to make the change possible.

Validated on 2026-08-30: the whole backend suite, mypy, ruff, import contracts,
frontend type check, lint, unit tests, the documentation check and the whole
end-to-end suite.

D39 settles the third: creating and dropping are one capability, because an
index that can be made and not unmade is a trap. The request carries columns in
index order, a method code and uniqueness, and no name — an index means nothing
to a person beyond the columns it covers, and PostgreSQL already derives a name
and uniquifies it, so the answer reads back which index appeared. What each
method can do is read from `pg_indexam_has_property` and travels with it, so
neither the screen nor the adapter restates it; whether a method fits a column's
type is left to the server, because operator classes change with what is
installed. A unique index over values that already repeat is answered with the
number of repeating values, as in D37, counted with NULLS DISTINCT so nulls do
not count as collisions.

Validated on 2026-08-30: the whole backend suite, mypy, ruff, import contracts,
frontend type check, lint, unit tests, the documentation check and the whole
end-to-end suite.

D40 settles the fourth. A constraint is what an index is not: a named promise
other objects can depend on, carrying the closed `RefAction` behaviour, and
possibly unenforced — so `validated` now travels with every foreign key and
check. What a foreign key may point at is published as `candidate_keys` rather
than worked out by the reader, and the target is a catalog node id handed back
as given. The data refuses both kinds and is counted: repeating values for a
unique constraint, rows pointing nowhere for a foreign key, the latter under
MATCH SIMPLE. Dependency behaviour is explicit — no `CASCADE`, a foreign key
holds its unique constraint in place, and a primary key is not dropped here
because rows can only be edited while one exists (D25). Lock behaviour is
explicit too: the request waits for the scan, as it waits for an index build,
and jobs remain Phase 4.

This is the fourth command the data can stop, so the counting moved into one
module shared by all four.

Validated on 2026-08-30: the whole backend suite, mypy, ruff, import contracts,
frontend type check, lint, unit tests, the documentation check and the whole
end-to-end suite.

Each bullet is its own spec-sized slice. Raw SQL fields are not an acceptable
shortcut. PostgreSQL remains the first implementation; another relational
adapter follows only after the capability contract has settled.

### 1.3 Bulk data movement through the grid

- [x] Paste a rectangular TSV selection into editable cells with type-aware
  validation and one atomic server request.
D41 settles the first bullet. The block travels as rows, because D25 versions a
row rather than a cell, and every row must still hold the version it was read
with or nothing is written. All-or-nothing is a transaction now: the session
gained one, since setting a different value in each row cannot be written as
the single statement D26 used. Every arriving value is checked against its
column's type with `pg_input_is_valid` before anything is written, and the
cells that fail come back named rather than counted — the mirror of D37 through
D40, where what stands in the way is data the reader has not seen. Where the
block lands is decided in the browser and refused there if it would run past
the loaded rows or the visible columns; the grid's TSV also became lossless in
both directions, so a copy survives its own paste.

Validated on 2026-08-30: the whole backend suite, mypy, ruff, import contracts,
frontend type check, lint, unit tests, the documentation check and the whole
end-to-end suite.

- [x] Import a bounded CSV into an existing relation with column mapping,
  preview, transaction semantics and a downloadable error report.
D43 settles the second bullet, and renames it on the way: it is not an import
of a CSV but a bounded move of rows from any readable source into any source
that accepts them, with a file in personal storage as the first pair. It is the
first command naming two connectors, so it lives in `connectors` rather than in
an adapter, and it checks two permissions. Columns are paired explicitly and
both sides validated; the target checks every value before writing and names
the ones it cannot read; one transaction, so a partial import cannot happen.

The downloadable error report the plan asked for is deliberately absent, and
the entry is marked done anyway: a report of what went wrong part-way only
means something where part-way exists, and the same information is the answer
to the request, bounded like everything else.

Validated on 2026-08-30: the whole backend suite, mypy, ruff, import contracts,
frontend type check, lint, unit tests, the documentation check and the whole
end-to-end suite.

- [x] Add export scopes beyond the current page only through an adapter-owned
  streaming/export capability; never raise the fetch ceiling to simulate an
  export.
D44 settles the third bullet. PostgreSQL holds one server-side cursor and emits
bounded batches; the platform writes those batches to a temporary CSV in the
user's personal storage and atomically publishes it only after the stream ends.
The browser receives a short-lived ticket for that exact file and lets the
native download path carry it, so neither Python nor JavaScript assembles the
whole relation in memory. Page download remains D28's separate bounded path.

Validated on 2026-08-30: the whole backend suite, mypy, ruff, import contracts,
frontend type check, lint, unit tests, the documentation check and the whole
end-to-end suite.

### 1.4 File-source depth

- [x] Specify how a readable file declares its available representations and
  which one opens by default. Opening a catalog node must not imply
  `SupportsFetch` or a grid: text, structured documents, tabular data and media
  need different viewers. The source identifies representations; the client
  chooses a viewer by representation kind, never by connector type or a
  hard-coded extension table.
- [x] Give JSON and JSONL a bounded structured-data viewer that preserves the
  document rather than flattening it into rows. JSON opens as one navigable
  value; JSONL opens as a bounded sequence of independent values. Invalid or
  truncated input keeps an honest text representation with a precise parse
  notice instead of silently becoming a table.
- [x] Keep a tabular interpretation of JSON/JSONL as an explicit **View as
  table** representation, offered only when the source can project records.
  It uses the existing bounded `FetchRequest` and grid after the user asks for
  it; it is not the file's default viewer. A top-level array supplies records,
  another top-level value is one record, columns are deterministic for the
  whole projection, and neither the server nor the client guesses that a key
  such as `data` contains the table.
- [x] Open text, JSON and JSONL in a source editor that highlights by file
  type, and save the document back under the version it was read at. Editing
  is a capability of its own (D48): the source issues an opaque version, a
  stale one is a conflict rather than an overwrite, and the format is checked
  by the server before anything is written.

D47 and D48 are implemented. The catalog publishes ordered representations for
every node; `SupportsContent` and its route carry bounded text, JSON and JSONL
results separately from `SupportsFetch`; `SupportsContentEdit` carries the
whole document with its version; and the workspace gives every representation
its own stable panel. JSON is bounded at 4 MB, text at 256 KB, JSONL at 100
records and 4 MB per request and 1 MB per physical line, and the editor at 4 MB
in both directions.

Two things were decided against D47 as first written. A document tab has one
mode — it opens the editor, and the JSON tree was removed from the screen, so
the bounded text, JSON and JSONL results are currently reached by tests alone;
they are kept because paging a large JSONL file is the one thing the editor's
ceiling cannot do. D49 now gives `SupportsContent` a screen for verified image
content. And a text file no longer declares a table representation, so it can
no longer be chosen as the source of an import (D43); CSV, TSV, JSON and JSONL
still can.

Validated on 2026-08-31: the whole backend suite, mypy, ruff, import contracts,
frontend type check, lint, unit tests, the documentation check and the whole
end-to-end suite. Two end-to-end scenarios had to be repaired on the way and
neither was about this slice — `reload.spec.ts` still expected a text file to
open as rows, which D47 had already changed, and the delete loop in
`grid.spec.ts` ticked a row before the page had been re-read, so the source
was asked to delete an already deleted row and rightly refused.

- [x] Finish the rendered document while it is fresh: a table of contents,
  in-document search, export, and relative paths resolved against the
  document's own directory — that last one is what makes a link to a
  neighbouring file inert today, and what would let an image beside a `.md`
  file be shown. Each needs the byte path of D49 or a place in the workspace,
  not a new contract. Deliberately ahead of Parquet: it is the same code, read
  by the same people, and the reason a document cannot yet point at its
  neighbour.
  The implementation and its tests are written. Headings form a duplicate-safe
  Unicode outline; literal search visits visible prose and callouts; rendered
  HTML embeds verified local images and the same inert copy prints to PDF; and
  relative references walk source-issued paths and catalog nodes without
  composing an id. Validated on 2026-08-31 by the whole backend suite, mypy,
  ruff, import contracts, frontend type check, lint, unit tests, production
  build, the documentation check, the four file end-to-end scenarios and the
  whole 105-scenario end-to-end suite. One old workspace geometry scenario
  failed once under parallel load, passed 3/3 in isolation, and the repeated
  whole suite passed 105/105.
- [x] Add Parquet and XLSX as explicit optional capabilities, with sheet or
  dataset selection, format-specific metadata and server-side bounds. Their
  natural representations may use the grid, but that does not make every file
  tabular.
  D51 settles it. Sheet selection is browsing rather than a parameter: a
  workbook is a file with children, and each sheet is a `dataset` node whose id
  the source issues. A Parquet file stays one file and keeps the `table`
  representation. Both answer `relation-model` — which node can be described is
  now said by the source in `CatalogNode.describable` instead of decided by the
  client from a kind — and the facts only their format knows travel as a typed
  union in `RelationModel.dataset`. Three fields of the relation model and one
  of a column turned out to be relational vocabulary a file has none of, and
  are absent rather than filled in. Nothing reads a whole file: a Parquet page
  is streamed from the row groups it falls in, a sheet through the read-only
  iterator, and a workbook is refused from the zip's own directory before a
  byte is inflated. `encode_cell` moved out of the PostgreSQL adapter into
  `adapters/cells.py`, since the canonical text of a value belongs to no driver.
  Validated on 2026-08-31: the whole backend suite, mypy, ruff, import
  contracts (the new one verified by breaking it), frontend type check, lint,
  unit tests, production build, the documentation check and the whole
  106-scenario end-to-end suite, then read in the browser. Two defects came out
  of that reading rather than a check: a Parquet handle stayed open after a
  malformed file was refused, which on Windows also blocks the delete; and a
  sheet's caption read "1 rows · 1 columns" and said nothing about a sheet the
  spreadsheet hides.
- [x] Add source-declared download and the first safe, bounded image viewer.
  D49 gives every adapter one download-action transport over selected nodes.
  The file source returns one file unchanged or archives a set or directory;
  PNG/JPEG previews are verified under byte and pixel ceilings.
  Validated on 2026-08-31 by the whole backend suite, mypy, ruff, import
  contracts, frontend type check, lint, unit tests, the documentation check and
  the whole end-to-end suite. They found four defects, each in code no test had
  reached: an undefined name in the download error path, a blocking stat inside
  an async method, the new `image` format falling through `assert_never` when a
  picture was asked for as rows, and a type narrowing that did not survive into
  a render closure. Four download tests wrote their fixtures with `write_text`
  and then compared bytes, which only holds where the platform adds no carriage
  returns; they write bytes now. The documentation check refused AGENTS.md over
  its budget, so the trap about `../.env` and rehearsing CI moved into the
  backend architecture file.
- [x] Add Markdown as a rendered representation, ported from `rich-md-viewer`.
  D50 gives `.md` two representations — rendered first, source second — and the
  document is parsed, sanitised and drawn entirely in the browser: prose through
  `markdown-it` with KaTeX and task lists, and `mermaid`, `echarts`, `svg` and
  code fences as bounded blocks that mount when they are scrolled to. Code
  fences reuse the editor's CodeMirror rather than a second highlighter, and the
  whole stack is loaded only when a document is opened. The initial slice left
  its tabs, table of contents, in-document search, export, share links and i18n
  in the old project; the `[x]` follow-up above brings the middle three into the
  existing panel without bringing its tabs or sharing model.
  Validated on 2026-08-31 by the whole backend suite, mypy, ruff, import
  contracts, frontend type check, lint, unit tests, the documentation check and
  the whole end-to-end suite, and then read in the browser: the sample document,
  this repository's AGENTS.md, and the demo document of the project the viewer
  came from. Six defects came out of reading rather than running — a relative
  link styled as a live link while being inert; `_require_editable_file`
  refusing to edit a document once `.md` stopped being a text file; four
  diagrams taking each other's output because Mermaid renders through one shared
  element; those diagrams arriving as empty shapes because Mermaid labels are
  HTML in a `foreignObject`; charts drawn as empty boxes because the option
  named a series this bundle did not carry; and tall inline maths colliding with
  the line above it. A second reading, against the standalone viewer this came
  from, added four more: edge labels boxed by the background rectangle Mermaid
  draws once labels are native text; a chart title sitting on its own legend;
  code highlighted with CodeMirror's light-theme palette on a dark ground, in
  the editor as well as in a fence; and no way to copy a block or save a drawing.
  Every block now wears one frame with those actions in it, and a callout an
  agent wrote — `summary`, `decision`, `risk` and six more — is drawn as a card
  with its fields laid out. Video embeds stay out: a `component:YouTubePlayer`
  fence is left as code.
- [x] Add bounded audio, video and PDF viewers. Their bytes use D49's dedicated
  content path and trustworthy metadata; audio and video first need a range
  contract, and PDF needs an isolation/rendering decision.
  D52 settles both. The range contract is a capability of its own —
  `SupportsContentStream` answers with the verified media type, the size and a
  reader over two offsets, and the HTTP of `206`, `416` and `Accept-Ranges`
  belongs to the route, which is what lets a player ask for the end of an MP4
  before it asks for the beginning. Metadata is trustworthy because the
  container is parsed rather than the suffix believed: an exact duration from a
  WAV and a FLAC, duration and picture size from an MP4 whose index may sit at
  the end, and a refusal where the bytes are not what the name promised. The
  isolation decision is that a PDF is drawn by the application with `pdf.js` —
  canvas plus a text layer, no annotations, no forms, no scripting — rather
  than handed to the browser's own viewer, which understands all three. A
  stream ticket lives an hour rather than a minute, because a recording is
  seeked over its own length and every seek is a new request.
  Validated on 2026-08-31: the whole backend suite, mypy, ruff, import
  contracts, frontend type check, lint, unit tests, production build, the
  documentation check and the whole end-to-end suite, then read in the browser
  — the WAV plays, the MP4 plays to its end, and the PDF draws its page and
  its text. Three things came out of that reading. The plan named an
  `isEvalSupported: false` option that version 6 of the renderer no longer has,
  so the decision was corrected to what actually holds; a page was laid out one
  scrollbar too wide, and the panel now re-fits itself when its room changes,
  which is also what a document opened behind another tab needs; and the first
  page is drawn without waiting to be scrolled to, because intersection is
  delivered only while the browser paints.
- [ ] Add archive browsing only after containment, decompression limits and
  symlink behaviour are specified.

### 1.5 PostgreSQL-specific operations, after the general table rounds

- [?] Inventory extensions, processes, tablespaces, backups and TimescaleDB
  operations from the old adapter.
- [ ] Port them one capability at a time as source-specific catalog node kinds
  and declared actions. Do not add PostgreSQL branches to generic screens.

Exit condition for Phase 1: PostgreSQL covers the common daily table workflow;
files open in a representation appropriate to their content, with a grid only
where a tabular representation is declared; and remaining old behaviour is
classified as a deliberate later capability rather than an unknown gap.

## Phase 2 — share a bounded fetched snapshot

The first sharing slice is data sharing, not connector sharing; D33 already
covers the latter. It shares an immutable snapshot, never credentials and never
an instruction to rerun an unlimited source query.

Old sources to inspect:

- `myquasar/src/myapp/components/CopyPaste/`;
- `myquasar/src/myapp/stores/contentCopyRegister.ts`;
- `dbwebtool/webdb/webapi/view_services/fetch_data_handler.py`;
- `dbwebtool/webdb/webapi/view_services/execute_data_handler.py`.

Sequence:

- [ ] Specify snapshot scope: begin with one fetched column, then allow the
  visible bounded page without changing the storage model.
- [ ] Re-fetch the exact bounded request at creation time, preserve lossless
  text and declared column types, and apply a hard byte ceiling.
- [ ] Store the snapshot durably with owner, opaque token, expiry and revocation.
  Personal storage or the application database is the first implementation;
  Redis is not a prerequisite.
- [ ] Decide separately whether a link requires sign-in or may be public. Public
  sharing needs an explicit confirmation that states the expiry and data scope.
- [ ] Add the Share command to the fetched column/grid and a minimal read-only
  viewer for the recipient.
- [ ] Cover foreign access, expiry, revocation, connector deletion, secrets,
  audit metadata and end-to-end link opening.

Exit condition: the button creates a bounded, revocable snapshot whose meaning
does not change when the source changes.

## Phase 3 — query editor

The query editor is an explicit source capability, not a generic text box added
to every connector. It needs a decision that reconciles intentionally supplied
SQL with D2c: DataPlayer may pass a complete statement to a source that declares
the capability, but must never interpolate client identifiers or fragments into
another query.

Old sources to inspect:

- `myquasar/src/myapp/components/SqlEditor/`;
- query/history code in `myquasar/src/myapp/serverAPI.ts`;
- `dbwebtool/webdb/webapi/view_services/execute_data_handler.py`;
- SQL execution methods in the old PostgreSQL adapter.

Sequence:

- [ ] Define `SupportsQuery` with dialect, statement policy, timeout, row cap,
  cancellation support and read/write classification.
- [ ] First slice: one PostgreSQL read statement, server-enforced timeout and
  result bound, cancellation, safe errors and no multi-statement execution.
- [ ] Render results through the existing typed grid boundary so copy, download
  and bounded charts are reused rather than rebuilt inside the editor.
- [ ] Add per-user query history with an explicit retention/delete policy;
  queries may themselves contain sensitive literals.
- [ ] Add write/DDL execution only as a later slice with a transaction policy,
  affected-object summary and explicit confirmation.
- [ ] Add file querying through DuckDB only after the file capability says which
  files and paths may be exposed to it.

Exit condition: PostgreSQL read queries are bounded, cancellable and reusable by
the same result tools as a fetched relation.

## Phase 4 — managed Docker services in connector creation

This is not "run a compose string from the form". It is a server-owned service
lifecycle whose successful output may become connector credentials.

Old sources to inspect:

- `dbwebtool/webdb/webapi/view_services/connector_actions.py`;
- `dbwebtool/webdb/sysutils/utils/compose_file_creater.py`;
- `dbwebtool/docker_templates/`;
- `myquasar/src/myapp/components/EditConnectorAI/`.

Sequence:

- [ ] Define a code registry of approved service templates and generated
  credential fields. No arbitrary image, command, environment key, volume or
  host path comes from the client.
- [ ] Model create/start/stop/restart/delete as owned asynchronous jobs with
  durable state and realtime progress. A request must not wait for image pulls.
- [ ] Detect Docker availability and state the refusal in the adapter catalog.
- [ ] Pilot one PostgreSQL service: generate credentials server-side, wait for
  readiness, then fill and save the connector through the normal connector
  schema.
- [ ] Add retry, idempotency, cancellation, log tail, orphan discovery and
  deletion semantics. Deleting a connector must not silently delete a volume.
- [ ] Add a Redis pilot only after the lifecycle is correct for PostgreSQL.
- [ ] Threat-model socket access, project/container naming, resource limits,
  network exposure and concurrent users before enabling this outside local
  development.

Exit condition: a user can request an approved service from the connector
window, watch it become ready and receive a normal encrypted connector without
the browser constructing Docker commands.

## Phase 5 — optional Redis infrastructure

The rewrite already has D31's bounded, process-local `DataCache`. Redis is not
needed to make a single-process installation correct. Add it when deployments
need shared cache entries and invalidation across backend workers, not merely
because the old project had a Redis object.

Sequence:

- [ ] Extract a cache backend protocol without weakening D31's exact keys,
  in-flight coalescing, LRU/TTL bounds or post-mutation invalidation rules.
- [ ] Define versioned serialization, namespace by deployment and user, and
  decide whether sensitive fetched values require encryption in Redis.
- [ ] Implement optional Redis cache storage plus a cross-worker invalidation
  channel. Failure must degrade to direct reads, not take data access down.
- [ ] Add configuration, health reporting, TLS/auth examples and an optional
  Compose service; keep the in-memory backend as the default.
- [ ] Only after measurement, reuse Redis for distributed locks, job fan-out or
  share acceleration. Snapshot truth and job truth remain durable elsewhere.

Exit condition: two backend workers observe the same invalidation behaviour,
and turning Redis off changes performance rather than correctness.

## Phase 6 — add adapter families deliberately

Do not port seventy adapters as seventy partial packages. Add one representative
of a new contract family, settle the capability, then add siblings cheaply.

Recommended order after Phase 5:

1. DuckDB or SQLite for a second local/relational implementation and file-query
   synergy.
2. MySQL for a second networked SQL pool and dialect.
3. Redis/Valkey as a user data source, distinct from infrastructure Redis.
4. S3/MinIO for an object-store catalog and streaming file transfer.
5. Kafka or RabbitMQ only after a stream/topic contract is designed; a stream is
   not a paged table pretending to have rows.

Every adapter must meet the same acceptance checklist:

- [ ] self-described options and variants, secret splitting and connection
  string behaviour;
- [ ] connection check, resource ownership and cleanup;
- [ ] honest catalog/fetch/action capabilities and safe errors;
- [ ] permissions and cache policy;
- [ ] backend contract tests, frontend capability behaviour, an end-to-end
  scenario and architecture documentation.

## Phase 7 — charts and dashboards, second slice

The bounded page chart in D35 stays honest and small. The next chart round must
not silently reinterpret it as a whole-relation result.

Old sources to inspect:

- `myquasar/src/myapp/views/ViewChartNew/`;
- `myquasar/src/myapp/views/Dashboards/`.

Sequence:

- [ ] Define an adapter-owned aggregate request with a closed group/measure/
  function vocabulary and hard cardinality limits.
- [ ] Add whole-result aggregate charts as a distinct data source from the
  bounded page chart.
- [ ] Define saved chart ownership and persistence before adding names or URLs.
- [ ] Define a dashboard layout and widget versioning before multiple charts
  share a screen.
- [ ] Add realtime metric widgets only for sources with a real subscription
  capability. Polling and streaming remain different contracts.
- [ ] AI suggestions may return only the closed chart specification and belong
  after the disclosure and tool rules in Phase 8.

## Phase 8 — user-configured AI agent

The old ChatAI area contains useful interaction ideas but is several products at
once: provider settings, local models, chat history, tools, MCP, memory,
attachments and external agents. Port it as independent slices.

Old sources to inspect:

- `myquasar/src/myapp/components/ChatAI/`;
- `myquasar/src/myapp/components/AiPanel/`;
- `dbwebtool/webdb/ai_handler/`;
- `dbwebtool/webdb/dashboard/agents.py`.

Sequence:

- [ ] Provider/model configuration with encrypted per-user keys and explicit
  third-party data disclosure.
- [ ] One streaming conversation surface, cancellation and a retention/export/
  deletion policy.
- [ ] A typed tool registry that wraps existing catalog, fetch, query, action,
  chart and share capabilities. Read-only tools are the default.
- [ ] Confirmation for every mutation, clear tool-call progress and an audit
  record. The model never receives connector credentials.
- [ ] User instructions and a saved agent definition with a bounded tool
  allowlist.
- [ ] Attachments, memory, MCP/external agents and local browser/server models
  only as later, separately consented capabilities.

Exit condition: a user can configure one agent, understand where their data is
sent and let it use the same permission-checked operations available in the UI.

## Explicitly deferred

These old areas are not on the main migration path until a user goal promotes
one of them: web terminal, MRP, trading screens, translation, karaoke/media
generation, generic monitoring agents, Kubernetes/cloud control panels and
one-off adapter demos. Their presence in the old repository is not evidence
that they belong in the platform core.

## Patterns that must not be ported

- dynamic `getattr` action dispatch from a client method name;
- client-built SQL identifiers or predicates;
- server data duplicated into Pinia stores;
- generic screens branching on adapter names;
- Redis as an untyped global dictionary;
- arbitrary Docker Compose or shell text accepted from the browser;
- administrator access bypassing data grants;
- chart or AI payloads accepting executable renderer/tool configuration;
- a large fetch limit used as export, sharing or aggregation.

## Corrections found while using it

Reported from the running application rather than by a check, and fixed where
they were found.

- **A row moved when it was edited, and pages overlapped.** The fetch ordered
  rows only when the reader had chosen a sort, so the order was the plan's and
  an updated row — written elsewhere by MVCC — reappeared at the end. D42 makes
  the order part of the answer.
- **A relation without a primary key could not be edited or deleted.** That was
  a property of how the handle was built, not of the data. D42 lets such a row
  be named by its place, with the version check it always had.

Those two corrections were validated on 2026-08-30: the whole backend suite,
mypy, ruff, import contracts,
frontend type check, lint, unit tests, the documentation check and the whole
end-to-end suite.

- **A table chosen as an import source was treated as another catalog level.**
  The D43 route already reads any `SupportsFetch` source, but its dialog alone
  called only a file a readable leaf. It now uses the catalog's one node-role
  and readability table, so tables and views are selected while schemas and
  directories are entered; a failed level read no longer invents a breadcrumb.
  Validated on 2026-08-30 by frontend type check, lint, unit tests, production
  build, the documentation check and the whole end-to-end suite, including the
  PostgreSQL-to-PostgreSQL path.

## Next session

The media and PDF viewers are complete and validated. Resume with archive
browsing, the last item of 1.4, and specify containment, decompression limits
and symlink behaviour before implementing it: an archive's entries are members
of a file, which is the shape D51 gave a workbook's sheets, and its bytes are
the ranged stream of D52. After 1.4 the phase closes with 1.5, the inventory of
PostgreSQL-specific operations in the old adapter.
