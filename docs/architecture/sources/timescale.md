# TimescaleDB in a PostgreSQL connection

The extension-specific contract: how Timescale is discovered, how it changes
the meaning of relational operations, and where its long work belongs.
Read alongside [contract.md](contract.md), [relations.md](relations.md),
[actions.md](actions.md), [connecting.md](connecting.md) and
[owned jobs](../jobs.md).

**Implementation status:** T1 inspection and protection, T2 bounded metadata
changes and T3 owned chunk operations are implemented. Every scenario runs
against each source of the matrix in
[compatibility/timescale](../../../backend/compatibility/timescale/README.md),
which pins Timescale 2.14 to 2.30 across PostgreSQL 14 to 18 and holds the
validation record. A release outside that matrix is neither certified nor
blocked: what a strategy can do there is decided by discovery (D120).

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
external plugin loader. The managed service template that starts the
extension's own image is exactly this: it produces an ordinary PostgreSQL
connector, and what that database holds is discovered while it is open, the
same as for a database that gains the extension later
([services](../services.md)). A Timescale-branded connection preset is not
part of the pilot.

Spec: [TimescaleDB through a PostgreSQL connection](../../decisions/2026-09-07-timescale-capabilities-design.md)

## D120. Runtime features complement static capabilities and grant no permission

D2/D13 still answer what a driver implements without opening a connection.
`SupportsSourceFeatures.source_features()` and the read-authorised
`GET /connectors/{id}/features` answer what this database exposes now. The
typed answer distinguishes `absent`, `available`, `unsupported` and `unavailable`,
with installed version and safe reasons. Unknown is not absent. An unavailable
optional view is not a failed PostgreSQL connection check.

The same answer carries what the server itself is running — the number and not
the sentence a driver hands over, which names the build, the distribution and
the compiler. A source with no optional features still has one, so Redis
answers too: "which server am I about to work on" is the same question
whatever the type, and it is asked at the moment a connection is checked.
That is where it is answered: a pressed check replies with the result and what
the source says about itself, while the monitor's rounds behind a coloured dot
stay exactly what they were (D19) — nothing there reads a version, and a second
query per connection per round would be a cost with no reader.

Detection selects implemented readers/actions from installed version and
verified public API shapes: schema, signature, function/procedure kind and
extension ownership where available. It neither calls mutating functions as
probes nor trusts a name found through `search_path`. Each implementation owns
its requirements, so support declarations cannot grow independently of code.

**A strategy asks for the arguments it passes, not for a release.** A shape
declares the leading arguments of one call; the routine must be owned by the
extension, live in its schema, return what the caller expects, take no variadic
argument, begin with exactly those argument types and give every further
argument a default. Nothing else is asked, and no list of tested version
strings is kept anywhere, so a release that appends an optional argument is
still recognised: `add_compression_policy` gained `hypercore_use_access_method`
in 2.18 and lost it again by 2.23, and `add_continuous_aggregate_policy` has had
seven, eight, ten and eleven arguments. Pinning whole signatures made every
unlisted release refuse with a reason that named no cause, which is worse than
a plain failure.

A routine no release of the installed version provides, or one this role may
not execute, refuses by name — "the TimescaleDB add_retention_policy API is not
usable by this connection". Where discovery itself already knows why a source
cannot be worked with, every strategy repeats that reason rather than replacing
it with a blanket one. The PostgreSQL major is not gated: the extension's own
public API is what the strategies call, and the matrix covers 14 to 18.

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
implemented; the user confirmed green checks after `482a537`. The interval
action is now registered, and its registration checks passed on 2026-09-11. PostgreSQL implements the optional
`ExplainsActionAvailability.action_offers(node_id)` protocol: one read returns
eligible actions and typed named refusals. Its ordinary `available(node_id)`
delegates to that same answer. The menu and execution use the source reason;
sources without this protocol retain the generic refusal. For multiple targets,
the first explicit refusal in request order explains a blocked selection; an
eligible destination still admits a destination workflow. Lookup stays a
registered action set.
No Timescale commands appear on a database without the extension. Static
vocabulary discovery raises an inspection error when extension status is
unavailable. Installed unsupported versions keep the interval command but its
live plan refuses execution. Interval admission uses a one-day read-only plan
for a user hypertable; actual preview validates the chosen duration separately.
Retention and compression policy commands are each admitted from one read-only
snapshot per hypertable; removal carries a reason when no policy exists, and
compression commands when compression is not enabled. Compressing and
decompressing chunks are admitted together from one more snapshot that
verifies the hypertable, enabled compression and both routines. A continuous
aggregate offers only refresh policy commands, admitted the same way. An ordinary user
table in a Timescale database is admitted for conversion behind the ordinary
relation guard; without Timescale, one catalog read settles it.
The ordinary relation guards remain independent of management admission. Static
action declarations carry typed feature requirements so the type catalog can
word conditional capabilities honestly. The default-empty tuple uses the closed
`FeatureCode` vocabulary. The server appends the installation condition to the
derived capability title, so the existing type catalog and search receive the
same wording without a second frontend feature-name table. This describes an
installation prerequisite, not verified mutation support or permission.
D118 target resolution and application
grants remain independent, and execution also faces PostgreSQL permissions.

