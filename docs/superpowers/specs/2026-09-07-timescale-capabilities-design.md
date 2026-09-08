# TimescaleDB through a PostgreSQL connection

Date: 2026-09-07.
Status: accepted for implementation. T1 is in progress; the runtime-feature
contract and read-only PostgreSQL discovery are written but have not been
validated. T2 and T3 define subsequent delivery boundaries, not features
claimed by T1.

Decisions: D119 through D123, in
[TimescaleDB](../../architecture/sources/timescale.md).

## Outcome

A person connects to a TimescaleDB database using the existing PostgreSQL
connection form. DataPlayer recognises the installed extension, distinguishes
hypertables and continuous aggregates, and describes chunks, dimensions,
storage and policies without requiring a second connection to the same data.
Ordinary tables continue to use the ordinary PostgreSQL workflow.

Timescale-specific code has a package of its own inside the PostgreSQL driver.
The registered source type remains `postgres`. Extension detection is read-only:
it neither installs nor upgrades an extension. SQL transport, credentials,
pools, grants, row encoding and query documents remain shared.

This design settles the adapter boundary and makes the read-only pilot concrete.
It also states the constraints later mutations must satisfy. Supporting a
PostgreSQL operation against an ordinary table does not establish that it is
safe against a hypertable, a continuous aggregate or an internal chunk.

## Evidence and corrections to the earlier proposal

The following legacy sources were inspected as workflow evidence:

- `dbwebtool/webdb/settings.py`, which registers `Timescale` separately.
- `dbwebtool/webdb/data_adapter/timescale/timescale_extended_adapter.py`,
  especially `to_hypertable`, `update_hypertable_policies`, `chunk_handler`,
  compression loops, dimension builders and tablespace operations.
- `dbwebtool/webdb/data_adapter/postgre/postgres_extended_adaptor.py`,
  `templates.py` and `extensions/timescaledb.py`: detection, hypertable row
  estimates, metadata and internal schema classification also lived here.
- `myquasar/src/myapp/components/DataSource/Timescale/timescale.ts`,
  `TimescaleHypertableEditor.vue`, `TimescaleHypertableStatistics.vue` and
  `MasterViewer/TimescaleView/timescaleViewHelper.ts`: the editing, statistics
  and chunk-selection workflows.

These are paths in the two legacy projects named by AGENTS.md. Their absolute
machine paths are not dependencies of the new implementation.

The old adapter combines range and integer dimensions, optional hash dimensions,
conversion of populated tables, compression settings and policies. Its chunk
workflow covers selection by time, compression, decompression, moving, splitting,
merging and detaching. Continuous-aggregate *policy management* is present;
this inventory does not establish a complete aggregate-definition editor.

Method declarations are not proof of a working feature. Examples in the old
code include `attach_chunk` in the frontend vocabulary versus `attached_chunk`
in the backend dispatcher, `reorder_chunk` in that vocabulary without a matching
dispatcher entry, and an empty chunk list expanding to all chunks in the
compression helpers. Porting the action names would preserve those ambiguities.

The current implementation provides better starting points:

- `PostgresAdapter` composes modules on one `PostgresSession`.
- D13 describes *type-level* capabilities through class protocols; D9/D118
  already resolve action applicability for individual nodes.
- `SupportsActions.all_actions()` currently returns the class vocabulary
  synchronously. Merely filtering `available()` would leave Timescale commands
  greyed out on every ordinary PostgreSQL database.
- `PostgresFetch` already uses `(tableoid, ctid)` for physical identity and
  `xmin` for optimistic concurrency. It is not missing `tableoid`, but the
  behaviour of those system columns over compressed storage still needs proof.
- D70 row commands and D81 owned jobs now exist. The 2026-08-31 inventory that
  called them missing is historical, not the present implementation boundary.
- D54 currently protects `pg_*` and `information_schema`; that does not cover
  Timescale-owned schemas or internal materialisations in other schemas.
- `PostgresBackup.restore_program()` produces a plain `pg_restore --clean`
  command and has no Timescale pre/post-restore lifecycle.

Two claims in the preliminary discussion are deliberately corrected here:

1. A subclass inherits unchanged PostgreSQL methods automatically; a second
   class does not inherently require copying every method. The argument for
   composition is the extension lifecycle and the interaction of independent
   features, not a claim that inheritance cannot reuse code.
2. D2a does not require a new node kind for every database-specific subtype.
   A hypertable is still a table, and a continuous aggregate is still a view.
   Typed specialisation can describe them without changing their addresses or
   copying all relational behaviour into new union members.

## D119: choose composition and retain one source identity

