# TimescaleDB in a PostgreSQL connection

The extension-specific contract: how Timescale is discovered and how it changes
the meaning of relational operations. Its long work — chunk conversion,
policies, compression settings and conversion to a hypertable — runs as owned
jobs and is in [operations.md](operations.md). Read alongside
[contract.md](contract.md), [relations.md](relations.md),
[actions.md](actions.md) and [connecting.md](connecting.md).

Every scenario runs against each source of the matrix in
[compatibility/timescale](../../../backend/compatibility/timescale/README.md),
which pins Timescale 2.14 to 2.30 across PostgreSQL 14 to 18 and holds the
validation record. A release outside that matrix is neither certified nor
blocked: what a strategy can do there is decided by discovery (D120).

Decisions here: D119, D120, D121, D122.

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