Spec: [TimescaleDB through a PostgreSQL connection](../../decisions/2026-09-07-timescale-capabilities-design.md)

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

The Continuous aggregates report projects the fields every release in the
matrix shares. It omits the legacy `finalized` column, which 2.30 no longer
has, instead of requiring it or inventing a replacement value. Other projected
columns and extension ownership remain mandatory.

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

Spec: [TimescaleDB through a PostgreSQL connection](../../decisions/2026-09-07-timescale-capabilities-design.md)

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

Support is declared against public API strategies exercised on the pinned
matrix, which spans the rowstore, Hypercore and columnstore eras. Installed does
not mean every operation is supported, and a signature match alone never enables
a mutation.

Spec: [TimescaleDB through a PostgreSQL connection](../../decisions/2026-09-07-timescale-capabilities-design.md)

## D123. Long source actions are owned jobs with fixed targets and partial outcomes

A job-producing action implements `ProducesJob` (`adapters/operations.py`): it
plans a fixed `OperationPlan` of at most 1000 targets against a reviewed
fingerprint, carries out one target per source transaction and reads targets
back. `POST /connectors/{id}/actions/{name}/jobs` reuses the lookup,
availability and grant checks of an ordinary action (`connectors/action_lookup.py`),
draws the plan again, compares it with the review and answers 202 with the
job. `app.source_operations`, a layer above `jobs` and `connectors`, owns
admission, the typed durable payload, execution and restart recovery; adapters
never import it, and the import contracts say so. `ActionInfo.produces_job` is
derived from the protocol, and such an action always requires review.

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

Admission takes a transaction-scoped advisory
lock on the connector in the application database and refuses, with 409 and
the job's ID, while another source operation or a restore is unfinished there;
a restore is refused the same way while a source operation runs. The job
records the initiator, the required access, the action's form, the
connection's server-maintained `updated_at` as its revision, the plan's unit
fingerprint and every target as pending. Before the first unit and each later
one the handler reads the connection, its enabled state, that revision and the
owner's grant from a fresh session; a change stops the job before the next
target, says that committed work stays, and reads nothing more back. Target
outcomes are pending, running, completed, already, refused, rolled back and
unknown. Each is written to the row before the same named step is announced
again, and the read cache is invalidated after every unit whatever its outcome.
The first refusal or unknown outcome stops dispatch. A cancelled unit is read
back: unchanged is rolled back, as requested is completed, anything else stays
unknown. At startup, before D81's sweep, targets left running become unknown
and their connections' cached answers are dropped. Activity shows the action's
title, the counted targets with an outcome and those that need a look, and
re-reads a connection's data whenever a polled operation moves.

Chunk conversion is two such actions, Compress chunks and Decompress chunks,
on a time hypertable with compression enabled and a discovered `compress_chunk`
or `decompress_chunk`. The form is a window of instants with time zones; the
plan fixes the whole chunks inside it not yet stored as requested, in time
order, refuses more than 1000 and an empty selection, and counts those already
stored as requested. Its fingerprint covers the chunk list; a separate unit
fingerprint covers only the hypertable identity and the verified
`compress_chunk` or `decompress_chunk` of the installed version, so a unit can
tell that nothing but chunk states changed. Each unit runs at READ COMMITTED
with a five-second lock timeout and a fifteen-minute statement timeout,
re-resolves the chunk's membership in its parent by name, answers already when
it is stored as requested, and otherwise calls the routine with the bound chunk
OID and the if-not flag set. Lock waits and the statement timeout refuse; a
connection lost after the call was sent is unknown. A partially compressed
chunk counts as compressed.