| Option | Benefit | Cost | Decision |
| --- | --- | --- | --- |
| Registered `timescale`, subclass of `PostgresAdapter` | Clear product name; ordinary methods inherited | Both types still need extension/version checks; an existing PostgreSQL connection can gain Timescale; shared operations still need Timescale-aware behaviour | Not selected |
| Two registered facades composed from shared PostgreSQL modules | Explicit separate assembly without inheritance | Two identities for the same database semantics and repeated choices when extensions coexist | Not selected |
| One PostgreSQL adapter with a composed Timescale feature package | One saved identity, runtime extension lifecycle, shared relational implementation | Requires an instance-level feature answer and explicit extension integration points | Selected |

A second adapter would be appropriate for genuinely different connection or
execution semantics, or a deliberately separate product workflow. The legacy
Timescale workflow provides no such requirement. The same database can contain
Timescale and other extensions; combinations must not require subclasses such
as a Timescale-plus-PostGIS driver.

The intended source package is:

```text
adapters/postgres/
  adapter.py                composition and protocol delegation
  session.py, pool.py        existing driver and connection ownership
  features.py               installed extensions and feature composition
  relation_context.py       one classification used by readers and mutations
  timescale/
    profile.py              compatible public API shapes and feature requirements
    catalog.py              relation specialisations and owned objects
    reports.py              fixed reports built from public views
    summary.py              bounded typed Timescale facts
    actions.py              T2 operations, registered objects
    operations.py           T3 plans and execution primitives, no job runner
```

Create modules when the slice needs them, not empty files for future work.
Shared wire models live in driver-free modules under `adapters/`; all psycopg
use stays under `adapters/postgres/`. Use a small explicit registry of compiled
feature providers, with Timescale as its first member. No external plugin
loader, `__getattr__`, generated proxy, mixin hierarchy or ORM plugin table.

The shared PostgreSQL components receive the feature/classification collaborator
at construction. They do not import concrete Timescale action classes or grow
name-based branches. The feature package owns its SQL, detection and restrictions;
the facade assembles the objects. Multiple feature contributions are combined:
an operation is allowed only if every applicable restriction allows it.

There is no connection migration, replacement connector, new auth variant or
separate pool. The existing connector UUID and node IDs remain authoritative.
A future Timescale connection tile could be a preset over PostgreSQL, and a
future Timescale service could be a separate service template producing a
PostgreSQL connector. Neither is needed for this delivery.

## D120: distinguish implementation, discovery and permission

Three questions must have independent answers:

| Question | Authority | Meaning |
| --- | --- | --- |
| Does this driver implement a capability? | Existing class protocols and action declarations | D2/D13; independent of network access |
| Does this database expose the required feature/API? | Fresh instance-level discovery | The extension, its version and its usable public objects |
| May this caller do this to this object now? | DataPlayer grant, object classification, action validation and PostgreSQL | No cached feature flag grants authority |

Add the optional method-only protocol
`SupportsSourceFeatures.source_features() -> SourceFeatures` and
`GET /connectors/{id}/features`, requiring `read` access through the usual
connector resolver. A source without the protocol returns 501. A disabled or
foreign connector keeps its existing refusal. The source-types catalog does
not connect to a database.

`SourceFeatures` contains `observed_at` and at most 32 `SourceFeature`
models. A feature has a closed code (initially `timescaledb`), a title, an
optional installed version, a state and a safe reason. The states are:

| State | Meaning |
| --- | --- |
| `absent` | The installed-extension query succeeded and found no Timescale |
| `available` | Installed, with a recognised baseline inspection API; not a promise that every mutation is implemented or permitted |
| `unsupported` | Installed, but no compatible baseline reader is implemented |
| `unavailable` | Presence or usable metadata could not be established; the reason distinguishes permission from another inspection failure |

Unknown never becomes absent. An unreachable database still produces the usual
connection failure; a successful connection with an unavailable optional view
does not become a failed connection check. Failures expose the application's
own wording, never driver text. The public answer contains no function OIDs,
credentials or stored capability switches.

Feature codes are unique. `available` requires an installed version;
`unsupported` and `unavailable` require a reason. The baseline reader must
classify user-facing hypertables and continuous aggregates; individual optional
reports do not determine whether that baseline is usable.

Internally, discovery reads `pg_extension` in the selected database and selects
implemented API variants using the installed version plus required view columns
and function/procedure signatures. A bare `pg_proc.proname` match is insufficient:
verify namespace, signature, function versus procedure and extension membership
where available. Resolve extension-owned objects by identity, not by a user-
controlled `search_path`. Calling an API is not a discovery probe.

Each reader/action declares its own required API shape next to its implementation.
Feature availability is derived from those requirements, not a second manual
list of supported UI operations. No mutation is selected solely because a
function of the right name exists. Unsupported optional readers leave the
remaining reports usable and explain which detail could not be read.

### Lifetime and invalidation

