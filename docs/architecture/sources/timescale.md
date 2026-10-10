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

Decisions here: D119, D120, D121, D122, D207, D208.

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

## D207. A hypertable is designed as a whole and planned as one change

Every slice is implemented and passes the whole matrix: the settings editor
(H1, H2), conversion from it (H3), the table designer's Hypertable section
(H4), integer time (H5) and the options only some releases have (H7).

One closed model, `HypertableDesign`, says what a hypertable should be:

- the time dimension and its interval, time or integer;
- `integer_now`, chosen from the source's functions or created from a closed
  template whose body is the server's;
- hash dimensions;
- the columnstore, where `segment_by` and `order_by` are each "Timescale
  chooses", "none" or an ordered list, plus a merge interval separate from any
  policy's age and, from 2.22, sparse indexes;
- retention, columnstore and reorder policies;
- attached tablespaces.

The model serves two entry points:

- the table designer's Hypertable section, inside `TableDefinition` (D117);
- the `timescale_design_hypertable` action, "Hypertable settings…", on an
  ordinary table or a hypertable.

The server reads the current state into the same model and plans only the
differences, in a fixed order, through the existing per-domain composers. A
policy left empty in the design is removed. The person reviews one plan, and it
applies in one transaction under the union of the parts' locks.

A table with rows is converted with `migrate_data` as a one-unit owned job
(D123). The conversion and the rest of the design are in that unit's
transaction. Its statement timeout is a setting.

The server enforces these rules:

- keys contain the time column and every hash column;
- the time column requires a value;
- the table is not unlogged and not declaratively partitioned;
- a hash dimension is added only to an empty hypertable, and none is removed.

At creation, `create_default_indexes` is false and the designer proposes a
visible time index instead.

Creation and conversion use `create_hypertable` with `by_range`, which exists
on every release in the matrix. `CREATE TABLE … WITH (tsdb.hypertable)` is not
used: it exists only from 2.20, adds an unplanned columnstore policy from 2.23,
and picks the column itself. Some things have no routine to inspect: a storage
option, and which column types a dimension accepts. Their strategy declares a
minimum release, and the matrix keeps a source on each side of it.

The eleven single-purpose actions remain and are grouped in a Timescale
submenu. An action names its submenu in `menu_group`, so the client groups
lines without a list of action names. Compressing and decompressing chunks
stay outside the editor.

What the matrix showed, and the code follows:

- Before 2.20 an `ALTER TABLE` that leaves a columnstore list out derives a
  default for it again. Changing only the merge interval once produced a
  segment column that was already an order column, and the source refused. So
  every columnstore change states both lists whole, in one statement.
- `RESET` of a columnstore list is refused before 2.22.1, and an unset list and
  an empty one read alike there. "Timescale chooses" is therefore offered after
  enabling only from 2.22.1, a minimum the matrix proves on 2.19.3 and 2.23.1.
- The text views join column names with commas without quoting them, so the
  lists are read from the per-column `compression_settings` view, deprecated
  but present in every release of the matrix.
- A policy runs at once when it is added. Scenarios use ages far beyond their
  rows, or the job drops or compresses chunks under the test.
- An integer column's lengths are counts, carried as decimal strings and cast
  to bigint; Timescale checks a chunk interval against the column's type but
  accepts a policy age past it, so the planner checks both.
- `timescaledb_information.dimensions` names `integer_now` without its schema,
  and the function can be dropped while a hypertable still names it. The
  reader names it only when one zero-argument function of that name and type
  exists, and keeps it as it is otherwise. A template's function must have a
  name no other zero-argument function has, so it reads back by name.
- Timescale reads `compress_chunk_time_interval` as time even on an integer
  column. The editor offers no merge interval there, and refuses a hypertable
  that has one.
- Sparse indexes are offered where the settings view has its `index` column,
  which is discovery rather than a release. The view lists Timescale's own
  indexes beside the ones that were set; only those whose source is `config`
  are the design's, an empty `config` entry is "none", and none at all is
  "Timescale chooses". Timescale refuses sparse indexes without a named order,
  and so does the planner.
- UUIDv7 partitioning exists from 2.22, but until 2.25 the views report its
  interval in microseconds and its chunks without a range. A UUID time column
  is offered from 2.25, a declared minimum the matrix proves on 2.23.1 and
  2.30.0, and an older one is refused saying so.
- The compaction policy (2.29) needs the columnstore on, and
  `merge_chunks_concurrently` refuses a transaction block like a move; both
  are found by discovery.

Conversion from the editor plans an ordinary table as the hypertable it would
become by the chosen column, so the conversion and every setting after it are
planned by the same rules as an existing hypertable's. An empty table converts
in the request's transaction. A table with rows makes the preview say
`runs_as_job`, and the editor starts the job instead of applying: one unit,
whose transaction holds the conversion with `migrate_data` and the rest of the
design, under `TIMESCALE_CONVERSION_TIMEOUT_SECONDS`. A row with no time fails
the whole conversion and leaves the table as it was.