Reading chunk states back pairs its two arrays with `ROWS FROM`: the
multi-argument form of `unnest` is a parser construct that cannot be
schema-qualified, and every function these statements name is qualified.

Known deviations: there is no retry command, so reviewing the same window
again is a new plan the person sees, which may include chunks created since.
Access revoked while a chunk converts does not stop that chunk. Populated-table
conversion is not part of T3 until it has a tested plan and locking strategy.

The first T2 plan model covers a future-chunk interval change. It records the
database/relation OIDs as decimal text, schema/name, time dimension and its
current interval, typed requested duration, extension version and exact API
identity. Its SHA-256 fingerprint covers the complete canonical JSON plan;
malformed fingerprints and changes to any field require renewed review.
It carries no credential, connector authority or execution admission. Duration
amounts are strict positive integers with a closed unit vocabulary; calendar
units remain calendar units. Models and staleness tests pass.
The interval model is used by the registered reviewed interval action.

The shared single-action transport now accepts an optional `reviewed_fingerprint`
separately from form parameters. `ActionPreview.fingerprint` carries the review
value; `ActionInfo.requires_plan_review` is derived from `RequiresReviewedPlan`.
Execution routes these actions only to `perform_reviewed`, after the ordinary
availability and grant checks, and refuses a missing fingerprint. The action
must re-plan and compare under its source execution boundary; the route never
treats the fingerprint as authority or checks staleness outside that boundary.
Existing actions keep their normal parameter transport. Backend transport tests
pass; the client was regenerated after this schema change.

The action form requires a successful unblocked fingerprint before submitting
an action marked for review, and sends it outside the form parameters. Parameter
changes immediately invalidate the displayed plan and in-flight replies; stale
replies cannot enable the button during the debounce. A refused execution keeps
the form open, clears its review and asks for a new plan without retrying the
mutation. Optional previews preserve their advisory behaviour. Component and
mapping tests pass, and a browser scenario covers the form's review contract.

The interval inspector has a five-second total budget and read-only statements.
It verifies public-view ownership/columns, resolves one owned
hypertable with one time dimension, excludes aggregate materializations, and
checks the extension-owned `set_chunk_time_interval(regclass, anyelement, name)`
function and execution privilege through the shared discovery above, without
calling it. Availability, not a version list, decides where it plans.
Integer dimensions, multiple dimensions, calendar intervals and subday intervals
for date columns are refused. Shared duration models preserve calendar units,
but this strategy does not offer them. There is no private catalog fallback.
Unit scenarios pass; isolated real-source planning scenarios passed
in the 2026-09-09 interval validation run and again on 2026-09-11. The
interval preview renderer now uses the shared ActionPreview transport with the
plan fingerprint, source-resolved quoted target, old/new interval and the
existing-chunk warning. Refused or failed inspection returns a blocked preview
without a fingerprint. The registered action uses this renderer.

Multi-query preview inspection now has a PostgreSQL read collaborator bound to
one repeatable-read, read-only transaction. Acquisition, reads and cleanup share
a five-second budget; each statement also has a source timeout. This keeps a
plan from combining committed metadata versions across separate connections.
The collaborator does not expose mutation methods. It is snapshot consistency,
not execution locking or mutation certification. Unit coverage passes.

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
passed on both pinned fixtures on 2026-09-09. The user subsequently confirmed
green checks after `482a537`; registration changes made afterwards passed on 2026-09-11.