T1 memoizes discovery only within one adapter/request, using a shared in-flight
load for modules in that request. It does not introduce a cross-request feature
cache. A real catalog/fetch cache miss, direct summary read, feature read or
mutation gets fresh discovery; ordinary cached catalog/fetch answers retain
D31/D105's stated staleness. There is no discovery query per catalog row or
per fetched data row.

The features endpoint sends `Cache-Control: no-store`. Vue-query owns the
displayed feature answer with a 30-second stale window; opening the relevant
connector and explicit Reload revalidate it. Successful extension install/drop,
connector edits and structure-change notifications invalidate the feature query
alongside catalog, relation metadata and affected pages. External extension
changes are observed on the next actual read/Reload, not by a new background
poller. Every mutation discovers again even if the UI is still showing an old
answer. Profile data is not put in a pool key or attached forever to a pooled
connection. Longer-lived query sessions must not retain a profile as permission
to execute later operations.

### Actions and type descriptions

In T2, make `SupportsActions.all_actions()` asynchronous across the three
adapters. It returns the vocabulary relevant to this connection, independent
of the selected node. `available(node_id)` then determines applicability;
execution repeats that check and validates the live target. This avoids
mutating a request-local action registry as a side effect of calling
`available()`. Lookup remains a closed registry; no client name resolves to a
method outside it.

With no Timescale installed, Timescale commands do not appear. With Timescale
installed, implemented commands remain visible but disabled where the object
or supported API cannot admit them, with a specific reason rather than only
"cannot be done to this node". Extend the source applicability answer to carry
that reason; D118's final target-selection logic remains shared. Permissions
are filtered by the existing route and checked on execution.

`action_types()` remains the static list of implemented action classes. Add a
default-empty typed feature requirement to action declarations and expose that
condition on the derived D13 capability description, so the type catalog can
say "when TimescaleDB is installed". Do not advertise future T2/T3 actions in
T1 merely because this spec names them.

## D121: relational nodes stay relational; large inventories are reports

Retain `TableNode.kind = table` and `ViewNode.kind = view`, with their existing
IDs and preferred table representation. Add an optional typed `specialization`
to each relevant model, defaulting to null. Initially the table variant is
`timescale_hypertable` and the view variant is
`timescale_continuous_aggregate`. Use literal-discriminated models, not a
dictionary or several unrelated booleans. Neither variant carries a full
inventory of chunks, jobs or policies.

The same classification produces the catalog node, path, relation description
and summary. `RelationModel.kind` remains its PostgreSQL structural kind;
`RelationModel.specialization` carries the same relation-specific meaning.
`RelationContents` gains typed Timescale detail using that classification.
There is no `hypertable_info` attached to every fetched column or page.

This preserves links, saved tabs, foreign and declared reference targets, row
view and the existing table destination selector. UI consumers render the
typed specialisation for the icon/caption and details; action applicability
stays on the server. Ordinary frontend code never checks
`connector.adapter_type == timescale`.

### Reports and navigation

When baseline inspection is available, the existing System section contains a
TimescaleDB report section. It holds these fixed report definitions, individually
gated by their reader's requirements:

| Report | Main source | What the reader can inspect |
| --- | --- | --- |
| Hypertables | `timescaledb_information.hypertables` | Schema/name, dimensions, chunk count, storage settings |
| Chunks | `timescaledb_information.chunks` | Parent, chunk schema/name, typed time or integer boundaries, storage state, tablespace |
| Dimensions | `timescaledb_information.dimensions` | Column, type, time/integer interval or hash partition count |
| Continuous aggregates | `timescaledb_information.continuous_aggregates` | User-facing view, materialisation, materialized-only setting and definition when accessible |
| Policies and jobs | Explicit projections of public jobs/job-stats views | Policy type, target, schedule, last/next execution and outcome |

Report IDs use a versioned namespace under the already reserved
`pg_dataplayer` prefix, for example `pg_dataplayer.timescale.v1.chunks`. They are
registered definitions, not arbitrary SQL selected by a URL. `path_to`, fetch,
summary, report SQL content and query generation must all resolve the same
definition. Update consumers that currently assume System reports have only
one path segment after the section.

These are existing `ReportNode`s opened by the ordinary grid. SQL projections
use explicit columns, source-side filtering and sorting, an outer deterministic
tiebreaker and the existing fetch ceiling of 1000 rows, reading one extra for
`has_more`. Limits and filters apply in SQL; a report must not first materialise
all chunks in Python. The catalog lists five reports, not a chunk per child.
Default ordering is schema/name for relations, parent/schema/name for chunks,
hypertable/dimension ordinal for dimensions, and job ID for jobs. A user's sort
keeps those keys as trailing tiebreakers.

The policies/jobs report projects known fields and typed, allowlisted policy
settings. It does not expose arbitrary job configuration blobs, user-defined
job SQL or raw source error text as report metadata.