The table designer's Hypertable section names columns and the reorder index by
draft id, in `TableDefinition.hypertable`. The new table is planned as the empty
hypertable `create_hypertable` would make of it, through the same step planner,
and the steps are rendered as statement text for the review, after the table
and its indexes; the fingerprint covers them like every other statement (D117).
The designer adds the time index, newest first, as one of the draft's indexes
unless a key or index already leads with the time column, which is the rule
TimescaleDB applies to its own default index.

Known deviations:

- **The designer attaches no tablespace and keeps nothing as it is.** A new
  table has nothing to keep, and the designer places no table in a tablespace
  (D117).
- **A conversion that runs out of time is reported as refused,** with a message
  saying it was rolled back. The spec asked for the job's "rolled back" outcome,
  which the job handler gives only to a cancelled unit.
- **The order of steps differs from the spec.** Policy removals come before the
  columnstore changes rather than after the tablespaces, because a columnstore
  cannot be turned off while its policy exists.
- **Columns of an existing table are named, not numbered.** The spec said
  attribute numbers. A name is checked against the table when planning, and a
  rename between review and apply changes the fingerprint.
- **A refusal is one sentence of the preview.** The table designer attributes
  each problem to an object; this editor does not yet.
- **Releases 2.20 to 2.22.0 are read as the older ones.** None of them is in the
  matrix, so an unset list there is shown as "none".
- **`integer_now` cannot be taken away.** Timescale has no call that unsets it,
  so the editor keeps it or replaces it.
- **Chunk skipping is two actions, not part of the design.** Which columns
  record their ranges is kept only in a private catalog (D121), so the editor
  could not say what is set. "Skip chunks by a column" and "Stop skipping
  chunks by a column" call Timescale with `if_not_exists`, so asking for what
  already holds changes nothing, and set `timescaledb.enable_chunk_skipping`
  for their own transaction; the preview says when it is off for queries.
- **The designer never proposes an integer time column.** It proposes a
  timestamp or date column; an integer one is chosen by hand, since an `id`
  column is as likely as a clock.

Spec: [Designing a hypertable](../../decisions/2026-10-09-hypertable-designer-design.md)

## D208. Chunk maintenance is a reviewed job over a fixed set of chunks

Implemented (H6) and passing the whole matrix, over time and integer columns,
with hash dimensions beside them.

Drop, merge (2.18+; letting reads go on, 2.29+), split (2.20+), move,
reorder, detach and attach (2.21+) each work like compressing chunks:

- a registered action;
- a plan that fixes the actual chunks and their ranges;
- a unit per chunk, or per merge group;
- an outcome per unit (D123).

A drop never re-evaluates an age threshold at execution. Attach takes typed
bounds per dimension. A window, a split point and an attach range are instants
on a hypertable over time and values of the column on one over an integer
column; one field type takes both, the plan refuses the wrong kind, and the form
learns which it is from the action's field hints ([D9](actions.md)). A Detached chunks report reads public views and
`pg_class`, never private catalogs, so it offers attach without asserting
anything.

Each is an action in the hypertable's Timescale submenu, over a window of
whole chunks like compressing; a split takes the instant to split at, and an
attach the table and the range it is to cover. A merge, a split and an attach
are one unit, and the unit carries the exact chunks, point or bounds it was
reviewed with, so a source that changed between review and run refuses it.

What the matrix showed, and the code follows:

- `move_chunk` and `reorder_chunk` refuse a transaction block. Their unit is
  checked in a transaction and then sent with none, the way VACUUM runs
  (D206). `move_chunk` also refuses a chunk with no clustered index, so a move
  names an index, the one on the time column unless the person names another.
- `merge_chunks` merges compressed chunks from 2.19, which has no routine to
  inspect: the minimum is declared, and the matrix proves it on 2.18.0 and
  2.19.3. `split_chunk`, `detach_chunk` and `attach_chunk` are found by
  discovery; a release without them says the API is not usable.
- `detach_chunk` refuses a compressed chunk, and a detached chunk keeps its
  name but none of its constraints. The report therefore matches by name
  alone.
- A drop is `DROP TABLE` on the chunk, re-resolved as a member of the parent
  for every unit; it drops a compressed chunk as well.

Known deviations:

- **Not offered from a selection in the Chunks report.** A report row offers
  only commands that run at once (D70), and these are reviewed first; the
  submenu's window chooses the same whole chunks.
- **No merge, attach or split beside hash dimensions.** Which hash partition
  a chunk is in is not in the public views, so neither a merge nor an attach
  could be checked first; TimescaleDB itself refuses to split a chunk of a
  hypertable with more than one dimension. Drop, move, reorder and detach take
  each partition's chunk by name. A second range dimension is not maintained.
- **Compressing keeps the narrower target.** Converting chunks to and from the
  columnstore still takes a hypertable with one time dimension.
- **A reorder is never read back as done.** No public view tells a reordered
  chunk apart, so an interrupted one is read as not done; doing it again is
  harmless.
- **A split takes a point, not "the middle".** The point is typed, not taken
  from a selected row.

Spec: [Designing a hypertable](../../decisions/2026-10-09-hypertable-designer-design.md)