The registered SetChunkInterval action connects the preview and execution
primitives to the existing reviewed transport, requires structure access and
resolves its target through the catalog. Plain execution refuses a missing
review; its parameter schema excludes calendar units. Source planning remains
the authoritative hypertable/ownership check. Isolated
mutation scenarios (future versus existing chunks, an external native setter,
stale review, source refusal, cancellation cleanup, lock permission and an
overload) passed on both pinned fixtures in the 36-test isolated interval run.
Unit coverage passes. The exact command and scope are recorded in the
[compatibility record](../../../backend/compatibility/timescale/README.md#t2-interval-execution-isolated-validation-2026-09-09).

Once reviewed execution has been dispatched, its route invalidates connector
reads on success, refusal, failure or cancellation. This conservatively covers
an uncertain commit without inferring source effects from error text. Preview,
missing-review and access refusal do not dispatch execution. Ordinary actions
retain their existing success-only invalidation. Route/helper tests pass.

Retention and compression policies are one family of reviewed actions over a
time hypertable: set (first or replacement) and remove, for each kind. The plan
fingerprints the kind, the extension-owned policy job (identity, schedule, pause
state and validated threshold), the exact add/remove API shapes of the
installed version and the public jobs view. Execution locks that view in SHARE
ROW EXCLUSIVE mode, which PostgreSQL extends to the job, job-statistics and
hypertable catalogs it reads, then ONLY the root; it replans, compares, and
removes and adds in one transaction, so a refused addition keeps the old
policy. A paused policy is never replaced, because its replacement would be
scheduled by default and resume it; it is removed first. Setting a retention
policy is destructive and its question names future automatic deletion;
compression and removals are not. A compression policy requires compression
already enabled on the hypertable. Thresholds run from hours to years, calendar
units kept; date dimensions take whole days. Integer dimensions, created-before
thresholds, custom schedules and aggregate targets are not offered. Unit and
isolated scenarios passed on 2026-09-11.

Refresh policies are set, replaced and removed on an existing continuous
aggregate by two more reviewed actions; there is no aggregate editor. The job
belongs to the materialization hypertable and execution locks the jobs view and
ONLY that materialization before the same replan, compare, remove and add
transaction. The public jobs view, though, names the materialization only up to
2.19 and the user view from a later release on, so the plan looks for the job
under either identity; reading it under one alone made a newly added policy
invisible on the newer releases and the next set refuse as a duplicate. The window is a start offset, an
end offset and a schedule, each a positive bounded duration. PostgreSQL
compares them: the window must start further back than it ends, and must start
more recently than the source hypertable's age-based retention threshold,
because refreshing where raw data was dropped removes aggregated rows. A
creation-time retention threshold cannot be compared and is disclosed instead.
The source's retention job is part of the fingerprint. The source still
refuses a window smaller than two buckets at execution. Unit and isolated
scenarios passed on 2026-09-11.

Compression settings on a time hypertable are one reviewed action that enables
compression or changes its segment-by and order-by lists; it compresses
nothing, and disabling is not offered. The form takes one column per line, with
an optional ASC or DESC and NULLS FIRST or LAST for ordering. Each name must be
a live column of the table; a column listed twice, or in both lists, is
refused. Execution first locks ONLY the root in ACCESS EXCLUSIVE mode — the lock
ALTER TABLE takes anyway — under the two-second lock timeout, replans, compares
and issues one ALTER TABLE with both lists explicit, composed from quoted
identifiers and fixed keywords, so the source neither keeps an old list nor
derives a default. The plan appends the time column descending, nulls first,
when neither list names it, as the source would. Already compressed chunks keep
their own settings, which the preview says; unique-key columns in neither list
are disclosed on first enabling, where the source only warns. Unit and isolated
scenarios passed on 2026-09-11.

Converting an ordinary table into a hypertable is offered for an empty, logged
user table the connection owns, and keeps its node ID. Admission and the plan
name the source's own refusals first — partitioning, NO INHERIT check constraints,
inheritance, persistence, rules, an existing hypertable, foreign keys to or
from a hypertable, no timestamp or date column, rows. The plan then checks the
chosen column: every unique or exclusion index must include it, date columns
take whole days and calendar intervals are refused. Execution first locks ONLY
the table in ACCESS EXCLUSIVE mode, replans so emptiness is read under the
lock, compares and calls the dimension-based `create_hypertable` with
`by_range`, default indexes on and data migration off. The preview says that a
nullable time column becomes NOT NULL and whether the source adds its time
index, by the source's rule that only a one-column index on the time column
counts. Populated tables wait for T3's owned jobs. Unit and isolated scenarios
passed on 2026-09-11.

Spec: [TimescaleDB through a PostgreSQL connection](../../decisions/2026-09-07-timescale-capabilities-design.md)