Add default-empty `NodeSummary.related_views`, a bounded list of typed
`RelatedNodeView` values: title, target node ID and initial filters using the
existing closed filter vocabulary. A hypertable's Details offers Chunks,
Dimensions and Policies prefiltered by its schema/name. The UI resolves the
target through the normal node-opening path and shows the filters in the grid;
they are editable navigation defaults, never an access boundary. Reuse the
same reports rather than making a report identity for every hypertable.
Sharing the opened page retains its committed filters under D58/D59.

T1 does not add chunk catalog nodes or an "Open chunk rows" command. Later
chunk-management forms select typed identities from the paged Chunks report
while their action target remains the parent hypertable. A first-class chunk
node can be designed later if saved chunk views or chunk-specific catalog
navigation justify it. Its absence is intentional, not a fabricated table ID.

### Cost and truthful metadata

Catalog listings batch-classify their relations against public metadata rather
than issuing one Timescale query per relation. Do not copy the old
`_timescaledb_catalog` joins; public information views are the supported boundary.
Private tables are not a fallback when a view is inaccessible.

A hypertable's root `reltuples` and `pg_total_relation_size(root)` are not its
whole logical row count or size. In catalog and relation model, leave those
values null unless the chosen reader supplies a trustworthy aggregate with
the same meaning. Do not display an empty root as zero rows/bytes. T1 reads
whole-hypertable size and storage statistics on demand in Details through the
supported public functions. Columnstore/legacy statistics are normalised into
typed fields with explicit meanings; absent statistics stay absent.

Time boundaries and integer boundaries are different union members. Integer
values cross JSON as decimal strings, preserving values beyond JavaScript's
safe integer range; they are not inferred epoch timestamps. Summary facts
never turn nulls into zero and do not count user rows to fill a caption.
Read-only Timescale inspection statements have a five-second server-side
timeout, scoped to the operation and restored before a connection is reused.
A timed-out optional statistic leaves Details usable with a notice; a failed
report read is an error, not an empty report. No automatic COUNT(*) or unbounded
all-hypertable size computation is added.

## D122: compatibility controls shared operations too

### Support policy

Target the single-node TimescaleDB 2.x public API family. Read-only readers may
support multiple known public view shapes; each has explicit required fields.
No promise is made about all 2.x installations, an unknown future major,
sunsetted distributed hypertables or Cloud-only administration.

The test matrix must include plain PostgreSQL, a pinned pre-2.18 Timescale
release with the legacy API, a pinned 2.18-or-later release with columnstore
APIs, and the modern Timescale/PostgreSQL pair chosen for the pilot. Use a
PostgreSQL major supported by each release; an old Timescale fixture need not
run on the application's PostgreSQL 18. Before T1 validation, record exact
image versions/digests, installed extension versions and supported reader
shapes beside the fixtures. No `latest` tag or claim that a searched release
is necessarily the newest. No Timescale image was started for this design.

Mutation compatibility is narrower: enable a strategy only for tested
version/API combinations, with an explicit policy for extending the tested
range. A signature match alone does not prove semantics. Unsupported operations
remain disabled with their reason. Legacy and columnstore implementations are
strategies behind one user intention, not two sets of frontend controls.

### A shared classification, enforced by every structured entry point

`relation_context` distinguishes ordinary relations, hypertables, continuous
aggregates and extension-owned implementation objects. It records protection
and reasons separately from display specialisation. A shared schema such as
`public` is not protected wholesale merely because extension functions live in
it. Dedicated Timescale schemas are protected; chunk and materialisation
membership is checked by identity even if an object lives elsewhere.

Every relevant entry point consults that classification: fetch and export,
insert/update/delete and imports, relation/column/index/constraint changes,
rename/move/drop and their previews, destination selection, model-code/DDL
generation and backup/restore preparation. Hiding a node or disabling a button
is never the server-side guard. Directly naming an internal relation cannot
bypass it. Schema-level changes and cascading operations must also account for
affected Timescale objects; if the scope cannot be established safely, refuse
before executing or rehearsing the mutation.

The T1 protection scope uses a conservative PostgreSQL dependency walk, capped
at 1000 objects with a five-second read-only inspection timeout. Ownership
edges are traversed both ways and column references protect whole relations.
This can refuse more than the exact drop would remove; it never presents the
walk as a drop preview. A missing or oversized scope is refused. Dedicated
Timescale namespace names are reserved even before extension installation.

T1's delivery policy is deliberately conservative:

| Target | Read/describe/export | Structured row writes | Structured DDL/actions |
| --- | --- | --- | --- |
| Ordinary user table in the same database | Existing behaviour | Existing behaviour | Existing behaviour, subject to protected dependencies |
| Hypertable | Enabled through the logical table | Disabled with a Timescale support reason | Disabled until the relevant operation is tested |
| Continuous aggregate | Enabled through the user-facing view | Disabled | Disabled until specifically supported |
| Chunk, materialisation or other internal relation | Read-only if PostgreSQL permits it | Always disabled through ordinary row APIs | Always disabled through ordinary relation APIs |
| Timescale report | Existing report behaviour | Disabled | Only specifically declared commands, none in T1 |

This restriction must also reach per-column editable/insertable fields, import
destinations and server validation. Unavailable or unsupported classification
does not silently admit ordinary mutations against an object that might be
Timescale-owned. Unrelated reads stay usable; uncertain writes carry a reason.

Read-only fetching of hypertables and compressed internal relations must not
select `xmin`, `ctid` or `tableoid` merely to manufacture an unused row handle
or ordering. If no proven row identity is available, issue no handle and state
that paging without a unique explicit order has the same limitation as a view.
Where a visible primary key is usable, it can provide a read-order tiebreaker
without promising optimistic writes.

Ordinary grid writes remain outside T1-T3; enabling a management action does
not enable row editing. A later write-support slice must prove existing
primary-key and physical-handle semantics for every supported storage mode.
Compression changes
can invalidate handles; stale handles must refuse, never affect a different
row. Revalidate permissions and storage state during execution, including a
background policy changing storage between UI reads and writes.

The SQL editor retains D62/D66: PostgreSQL read-only transactions enforce the
locked mode, and explicitly authorised source SQL is not made into a sandbox
for every Timescale function by this feature. This pilot does not widen the
editor's statement vocabulary or claim that disabled structured controls
prevent all mutations by an authorised SQL user.

### DDL and whole-database copies

An ordinary CREATE TABLE or CREATE MATERIALIZED VIEW reconstructed from columns
alone is not a complete recreation of a hypertable or continuous aggregate.
Until an extension-aware representation is implemented and tested, withdraw
DDL representation and SQL model-generation actions for those objects with a
reason; structure inspection stays available. SQLAlchemy/Django/DBML generation
must not silently imply it preserves Timescale settings either. A later
explicitly labelled logical-schema export is a separate choice.

Logical whole-database backup is a viable PostgreSQL workflow, but restore
requires Timescale-specific preparation and completion. T1 does not claim the
current plain `pg_restore --clean` implementation is compatible: backup/restore
preparation for a Timescale-bearing connection is refused with a reason until
an integration-tested strategy lands. Inherited `SupportsBackup` must not leave
a falsely usable button; add an instance-level availability answer for the
backup UI and repeat validation in both preparation and job execution.

The restore gate also inspects the source archive in the existing isolated
tools container before any target mutation. An archive identifying a Timescale
extension is refused even when the target is plain PostgreSQL. Use a bounded
`pg_restore --list` inspection of a validated custom archive and conservatively
refuse an ambiguous/unreadable inventory, rather than substring-searching its
raw bytes. A future restore strategy must define extension-version matching,
pre/post hooks, cleanup on failure and cancellation, and recovery of a target
left in restoring mode. That strategy is not part of T1-T3.

## Mutation vocabulary and parameters for T2/T3

Every operation is a registered, namespaced action with its own Pydantic model
and `extra=forbid`. No generic `chunk_handler`, arbitrary SQL interval fragment
or client-named backend function. The first actions target one relation;
`bulk` remains false until true multi-relation semantics are designed.

The user intentions are distinct:

- Convert an existing ordinary table into a hypertable. Preserve its node ID;
  distinguish empty-table conversion from explicitly consented data migration.
- Change the time/integer chunk interval for future chunks.
- Configure rowstore/columnstore settings, including validated ordered columns
  and segment columns. Do not conflate a policy's age threshold with a chunk
  merge/rollup interval as the old conversion method did.
- Add, replace or remove a retention policy.
- Add, replace or remove a columnstore/legacy-compression policy.
- Add, replace or remove a refresh policy for an existing continuous aggregate.
- Convert a reviewed set of chunks to columnstore or back to rowstore as a job.

T2 initially supports the time-based variants and already-existing continuous
aggregates. Integer dimensions are accurately readable in T1; integer policy
mutation and custom now/hash functions are deferred until a bounded function
selection and unit contract exists. No automatic SQL-function creation.

Time durations are a positive integer amount plus a closed unit, not SQL text.
Calendar months, if offered by a strategy, remain calendar months and are never
flattened to seconds. SQL intervals are composed by the driver and bound as
values. Instants carry explicit time zones. Integer bounds are decimal strings
validated against the source integer type. No input's meaning is guessed by
whether its string looks numeric.

