# TimescaleDB in a PostgreSQL connection

The extension-specific contract: how Timescale is discovered, how it changes
the meaning of relational operations, and where its long work belongs.
Read alongside [contract.md](contract.md), [relations.md](relations.md),
[actions.md](actions.md), [connecting.md](connecting.md) and
[owned jobs](../jobs.md).

**Implementation status:** these are design decisions for review. No Timescale
feature is implemented or verified by their publication. T1 in the linked spec
is the read-only pilot; T2 adds bounded changes and T3 adds owned operations.
The [roadmap](../../migration-roadmap.md) tracks delivery.

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

When Timescale actions arrive, `SupportsActions.all_actions()` becomes async
and returns this connection's vocabulary. `available(node_id)` supplies
per-node applicability and its reason; lookup stays a registered action set.
No Timescale commands appear on a database without the extension. Static
action declarations carry typed feature requirements so the type catalog can
word conditional capabilities honestly. D118 target resolution and application
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

Root relation size/row statistics are not presented as whole-hypertable totals.
Unavailable totals stay null; on-demand statistics use public APIs and a
five-second inspection timeout. Time boundaries and integer boundaries are
different shapes, with large integers carried losslessly as decimal strings.
Private Timescale catalogs are not an inaccessible-view fallback.

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

Spec: [TimescaleDB through a PostgreSQL connection](../../superpowers/specs/2026-09-07-timescale-capabilities-design.md)
