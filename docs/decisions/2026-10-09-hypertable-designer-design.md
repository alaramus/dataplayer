# Designing a hypertable

Date: 2026-10-09. Decisions: D207, D208. Extends D117, D120, D122 and D123.

Status: agreed on 2026-10-09, not implemented. The answers to the open
questions are under [Settled](#settled). The statements are in
[timescale.md](../architecture/sources/timescale.md).

## The problem

A hypertable is configured by eleven separate actions: convert, chunk interval,
compression settings, retention and compression policies (set and remove each),
refresh policies, compress and decompress chunks. Each is right for one change.
None of them shows the hypertable as a whole. Setting up a new one means opening
four or five dialogs in an order the person has to know: convert first, enable
compression before a compression policy, and so on.

A table cannot be created as a hypertable at all. The table designer (D117)
creates an ordinary table, and conversion is a second step afterwards.

Several things the old application could do have no counterpart yet: extra
dimensions, integer time, reorder policies, tablespaces, and chunk drop, merge,
split, move, detach and attach.

## What the old application did

`dbwebtool/webdb/data_adapter/timescale/` and the `TimescaleHypertableEditor`
in `myquasar`. Ported here as ideas, not code.

- **One editor, two modes.** "Convert to hypertable" opened a form with these
  parts: time column, chunk interval, "Partition by" rows (hash, range,
  custom), compression with an age, retention with an age, `migrate_data` and
  dry run. "Update/Info hypertable" opened the same form with the time column
  and interval read-only, plus a statistics tab. This is the idea worth
  keeping: one picture of the hypertable, edited as a whole.
- **Integer time** was supported. A chunk size was proposed by the integer
  type. For retention, an `integer_now` function could be named or created
  automatically.
- **Chunk operations** came from the chunk list. They were drop by range,
  compress, decompress, merge, split (also at a selected row), detach, move to
  a tablespace, and attach a detached chunk. A separate catalog entry listed
  detached chunks.
- **Tablespaces** could be created, dropped, attached to a hypertable and listed.
- **Extensions** could be installed and removed from a list of available ones.

What it got wrong, and must not be carried over:

- Every step ran with no transaction and continued after a failure.
- SQL was built by string formatting with unquoted identifiers.
- Dry run only listed the SQL. The result dialog let the person edit a step's
  SQL and run it again, which is raw SQL from the client (D2c).
- The same value served as both the compression age and
  `compress_chunk_time_interval`.
- Retention was added even when its box was unchecked.
- Unchecking a policy never removed it.
- The "custom" dimension called `by_range` with a hash function, and the
  generated hash function referenced an undefined variable.
- `disable_chunk_skipping` lacked its column, and `attach_chunk` was sent the
  string `'None'` as its slices.
- "Reorder" had no backend.
- "Recompression policy" called a function Timescale never had.
- "Compress all" passed chunk names without their schema.

## What the releases disagree about

Read from `sql/ddl_api.sql`, `sql/policy_api.sql` and `sql/maintenance_utils.sql`
at tags 2.14.2, 2.17.2, 2.18.0, 2.19.3, 2.23.1 and 2.30.0 (the
[matrix](../../backend/compatibility/timescale/README.md)), and from
`CHANGELOG.md` at 2.30.0. Read on 2026-10-09.

| API | Where it exists | Note |
| --- | --- | --- |
| `create_hypertable(regclass, dimension_info, create_default_indexes, if_not_exists, migrate_data)` with `by_range` / `by_hash` | the whole matrix (since 2.13) | The old positional form is still present in 2.30. |
| `add_dimension(regclass, dimension_info, if_not_exists)` | whole matrix | Only on an empty hypertable. Timescale's own advice is not to use extra dimensions. |
| `set_chunk_time_interval`, `set_partitioning_interval`, `set_number_partitions`, `set_integer_now_func` | whole matrix | |
| `attach_tablespace`, `detach_tablespace(s)`, `show_tablespaces` | whole matrix | They affect only future chunks. |
| `add_reorder_policy`, `reorder_chunk`, `move_chunk` | whole matrix | TSL license, so an Apache-only build lacks them. Shape discovery already says so. |
| `add_retention_policy`, `add_compression_policy` | whole matrix, signatures stable | |
| `add_columnstore_policy`, `convert_to_columnstore`, `convert_to_rowstore`, `*_columnstore_*` views | 2.18+ | The older names are deprecated "for the next major" but still work in 2.30. |
| `ALTER TABLE SET (timescaledb.compress, compress_segmentby, compress_orderby, compress_chunk_time_interval)` | whole matrix | `enable_columnstore`, `segmentby` and `orderby` are aliases from 2.18 and 2.20. |
| Hypercore table access method | 2.18–2.21 only | Removed in 2.22. |
| `merge_chunks` | 2.18+ | |
| `split_chunk` | 2.20+ | |
| `CREATE TABLE … WITH (tsdb.hypertable, …)` | 2.20+ | Implicitly adds a columnstore policy from 2.23. |
| `attach_chunk`, `detach_chunk` | 2.21+ | Uncompressed chunks only. |
| `timescaledb.sparse_index` option (minmax, bloom) | 2.22+ | `hypertable_columnstore_settings` gains an `index` column. |
| `ALTER TABLE RESET` for `orderby` | 2.22.1+ | |
| Partitioning by UUIDv7 | 2.22+ | Retention on it from 2.25. |
| `enable_chunk_skipping`, `disable_chunk_skipping` | 2.16+ | Experimental, behind the `timescaledb.enable_chunk_skipping` GUC. |
| `add_compaction_policy`, `merge_chunks_concurrently` | 2.29+ | |
| Automatic segmentby/orderby defaults per chunk; an empty string means "none" | improved from 2.20 | |
| PostgreSQL 14 | up to 2.19 | |
| PostgreSQL 15 | up to 2.28 | |

The matrix already found that a strategy should ask for the arguments it passes,
not for a release (D120). This holds for routines. Two things here have no
routine to inspect: an `ALTER TABLE` storage option and the column types a
dimension accepts. For those the strategy declares a minimum extension release
beside itself. The matrix must hold a source on each side of that boundary, so a
wrong boundary goes red.

## D207. A hypertable is designed as a whole and planned as one change

One closed model, `HypertableDesign`, describes what the hypertable should be.
It serves two entry points:

- **Creation.** The table designer gains a Hypertable section beside Storage &
  partitioning. It is offered when discovery says the extension is available
  in the destination database. The design travels inside `TableDefinition` as
  an optional field. `create_table` stays the action (D117).
- **An existing table.** A new action, `timescale_design_hypertable`, is
  "Hypertable settings…". It applies to a user table, whether ordinary or
  already a hypertable. It opens with the current state read into the same
  model. For an ordinary table, the current state is "not a hypertable", so
  the first change in the plan is the conversion.

The server compares the requested design with the current state. It composes a
plan that holds only the differences, in a fixed order:

1. conversion;
2. dimensions;
3. intervals;
4. columnstore settings;
5. tablespaces;
6. policies to remove;
7. policies to add.

The existing composers (`interval_plan`, `compression_settings_plan`,
`age_policy_plan`, `conversion_plan`) produce their parts. Nothing is written
twice. The person reviews the whole plan, and it applies in one transaction
under the union of the parts' locks. A part that is refused refuses the plan,
and its problem names the object in the model the editor should select. This
is the same contract D117 uses for columns.

### The model

Every field is optional, so a payload from an older client still validates.
Columns are referred to by draft id at creation and by attribute number on an
existing table, so renaming a column in the designer changes nothing here.

- **Time dimension**: a column and an interval. The interval is a
  `TimeDuration` for `timestamp`, `timestamptz` and `date`. For `smallint`,
  `integer` and `bigint` it is an integer carried as a decimal string. The
  proposed default follows the old application: 10 000, 100 000 and 1 000 000.
  A date column needs a day or a week. On an existing hypertable the column is
  read-only, because Timescale cannot change it.
- **Integer now**: needed for age policies on an integer time column. It is
  either chosen from the functions the server offers (no arguments, returning
  the column's type, stable or immutable, executable by the role), or created
  from a closed template: seconds, milliseconds or microseconds since the
  epoch, cast to the column's type. The template's body is the server's. The
  person picks the template and the name, and the plan shows the
  `CREATE FUNCTION` before it runs.
- **Hash dimensions**: a column and a partition count, up to the limit
  `by_hash` accepts. They can be added only while the hypertable is empty,
  which Timescale requires. The count of an existing one can be changed through
  `set_number_partitions`. A dimension cannot be removed, so the editor shows
  existing ones without a delete. The editor states Timescale's advice against
  extra dimensions; it does not hide them.
- **Columnstore**: off or on. When on, `segment_by` and `order_by` each have
  three states:
  - *Timescale chooses*: the option is not set, or is `RESET` where the release
    supports it.
  - *None*: an empty string.
  - *These columns*: an ordered list. For `order_by`, each column has a
    direction and null placement.

  The three states exist because, from 2.20, an unset option and an empty one
  mean different things.

  The model also holds:
  - `merge_interval`: `compress_chunk_time_interval`, separate from any
    policy's age;
  - `sparse_indexes`: minmax or bloom per column, offered only where the
    settings view has its `index` column.

  Turning the columnstore off is offered only while no chunk is compressed and
  no columnstore policy exists. Otherwise the reason is shown.
- **Policies**: retention age, columnstore age and reorder index. An age is
  either "older than" or "created before", with the same validation as the
  existing actions. A policy left empty in the design and present in the source
  is removed. That is the difference from the old editor, where unchecking did
  nothing. The retention preview keeps its warning that Timescale will delete
  data later, on its own schedule.
- **Tablespaces**: the attached tablespaces. Only existing tablespaces are
  listed, and the editor says this affects only chunks created later.

### Rules the server states

These sit beside D117's partition rule, in the same checker:

- The primary key and every unique constraint must contain the time column and
  every hash column.
- The time column must require a value.
- A hypertable cannot also use PostgreSQL declarative partitioning, so the two
  options exclude each other in the designer.
- A hypertable cannot be unlogged.
- A foreign key between two hypertables is refused. A key from an ordinary
  table to a hypertable is allowed where discovery finds the release accepts it.
- `segment_by` and `order_by` cannot name the same column. Neither can name a
  column whose type has no comparison operator.

At creation, `create_default_indexes` is false. Instead, the designer adds a
visible draft index on the time column, descending. The person can delete it,
so every index is one somebody can see before it exists.

### Strategy

Creation and conversion call `create_hypertable(regclass, by_range(...))`, which
exists on every release in the matrix. Dimensions use `add_dimension(regclass,
by_hash(...))`. The columnstore uses the `ALTER TABLE` options the existing
settings action already uses; they work through 2.30.

`CREATE TABLE … WITH (tsdb.hypertable)` was considered and rejected:

- It exists only from 2.20.
- From 2.23 it silently adds a columnstore policy that the plan did not show.
- It picks the partition column itself when none is named.

One strategy across the matrix is also one code path to test.

### Transactions and long work

Everything except migrating rows is metadata. It applies in one transaction
with the existing timeouts and lock order, through `run_reviewed`.

Converting a table that has rows calls `create_hypertable` with
`migrate_data => true`. This is the populated-table conversion deferred in the
2026-09-07 spec. It runs as an owned job (D123) with exactly one unit. The
unit's transaction holds the conversion and the rest of the design, so a
failure leaves the ordinary table as it was. The plan shows:

- the estimated rows and size;
- that the table is locked against reads and writes until the job ends;
- that the job cannot be cancelled halfway.

The statement timeout for that unit is a setting in `.env.example`, with a
default of one hour. A unit that runs out of time rolls back and is reported as
rolled back, not unknown.

### What stays as it is

The eleven existing actions stay. They are quick for a single change, and the
agent uses them as tools. The context menu groups them under a "Timescale"
submenu, with "Hypertable settings…" first. Compressing and decompressing chunks
are data operations, not settings. They stay outside the editor, as does
everything in D208.

The existing target resolvers accept only a single time dimension. The
editor's current-state reader must read every dimension, including hash and
integer ones. The old actions keep their narrower targets, and refuse a
hypertable they do not understand, until they are moved onto the shared
reader.

## D208. Chunk maintenance is a reviewed job over a fixed set of chunks

Drop, merge, split, move, reorder, detach and attach are offered from a
selection in the Chunks report, and from the hypertable's Timescale submenu
with a time window. Each one follows the compress/decompress pattern:

- an action registered under its own name;
- a plan that fixes the actual chunks;
- a unit per chunk, or per group for a merge;
- outcomes per unit under D123.

| Operation | Strategy | Release | Note |
| --- | --- | --- | --- |
| Drop chunks | Each unit drops exactly the chunk it names, re-resolved as a member of the parent. | whole matrix | Destructive, asks first. The plan lists every chunk and its range, never "older than X" evaluated later. |
| Merge chunks | `merge_chunks` over the chunks in the selection | 2.18+ | The chunks must be adjacent in the time dimension. One unit per merge group. |
| Split a chunk | `split_chunk`, optionally at a point | 2.20+ | The point may come from a selected row's time value, as in the old app. |
| Move to a tablespace | `move_chunk`, optionally with an index tablespace and a reorder index | whole matrix, TSL | |
| Reorder | `reorder_chunk` by an index of the hypertable | whole matrix, TSL | |
| Detach | `detach_chunk` | 2.21+ | Uncompressed chunks only. The chunk becomes an ordinary table in its schema. |
| Attach | `attach_chunk(hypertable, chunk, slices)` | 2.21+ | The slices come from a form of typed bounds per dimension, never from text. |

A "Detached chunks" report lists ordinary tables that carry a former chunk's
name and constraints. The old application's way of finding them, matching a
`_hyper_%_chunk` name against the private catalog, reads private catalogs. That
is ruled out by D121. The report instead reads only public views and
`pg_class`, and accepts that it is a guess: it offers attach, it never asserts.

Chunk skipping is a column setting. It goes in D207's model, behind the GUC
check, not here.

## Slices

Each slice is planned, implemented, tested on the whole matrix and committed
before the next. Every slice adds its scenarios to
`backend/compatibility/timescale` and runs on all seven sources.

- **H1 — the model and the current-state reader.** `HypertableDesign`, the
  reader of every dimension, columnstore settings with the three states,
  policies and tablespaces, and the diff. Nothing is written yet.
- **H2 — Hypertable settings on an existing hypertable.**
  - Changes: interval, partition count, columnstore, merge interval, policies
    including reorder, tablespaces. One reviewed plan, one transaction.
  - The context submenu.
- **H3 — conversion from the editor.** An empty table in the same transaction.
  A table with rows as a one-unit job.
- **H4 — creation in the table designer.** The Hypertable section, the key
  rules, the visible default index, hash dimensions at birth.
- **H5 — integer time.** Integer intervals, `integer_now`, integer ages on
  policies.
- **H6 — chunk maintenance (D208).** Drop, merge, split, move, reorder,
  detach, attach, and the Detached chunks report.
- **H7 — release-bounded options.** Sparse indexes (2.22+), chunk skipping
  (2.16+ with the GUC), UUIDv7 time (2.22+), compaction policy (2.29+). Each
  declares its minimum release and is proven on both sides of it.

E2E: the existing Timescale scenarios mock the server. The designer and the
settings editor each get one scenario against a real source, the 2.30/PG18
service of the compatibility compose. It skips when that service is not running,
like Redis and SSH.

## Deliberately outside

- **Editing a step's SQL, or running the plan "anyway" past a refused part.**
  The plan is composed by the server and approved, not edited (D2c, D117).
- **Creating functions from text.** No hash or `integer_now` body is typed by
  the person. The `integer_now` templates are the only functions the editor
  creates. A custom hash function is not offered: Timescale's own is correct,
  and the old application's was broken.
- **Continuous aggregate definitions.** Creating one is a view designer, not a
  table designer. The old application never had one either.
- **Data tiering, Toolkit, distributed hypertables.**
- **Tablespace creation and removal, and extension install and removal.** They
  are not Timescale features: they belong to PostgreSQL administration, and a
  tablespace names a directory on the database server. They get a spec of
  their own. Attaching an existing tablespace to a hypertable is Timescale's
  API and stays in D207.

## Rejected

- **One dialog that runs the existing actions in a row.** Each action has its
  own transaction, so a failure midway would leave half a configuration. That
  was the old application's main fault.
- **`CREATE TABLE … WITH`** for creation. See the D207 strategy above.
- **Removing the single actions once the editor exists.** They are the right
  size for one change and for the agent.
- **Version lists for routines.** Already rejected in D120. Only the two kinds
  of capability with no routine to inspect declare a minimum release.

## Settled

Answered by the user on 2026-10-09.

1. **Order of delivery.** The settings editor comes first: H1 and H2, then H3,
   then H4. H2 cannot exist without H1's model and reader, so they ship
   together.
2. **Creating an `integer_now` function.** Allowed from the closed templates
   described in D207's model. This narrows the 2026-09-07 rule "no automatic
   SQL-function creation": no body is ever typed or generated from the
   person's text, and the statement is in the reviewed plan.
3. **Tablespaces and extensions.** Creating and dropping tablespaces, and
   installing and removing extensions, get a separate spec as PostgreSQL
   administration. It is not written yet.

Still open, to be decided when H7 is planned: whether `merge_chunks_concurrently`
and the compaction policy (2.29+) belong in it, or wait for a need.