Conversion planning validates the relation, time column/type, nulls, existing
partitioning, primary/unique keys, relevant references and API restrictions.
Potential scans have explicit bounds/timeouts and may refuse; they never return
a positive eligibility answer after inspecting only a sample. Data migration
and building indexes can be long even if the API is one SQL call and therefore
use a job. T2 may deliver only empty-table conversion until the job path exists.

Policies are replaced explicitly and atomically when the supported API permits
it; a bare conflict is not implicit replace. Start/end offsets and schedule
intervals are validated together. Policy previews explain that enabling a
retention policy authorises *future* automatic deletion by Timescale, beyond
the lifetime of a DataPlayer session. `requires=structure` and destructive
confirmation apply to creating/replacing such a policy. All Timescale management
actions require at least `structure`; grants do not bypass PostgreSQL ownership
or function permissions.

Read-only plans are the preview for conversion, storage rewrites and policy
work. Do not execute a costly operation then roll it back to discover its
effects. This is an explicit extension of D46's PostgreSQL-drop rehearsal
approach, not a claim that all actions share that implementation. A plan carries
target identity, normalised parameters, selected API strategy, preconditions,
impact and an opaque fingerprint. Execution re-plans and refuses changed
identity, strategy or relevant preconditions. A fingerprint detects staleness;
it grants no authority. Empty conversion takes an appropriate relation lock
and rechecks emptiness before the transaction changes it.

Chunk selection always has a parent hypertable. Empty selection means no work,
never all chunks. Schema/name identities are re-resolved against that parent's
live chunk membership, and bound as qualified regclass values where the API
takes regclass. A chunk from a different hypertable is rejected even if the
caller can read both. Time-window selection states whether it selects whole
chunks or overlapping chunks; the submitted plan fixes the actual set rather
than re-evaluating a moving `now()` when execution begins.

## D123: owned execution with explicit partial outcomes

Long source operations use the existing JobRunner. Job orchestration lives in
a new feature module above `jobs` and `connectors`, for example
`app/source_operations/`; add that module to the enforced layer and SDK
containment contracts. It imports generic adapter operation protocols, not
psycopg or Timescale implementation modules. Assembly registers its handler in
`api/main.py`. No `timescale/jobs.py` may import `app.jobs` from the adapter
layer. PostgreSQL strategies execute SQL; the handler owns durable lifecycle.

T3 introduces a job-producing action protocol that produces a typed, validated
operation plan. `POST /connectors/{id}/actions/{name}/jobs`, declared by action
transport metadata, reuses the existing action lookup, availability and access
checks and returns 202 with `job_id`. Existing synchronous `ActionResult` routes keep
their contracts. The UI records accepted work through the existing jobs/activity
source, without also creating a second "running request" operation.

The accepted job stores the initiator, connector, required access, operation,
normalised parameters, connector revision fingerprint and the exact selected
targets. Secrets are resolved from the connector by the handler and never
copied into public job parameters. A connector revision change makes the job
refuse rather than following edited credentials to a different database.
Use a server-maintained revision or private keyed fingerprint; never expose a
plain hash of credentials as the revision, and never trust a client-supplied
revision as proof that the connector is unchanged.
Each new operation kind has a typed durable payload validated on load; the
existing generic JSON column is storage, not permission to pass arbitrary
dictionaries between layers.

The job belongs to its initiating user, including when a connection was shared.
Access and connector enabled state are checked at admission, when execution
starts and before each further chunk. Revocation cannot undo already committed
work or reliably stop a statement before the next cancellation boundary.
Record this limitation in the activity result. Cancel/read remain owner-scoped.

Admission is bounded to 1000 exact chunks and one active source-operation job
per connector, with atomic admission using the application's database, not
the read-cache Redis. The connector is the initial subject lock granularity;
overly coarse locking is preferable to concurrent jobs changing intersecting
hypertables. Coordinate with restore's connector subject admission. This does
not lock external database clients, policy jobs or a second saved connector
pointing at the same database; source-side locks and fresh validation remain
necessary. More than 1000 targets requires a narrowed selection, not silent
truncation or multiple automatic jobs.

Processing is sequential, one chunk per source transaction/API execution unit.
Every target has a durable outcome: pending, running, completed, already in the
requested state, refused, or outcome unknown after interruption. Progress uses
the existing fixed named steps (validate, execute, reconcile), with measured
completed/total counts added as typed progress if displayed; percentages based
on elapsed time are not introduced. The first failure stops further dispatch
and leaves remaining targets pending/not attempted in the final report.

Cancellation requests cancellation of the active SQL operation through the
driver and waits for rollback/connection cleanup before releasing that session.
It stops before the next chunk and does not undo earlier commits. A job cannot
report that every chunk was cancelled if some are already complete.

