# Migration roadmap

Last updated: 2026-08-30.

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
- [ ] Add unique and foreign-key creation/removal only after dependency and
  lock behaviour is explicit.
- [ ] Consider relation creation and drop as a separate destructive round; do
  not mix it into a column change.

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

Each bullet is its own spec-sized slice. Raw SQL fields are not an acceptable
shortcut. PostgreSQL remains the first implementation; another relational
adapter follows only after the capability contract has settled.

### 1.3 Bulk data movement through the grid

- [ ] Paste a rectangular TSV selection into editable cells with type-aware
  validation and one atomic server request.
- [ ] Import a bounded CSV into an existing relation with column mapping,
  preview, transaction semantics and a downloadable error report.
- [ ] Add export scopes beyond the current page only through an adapter-owned
  streaming/export capability; never raise the fetch ceiling to simulate an
  export.

### 1.4 File-source depth

- [ ] Give JSON/JSONL a bounded tabular view with deterministic columns.
- [ ] Add Parquet and XLSX as explicit optional capabilities, with sheet or
  dataset selection and server-side bounds.
- [ ] Add download and safe previews for images, audio, video and PDF without
  loading an unbounded file into the normal row response.
- [ ] Add archive browsing only after containment, decompression limits and
  symlink behaviour are specified.

### 1.5 PostgreSQL-specific operations, after the general table rounds

- [?] Inventory extensions, processes, tablespaces, backups and TimescaleDB
  operations from the old adapter.
- [ ] Port them one capability at a time as source-specific catalog node kinds
  and declared actions. Do not add PostgreSQL branches to generic screens.

Exit condition for Phase 1: PostgreSQL and files cover the common daily table
workflow, and remaining old behaviour is classified as a deliberate later
capability rather than an unknown gap.

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

## Next session

Continue **Phase 1.2** with unique and foreign-key constraints, whose bullet asks for dependency and lock behaviour to be explicit first. The first question there is what a constraint
adds over the index D39 already builds: a unique constraint owns its index and
cannot be dropped through it, which is the refusal that slice already names. The
second is what a foreign key needs from the relation it points at — an index
there, a lock on both tables, and a validation scan that can be deferred with
`NOT VALID`, which is the two-step vocabulary D38 deliberately did without.
