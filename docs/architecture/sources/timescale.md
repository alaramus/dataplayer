# TimescaleDB in a PostgreSQL connection

The extension-specific contract: how Timescale is discovered, how it changes
the meaning of relational operations, and where its long work belongs.
Read alongside [contract.md](contract.md), [relations.md](relations.md),
[actions.md](actions.md), [connecting.md](connecting.md) and
[owned jobs](../jobs.md).

**Implementation status:** T1 inspection and protection are complete as of
2026-09-08; the user confirmed that all tests passed. The isolated T1 matrix
passed on Timescale 2.17.2 and 2.18.0, both PostgreSQL 16.6.
The [validation record](../../../backend/compatibility/timescale/README.md#t1-completion-2026-09-08)
distinguishes recorded command results from the user's final completion
confirmation. The [roadmap](../../migration-roadmap.md) names T2 bounded
metadata changes as the next slice, followed by T3 owned operations.
T1 inspection/refusal evidence does not certify T2/T3 mutation semantics.

## D119. Timescale is composed into PostgreSQL without another source identity

The connector stays `adapter_type=postgres`. A feature package under
`adapters/postgres/timescale/` owns Timescale detection, public metadata readers,
classification and later actions/operation primitives. It reuses PostgreSQL's
session, pool, options, row encoding and query machinery. Existing connector
and logical relation identities are retained.

A separate registered subclass would inherit ordinary methods, so code reuse
alone is not the objection. The same database can gain or lose an extension,
and several extensions can coexist: two registrations still need live discovery
and would make connector type a competing claim about what the database holds.
The facade composes feature providers through explicit collaborators; their
restrictions combine rather than one extension overriding another's answer.

No new credentials, pool, connector migration, dynamic method dispatch or
external plugin loader. A future Timescale-branded connection preset or managed
service template may produce an ordinary PostgreSQL connector; neither is part
of the pilot.

Spec: [TimescaleDB through a PostgreSQL connection](../../superpowers/specs/2026-09-07-timescale-capabilities-design.md)

## D120. Runtime features complement static capabilities and grant no permission

D2/D13 still answer what a driver implements without opening a connection.
`SupportsSourceFeatures.source_features()` and the read-authorised
`GET /connectors/{id}/features` answer what this database exposes now. The
typed answer distinguishes `absent`, `available`, `unsupported` and `unavailable`,
with installed version and safe reasons. Unknown is not absent. An unavailable
optional view is not a failed PostgreSQL connection check.

Detection selects implemented readers/actions from installed version and
verified public API shapes: schema, signature, function/procedure kind and
extension ownership where available. It neither calls mutating functions as
probes nor trusts a name found through `search_path`. Each implementation owns
its requirements, so support declarations cannot grow independently of code.

Initially discovery is shared only within one adapter/request. Persisted
catalog and fetch responses keep D31/D105's ordinary cache rules; mutations
always discover and validate again. Reload and known extension/connector
changes invalidate the Vue-query feature answer. The endpoint is not cached
by HTTP, and no new cross-request feature cache or background poller is added.

The Options panel reads features on opening and offers Reload. Vue Query keys
include the connector ID under the existing connector prefix, so connector
updates invalidate the answer. Catalog reload and known source structure effects
also invalidate it. No focus/reconnect refresh or interval polling is added.
Unsupported capability (501) hides this optional section; request failures show
an inspection error rather than stale detection or an absent extension.

`SupportsActions.all_actions()` is async across all three adapters, allowing
live discovery to supply this connection's vocabulary. This T2 foundation is
implemented with regression coverage written; validation is pending. No
Timescale mutation actions are registered yet. PostgreSQL implements the optional
`ExplainsActionAvailability.action_offers(node_id)` protocol: one read returns
eligible actions and typed named refusals. Its ordinary `available(node_id)`
delegates to that same answer. The menu and execution use the source reason;
sources without this protocol retain the generic refusal. For multiple targets,
the first explicit refusal in request order explains a blocked selection; an
eligible destination still admits a destination workflow. Lookup stays a
registered action set. This reason transport is implemented but unvalidated.
No Timescale commands appear on a database without the extension. Static
action declarations carry typed feature requirements so the type catalog can
word conditional capabilities honestly. The default-empty tuple uses the closed
`FeatureCode` vocabulary. The server appends the installation condition to the
derived capability title, so the existing type catalog and search receive the
same wording without a second frontend feature-name table. This describes an
installation prerequisite, not verified mutation support or permission.
D118 target resolution and application
grants remain independent, and execution also faces PostgreSQL permissions.

Spec: [TimescaleDB through a PostgreSQL connection](../../superpowers/specs/2026-09-07-timescale-capabilities-design.md)

## D121. Timescale specialises relations and exposes inventories as paged reports

A hypertable remains a `TableNode`; a continuous aggregate remains a `ViewNode`.
Optional literal-discriminated `specialization` models distinguish them in the
catalog, relation model and summary without changing IDs or the preferred rows
view. Missing specialisation defaults to null for existing payloads. One source
classification builds all those answers; no untyped `hypertable_info` travels
with every column or fetched page.

The System section gains a discovered TimescaleDB section with fixed report
nodes for Hypertables, Chunks, Dimensions, Continuous aggregates, and Policies
and jobs. They use explicit public-view projections, validated server-side
filters/sorts, outer stable tiebreakers and the existing fetch ceiling. A catalog
level lists reports, never an unbounded chunk tree. Their reserved, versioned
IDs resolve through the same registry for listing, path, fetch and SQL content.

Details exposes bounded typed facts and `related_views`: source-issued report
IDs with initial closed-vocabulary filters. Opening Chunks from a hypertable
therefore opens the existing report filtered to that relation, with visible,
editable filters. These defaults are navigation, not access restrictions.

`NodeSummary.related_views` defaults to an empty list, with at most 16 entries.
Each entry contains a report node and at most 16 ordinary filters. Hypertables
link to their Chunks, Dimensions and jobs reports using both schema and name;
continuous aggregates link to their logical view entry. These links reuse the
classified relation identity without probing optional report APIs during
summary loading; opening the target repeats the report's own API checks.

The Continuous aggregates report projects fields shared by the inspected
2.17.2/2.18.0 and 2.29.2 public APIs. It omits the legacy `finalized` column,
which is absent in 2.29.2, instead of requiring it or inventing a replacement
value. Other projected columns and extension ownership remain mandatory.
Regression coverage for both view shapes is written but unrun; this fix does
not certify the complete Timescale 2.29.2/PostgreSQL 17 combination.

Root relation size/row statistics are not presented as whole-hypertable totals.
Unavailable totals stay null; on-demand statistics use public APIs and a
five-second inspection timeout. Time boundaries and integer boundaries are
different shapes, with large integers carried losslessly as decimal strings.
Private Timescale catalogs are not an inaccessible-view fallback.

Optional Details metadata has a five-second budget for API inspection and the
target read together. A typed answer contains hypertable dimension/chunk counts
and compression configuration, or aggregate source/materialization identity,
materialized-only mode and compression configuration. Failure leaves the main
summary and report links intact and gives a safe unavailable reason. Compression
configuration does not state that every chunk is compressed. Chunk counts cross
the boundary as decimal strings. Root-table analyze/vacuum timestamps are not
presented as hypertable-wide statistics. Size and compression-ratio inspection
use separate public-function strategies. Optional statistics have their own
five-second budget for function inspection and reads together, after basic
metadata. A failed measurement retains earlier facts and measurements. Readers
verify extension ownership, extension schema, function kind, exact argument and
result types, and execution permission before calling a schema-qualified API
with a bound regclass identity. Only a single local result is accepted;
distributed results are not silently summed or truncated.

Detailed size reports current table/index/TOAST/total bytes, including chunks.
For an aggregate it describes its materialization, not the real-time source
portion. Compression statistics prefer the columnstore API when its public
shape is available and otherwise use the legacy API; an execution failure does
not trigger a second strategy. They describe recorded before/after compression
sizes and reported chunk counts, not a current whole-relation compression ratio.
Null measurements stay null and all counts/bytes cross as decimal strings.
Aggregate compression statistics target the public metadata's materialization
identity. Empty, ambiguous, malformed or remote results give a safe unavailable
reason. No private catalog fallback or per-chunk request loop is used.

The initial job report lists native job identity, target, routine, ownership and
scheduling settings. Arbitrary job configuration and error text are not selected:
custom routines can put secrets in both. A separate Job statistics report reads
the public `job_stats` view, so missing statistics never hide the job inventory.
Unrun jobs may have no statistics row; absence is not a zero run count. Timestamps
are source text to preserve PostgreSQL infinity values, durations retain source
interval text, and counters remain numeric for sorting and lossless transport.
The report independently validates view ownership, columns and read access.
The jobs report now projects allowlisted retention, compression and refresh
parameters after verifying the configured routine's extension ownership and
`(integer, jsonb)` procedure signature. Interval and integer lag columns are
separate; canonical intervals retain calendar units and integers stay numeric.
JSON type, length and PostgreSQL input validation precede casts. Null parameter
cells mean absent, inapplicable or invalid, not zero; the report does not claim
to validate policy execution semantics. Unknown/custom routines have no policy
kind or parameter values. Raw config never leaves the source. This projection
requires PostgreSQL's `pg_input_is_valid` (PG16+); older servers refuse this
optional report at its normal read probe. Other reports remain independent.
Interval fields are selected as source text to
retain calendar units; integer boundary fields remain numeric for source-side
ordering and use D23's lossless decimal-string cell transport.

Deliberate limits: no new `hypertable`, `continuous_aggregate` or `chunk` node
kind; no first-class chunk rows view in T1. Later chunk actions target the
hypertable and validate selected chunk membership. First-class chunk navigation
requires a separate demonstrated need.

Spec: [TimescaleDB through a PostgreSQL connection](../../superpowers/specs/2026-09-07-timescale-capabilities-design.md)

## D122. Extension compatibility constrains ordinary PostgreSQL operations

A shared live relation context distinguishes ordinary user relations, Timescale
relations and extension-owned internals. Dedicated extension schemas are
protected, and chunk/materialisation membership protects objects wherever they
live. Merely sharing `public` with extension functions protects no user table.
Dedicated Timescale namespace names are reserved by structured operations even
before installation, so new application-created objects cannot occupy them.
Schema mutation and cascade admission conservatively follow PostgreSQL
dependencies, including ownership edges in both directions and whole relations
for column dependencies. The scope is a protection check, not a promised drop
inventory. An incomplete scope refuses before rehearsal; ordinary PostgreSQL
without Timescale retains its existing cascade behaviour. A schema containing
extension functions cannot be renamed/dropped through these actions, while its
ordinary relations remain individually usable.
Every structured entry point, including direct mutation requests, imports,
schema/cascade changes and previews, consults that context. An unknown answer
cannot silently permit a write to a possibly protected object.

T1 enables inspection and logical row reads/export but disables structured
hypertable/continuous-aggregate writes with reasons until the relevant
version/storage strategy is tested. Ordinary tables retain their operations
where no protected target/dependency is affected. Internal relations always
refuse ordinary row/DDL mutation. Read-only paths issue no synthetic physical
row handles or unsupported system-column reads; write support later requires
proof of optimistic identity under storage changes.
Ordinary grid writes remain outside T1-T3; later management actions do not
implicitly enable row editing.

The SQL editor retains D62/D66's explicit source-SQL authority and read-only
transaction boundary. This restriction on structured operations does not claim
to sandbox every function an authorised SQL user can call.

Generic reconstructed DDL and model-code exports must not imply Timescale
recreation fidelity; they are withdrawn for specialised relations until that
representation is implemented. T1 also gates inherited backup/restore offers
and execution for Timescale databases. Restore inspects a bounded custom-archive
inventory before effects and refuses Timescale-bearing archives even into a
plain PostgreSQL target. A future restore strategy must handle compatible
extensions, pre/post-restore lifecycle, failures and recovery.

Support is declared against tested public API strategies and pinned source
fixtures, including legacy and columnstore APIs. Installed does not mean every
operation is supported, and a signature match alone never enables a mutation.

Spec: [TimescaleDB through a PostgreSQL connection](../../superpowers/specs/2026-09-07-timescale-capabilities-design.md)

## D123. Long source actions are owned jobs with fixed targets and partial outcomes

In T3, job-producing actions return typed plans through a dedicated transport
that reuses action/grant checks and returns a job ID. A feature module above
`jobs` and `connectors` owns admission and execution lifecycle; adapters own
source operation primitives and never import the job runner. Register the new
module in the enforced layer/SDK contracts and its handler in assembly.

Costly conversion/storage work is previewed with read-only planning, not an
execution rolled back. Plans carry exact target identities, normalised
parameters, API strategy and preconditions; changed plans require renewed
review. Empty chunk selection never means all chunks. Native Timescale policy
jobs remain source jobs, not DataPlayer Job rows.

An owned operation records its initiating user, connector revision, required
access and fixed selection. Admission allows at most 1000 chunks and one active
operation per connector, atomically in the application database. This does not
coordinate external clients, policies or duplicate saved connections. Access,
enabled state, identity and membership are rechecked at execution boundaries.
Credentials remain in the connector, never public job parameters.

Each committed chunk keeps its outcome; a first failure stops further dispatch.
Cancellation cancels/cleans up active SQL and prevents the next unit, but does
not undo prior commits. The two databases cannot commit atomically: interrupted
unrecorded outcomes stay unknown until reconciled. D81 still automatically
replays nothing; explicit retry reconciles the original targets before making
a new plan. Fixed named steps may be accompanied by measured completed/total
counts, never invented time-based progress.

Invalidate connector data after each commit and each uncertain possible commit,
including failure, cancellation and restart recovery. The existing activity
surface reads the durable job; accepting it creates no second local running
operation. Later policy actions require structure access, and retention-policy
confirmation describes future automatic deletion by the source.

The first T2 plan model covers a future-chunk interval change. It records the
database/relation OIDs as decimal text, schema/name, time dimension and its
current interval, typed requested duration, extension version and exact API
identity. Its SHA-256 fingerprint covers the complete canonical JSON plan;
malformed fingerprints and changes to any field require renewed review.
It carries no credential, connector authority or execution admission. Duration
amounts are strict positive integers with a closed unit vocabulary; calendar
units remain calendar units. Models and staleness tests are written but unrun.
The interval model is not yet registered as an executable action.

The shared single-action transport now accepts an optional `reviewed_fingerprint`
separately from form parameters. `ActionPreview.fingerprint` carries the review
value; `ActionInfo.requires_plan_review` is derived from `RequiresReviewedPlan`.
Execution routes these actions only to `perform_reviewed`, after the ordinary
availability and grant checks, and refuses a missing fingerprint. The action
must re-plan and compare under its source execution boundary; the route never
treats the fingerprint as authority or checks staleness outside that boundary.
Existing actions keep their normal parameter transport. Backend transport tests
are written but unrun; the client was regenerated after this schema change.

The action form requires a successful unblocked fingerprint before submitting
an action marked for review, and sends it outside the form parameters. Parameter
changes immediately invalidate the displayed plan and in-flight replies; stale
replies cannot enable the button during the debounce. A refused execution keeps
the form open, clears its review and asks for a new plan without retrying the
mutation. Optional previews preserve their advisory behaviour. Component and
mapping tests are written but unrun; browser validation is still outstanding.

The interval inspector has a five-second total budget and read-only statements.
It verifies public-view ownership/columns, resolves one owned
hypertable with one time dimension, excludes aggregate materializations, and
checks the exact extension-owned `set_chunk_time_interval(regclass, anyelement,
name)` function shape and execution privilege without calling it. Planning is
limited to the pinned 2.17.2/2.18.0 versions; this is not mutation certification.
Integer dimensions, multiple dimensions, calendar intervals and subday intervals
for date columns are refused. Shared duration models preserve calendar units,
but this strategy does not offer them. There is no private catalog fallback.
Unit scenarios remain unrun; isolated real-source planning scenarios passed
in the 2026-09-09 interval validation run. The
interval preview renderer now uses the shared ActionPreview transport with the
plan fingerprint, source-resolved quoted target, old/new interval and the
existing-chunk warning. Refused or failed inspection returns a blocked preview
without a fingerprint. The renderer is internal; action registration and
transport validation remain outstanding.

Multi-query preview inspection now has a PostgreSQL read collaborator bound to
one repeatable-read, read-only transaction. Acquisition, reads and cleanup share
a five-second budget; each statement also has a source timeout. This keeps a
plan from combining committed metadata versions across separate connections.
The collaborator does not expose mutation methods. It is snapshot consistency,
not execution locking or mutation certification. Unit coverage is written but
unrun.

The candidate interval execution strategy coordinates through a SHARE ROW
EXCLUSIVE lock on the public dimensions view, followed by SHARE UPDATE EXCLUSIVE
on ONLY the target root. PostgreSQL recursively locks the view's base relations;
on the pinned versions these are Timescale's hypertable and dimension catalogs.
This briefly blocks database-wide Timescale metadata changes, including chunk
creation, and requires lock permission on the public view. No privilege is
granted by DataPlayer and no private catalog is directly queried or modified.
The preview discloses the scope; the fingerprint includes the view OID.
Execution replans under those locks at READ COMMITTED before comparing the
fingerprint and calling the qualified API with bound values. It has a two-second
lock timeout and five-second total budget, with no automatic retry. Planning
also refuses same-named overloads and PostgreSQL majors other than 16.
Real-source permission, concurrent-change, refusal and cancellation checks
passed on both pinned fixtures on 2026-09-09. Registration and remaining
backend/frontend validation are still pending.

The unregistered SetChunkInterval action now connects the preview and execution
primitives to the existing reviewed transport, requires structure access and
resolves its target through the catalog. Plain execution refuses a missing
review; its parameter schema excludes calendar units. Source planning remains
the authoritative hypertable/ownership check. Isolated
mutation scenarios (future versus existing chunks, an external native setter,
stale review, source refusal, cancellation cleanup, lock permission and an
overload) passed on both pinned fixtures in the 36-test isolated interval run.
Unit coverage remains unrun. The exact command and scope are recorded in the
[compatibility record](../../../backend/compatibility/timescale/README.md#t2-interval-execution-isolated-validation-2026-09-09).

Once reviewed execution has been dispatched, its route invalidates connector
reads on success, refusal, failure or cancellation. This conservatively covers
an uncertain commit without inferring source effects from error text. Preview,
missing-review and access refusal do not dispatch execution. Ordinary actions
retain their existing success-only invalidation. Route/helper tests are written
but unrun.

Spec: [TimescaleDB through a PostgreSQL connection](../../superpowers/specs/2026-09-07-timescale-capabilities-design.md)