The application database and the external source cannot commit atomically. If
SQL committed but the process died before its outcome was saved, the target is
unknown until reconciled with the source. On restart, D81 marks the job
interrupted and automatically replays nothing. An explicit retry first
reconciles the original fixed targets and makes a new plan; it does not blindly
re-execute the old list or sweep in newly created chunks.

Invalidate connector data after every committed unit, and after an uncertain
outcome that might have committed, including failure/cancellation paths. On
recovery invalidate interrupted operations before allowing their old cached
answers to be reused. Use D31's generation/in-flight protection and invalidate
frontend feature, catalog, relation, summary and affected page queries from the
job outcome. Invalidating only on successful overall job completion is wrong
for a job that changed three chunks and failed on the fourth.

## Delivery and acceptance

The first optional Details reader uses public hypertable dimension/chunk counts
and compression configuration, and public aggregate source/materialization
identities, materialized-only mode and compression configuration. Inspection of
view ownership/columns and the targeted read share a five-second deadline. It
reads at most two records to detect ambiguous identity. Missing, malformed or
inaccessible metadata yields a safe typed unavailable answer without discarding
the basic relation summary or related links. Chunk counts remain decimal text;
configuration is not presented as measured compressed-chunk coverage. Root
analyze/vacuum timestamps are suppressed for specialised relations. Whole-source
size and compression statistics require separate public-function strategies.

### T1 — recognise and inspect safely

Hypertable and aggregate reports project explicit metadata columns from their
public views: owners, hypertable dimension/chunk counts and tablespaces,
aggregate source/materialization identities, and compression/materialization
configuration. Each report validates its complete projection on opening;
missing columns refuse that report without changing baseline discovery. Chunk
counts remain numeric for sorting and use lossless cell transport. Compression
configuration is not measured compressed-chunk coverage. The projections were
compared with the 2.18.0 public view definitions linked below; compatibility
validation remains pending.

Deliver composition, instance discovery, typed specialisation, public-view
reports, summary facts/related views and the shared-operation protections.
The feature endpoint is consumed by the connector UI and reports a detected
version or a safe reason. No Timescale mutating action is published.

Required evidence, with real source fixtures where semantics matter:

1. An ordinary PostgreSQL connection, including a database with another
   extension, keeps its catalog, options, URL and ordinary-table workflow.
2. Two databases on one server, only one with Timescale, produce independent
   features. A new adapter instance detects install/remove without changing the
   connector type; explicit Reload invalidates the displayed answer.
3. Discovery differentiates absence, unavailable metadata and unsupported API;
   insufficient permissions do not look like empty inventories. A spoofed
   same-named function in another schema is not selected.
4. One schema containing ordinary tables, multiple hypertables and a continuous
   aggregate has consistent catalog/path/model/summary specialisations and
   unchanged logical node IDs. Existing reference navigation and saved views
   still address the same relations.
5. Timestamp and integer hypertables, empty and populated, include mixed
   rowstore/columnstore chunks. Reads/export do not depend on unsupported
   system columns. Integers beyond 2^53 retain their exact values.
6. Chunks reports paginate/filter/sort at the source, including duplicate names
   in different schemas. Query counts do not grow once per listed relation;
   generated SQL applies bounds and deterministic ordering at the outer level.
7. Root-only estimates never appear as the hypertable's total. Optional
   statistics can time out without destroying other Details content.
8. All direct row/DDL/import/action entry points refuse protected internals,
   including forged IDs and cascade/schema routes. Ordinary tables in `public`
   remain usable. T1's hypertable/aggregate write refusal appears both in UI
   flags and in execution, with no rehearsal-side writes.
9. Backup and restore admission refuse Timescale targets and Timescale-bearing
   archives into plain targets before effects. A normal PostgreSQL backup
   remains eligible; ambiguous archive inspection refuses safely.
10. Read grants work for inspection, write-only versus structure gates remain
    correct, foreign/disabled connectors retain their refusals, and secrets
    appear in no metadata/error response.
11. Browser coverage opens a detected hypertable as rows, follows Details to
    its filtered Chunks report, reloads after an extension-state change, and
    confirms disabled mutation controls. Default/null specialisations still
    render older non-Timescale payloads correctly.

Mocks prove detection and wire-shape branches; real Timescale/PostgreSQL tests
prove compressed-row reads, identities, metadata and permission semantics.
Keep Timescale fixtures isolated from the application's development database;
they create their own schema/data rather than assume prestart seeded them.

### T2 — bounded metadata changes

Deliver async connection-specific action vocabulary, reasoned applicability,
typed planning, interval/storage configuration, time-based policies and
empty-table conversion for the tested API strategies. Each action includes
injection, permission, stale-plan, concurrent-change and failure-path tests.
Time-based existing-aggregate refresh-policy management does not imply an
aggregate creation editor. Mutation tests use disposable fixture data.

