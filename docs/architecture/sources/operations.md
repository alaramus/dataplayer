# Long source actions that run as jobs

A source action over many targets that cannot finish inside a request: how its
plan is fixed and reviewed, how each target's outcome is recorded, and what a
restart leaves behind. What a job is at all is in [../jobs.md](../jobs.md);
what an ordinary action is, in [actions.md](actions.md). Every worked example
here is Timescale's, whose contract is in [timescale.md](timescale.md).

Decisions here: D123.

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
overload) passed on both pinned fixtures in the 36-test isolated interval run. The exact command and scope are recorded in the
[compatibility record](../../../backend/compatibility/timescale/README.md#validation-record-2026-09-12).

Once reviewed execution has been dispatched, its route invalidates connector
reads on success, refusal, failure or cancellation. This conservatively covers
an uncertain commit without inferring source effects from error text. Preview,
missing-review and access refusal do not dispatch execution. Ordinary actions
retain their existing success-only invalidation.

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
refuses a window smaller than two buckets at execution.

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
are disclosed on first enabling, where the source only warns.

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
counts. Populated tables wait for T3's owned jobs.

Spec: [TimescaleDB through a PostgreSQL connection](../../decisions/2026-09-07-timescale-capabilities-design.md)