Before marking T2 ready, a policy refusal or failed replacement must leave the
old policy intact; conversion must refuse invalid keys, null time values and a
table populated after preview. Refresh offsets must not silently conflict with
the configured retention intent. Changes to the chunk interval must explain
that already-created chunks are not repartitioned.

### T3 — long operations and partial outcomes

Deliver the job transport/orchestration and reviewed chunk conversion in both
directions; populated-table conversion joins only with a tested plan/locking
strategy. Include cancellation during SQL, failure after a committed chunk,
restart between source commit and progress persistence, revoked access, edited
connector, concurrent admission and cache invalidation race tests. UI reload
must recover the same job and explain its completed and unattempted work.

### Explicitly outside T1-T3

- Ordinary grid writes to specialised Timescale relations: require a separate
  storage-mode and optimistic-concurrency acceptance slice.
- Detach/attach, split/merge, move/reorder chunks and destructive drop-by-time:
  each needs version-specific semantics, exact selection and a recovery story.
- Integer policy mutation, additional/custom dimensions, automatic now/hash
  function creation and experimental chunk-skipping APIs.
- Continuous aggregate definition/editor and `time_bucket` chart aggregation;
  ordinary permitted SQL queries keep their existing behaviour.
- Tablespace create/drop: PostgreSQL administration, not a Timescale feature.
  Filesystem locations on the source server require a separate permission
  contract. Timescale tablespace attachment is deferred with chunk management.
- Timescale-aware backup/restore, a managed Timescale service template, a
  separate source-catalog tile, cloud tiering, Toolkit and distributed features.
- Automatic extension installation/upgrade, migration of old application's
  connector records, a general-purpose extension marketplace or background
  policy scheduler in DataPlayer. Native Timescale policy jobs stay in Timescale;
  their reports are not fabricated DataPlayer Job rows.

The delivered slices must not claim parity with every legacy menu entry.

## Documentation and validation

This spec supersedes the adapter/node-kind prerequisites in the Timescale
section of the 2026-08-31 PostgreSQL inventory. D2b composition is retained;
D13 is extended by a separate instance question rather than replaced. D54's
system protection is extended by discovered object membership; D46 previews
gain a read-only planning implementation for costly source operations.
D81 keeps its owner, lifecycle and no-replay rules.

The architecture statements are explicitly marked unimplemented until their
slices land. The roadmap promotes T1 ahead of adding another source family;
completion removes the item only after the approved acceptance checks pass.

The initial design commit changed no runtime code. Implementation progress is
recorded in the roadmap. Documentation validation is
`bash scripts/check-docs.sh`, subject to the project's approval rule. Later
implementation requires the affected backend tests, strict mypy, ruff and
import checks, generated client after API changes, frontend unit/type/lint/build
checks and targeted browser scenarios as prescribed by ENGINEERING.md. Tests
are written with implementation and run only with the user's approval.

## Upstream references

The initial Chunks, Dimensions and jobs report projections were also compared
with [the 2.18.0 public view definitions](https://github.com/timescale/timescaledb/blob/2.18.0/sql/views.sql)
on 2026-09-08. This is API evidence, not a tested compatibility claim. Report
opening validates extension membership, required columns and read access.
Intervals remain source text and integer boundaries use the existing lossless
cell transport. The initial job projection omits arbitrary configuration and
error text because custom jobs can store secrets there; typed policy parameters
and public job statistics remain to be delivered.

Read on 2026-09-07. Public APIs are evidence for supported strategies, not a
substitute for testing the deployment/version combinations advertised here.

- [TimescaleDB installation](https://docs.tigerdata.com/self-hosted/latest/install/installation-windows):
  extension activation is per database, using PostgreSQL connectivity.
- [Chunk information view](https://www.tigerdata.com/docs/reference/timescaledb/informational-views/chunks):
  time and integer boundary columns have distinct meanings; secondary dimensions
  are described separately.
- [Columnstore conversion](https://www.tigerdata.com/docs/reference/timescaledb/hypercore/convert_to_columnstore):
  the procedure introduced in 2.18 replaces the legacy compression function;
  driver strategies must respect both invocation shape and semantics.
- [Legacy hypertable compression statistics](https://docs.tigerdata.com/api/latest/compression/hypertable_compression_stats):
  the documentation directs newer implementations to columnstore statistics.
- [Logical backup and restore](https://www.tigerdata.com/docs/deploy/self-hosted/backup-and-restore/logical-backup):
  Timescale restore requires explicit preparation/completion and compatible
  database setup; ordinary PostgreSQL transport does not remove those needs.
- [TimescaleDB release history](https://github.com/timescale/timescaledb/releases):
  use version-specific release notes when selecting fixture and mutation
  strategies, especially for supported PostgreSQL majors and breaking changes.
