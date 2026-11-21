# DuckDB

What a DuckDB source is, how it opens its file and locks the engine to the
owner's storage, how it reads its catalog, how its values and pages cross
to the grid and how its rows are changed there, how its structure is changed and
tables designed, what it reports, how it is searched and exported, what its
catalog can be asked to do, how its tables are copied and the file backed up,
its lab, a DuckDB file seen from a file source and one made here, and how its
SQL console differs from PostgreSQL's. The contract every source type follows is in
[contract.md](contract.md); reading a relation in general is in
[relations.md](relations.md); the other DuckDB in the server, the sandbox
behind SQL over files, is in [file-sql.md](file-sql.md). Read this before
changing the `duckdb` adapter.

Decisions here: D387, D388, D389, D390, D391, D392, D393, D394, D395, D396, D397, D398, D399, D400, D401, D402, D403, D404.

## D387. A DuckDB source is one file of its owner's storage, opened per call

The only option is a path below the owner's home, judged by the file source's
own containment rule (D8) on every open, symlinks followed — the rule SQLite's
source uses, in `adapters/home_file.py`. A missing file fails the check
unless **Create the file if it is missing** is ticked, and is then made only
in a folder that exists.

Every call opens the file in a worker thread, works and closes it. A file
held open by this process could not be opened at all by any other program,
and a second open in this process with another configuration is refused, so
nothing keeps it. Calls that overlap share DuckDB's instance, opened with one
fixed configuration. A file another program holds is `locked`, not a wait. A
request that goes away, and a clock that runs out, interrupt the statement
through the connection.

A file DuckDB cannot read, a SQLite file included, is a configuration failure
saying so; so is a path DuckDB opens as an empty database in memory, which it
does for `.csv` and `.parquet`. Driver text never reaches the caller: it names
the server's paths. `duckdb` is imported by this package and the file
explorer's sandbox alone (`lint-imports`).

Known deviations:

- A file on an SSH server or inside another connection cannot be opened.

Spec: [A DuckDB source](../../decisions/2026-11-20-duckdb-source-design.md)

## D388. The engine is locked to the owner's storage

Before anything of the file runs, the instance is given the owner's home as
`home_directory` and as its one allowed directory, the network filesystems
are disabled, external access is switched off and the configuration locked.
Extensions are neither installed nor loaded automatically, and the extension
directory lies outside every allowed one, because `INSTALL` downloads whatever
external access says. There is no temp directory, memory and threads are
bounded, and the time zone is UTC. A file of the home is named `~/…`; a
relative path is refused.

This is the engine's containment rather than D8's: what it is asked to contain
is DuckDB's own SQL over the person's files, where a path is any string any
function takes. The server never makes a symbolic link in a home, so the
engine's prefix check and D8's symlink-following one judge the same tree.

Known deviations:

- A link put into a home by an operator would be followed by the engine.
- `glob('~/**')` and a reader's `filename` column return the server's path of
  the home.
- `COPY … TO` and `ATTACH` would write inside the home; no client SQL runs
  until the console, which refuses them by class.

Spec: [A DuckDB source](../../decisions/2026-11-20-duckdb-source-design.md)

## D389. Schemas and relations come from DuckDB's catalog functions

The first level is the file's schemas, `main` among them; the `system` and
`temp` databases are the engine's and are not listed. Relations are the
non-internal tables and views, with `estimated_size` as a table's estimate.
Node ids are D229's. Columns, constraints and indexes come from
`duckdb_columns()`, `duckdb_constraints()` and `duckdb_indexes()`; a
constraint carries the name DuckDB gave it, and a foreign key's target is in
its own schema. A relation's DDL is the statement the file keeps, followed by
its indexes'.

Spec: [A DuckDB source](../../decisions/2026-11-20-duckdb-source-design.md)

## D390. A value crosses as the text DuckDB writes for it

A column's category is its type. Every value leaves the engine as text DuckDB
made: numbers to their last digit, a moment with a time zone in UTC, a blob as
`0x` and its hexadecimal, a list, an array, a struct, a map, a union or a
variant as `to_json`. A nested column does not sort. A filter binds text,
which DuckDB reads as the type it infers from the column; a value it cannot
read is the reader's error. A boolean is spelt `true` or `false`. `contains`
compares the text a value is shown as, with `ILIKE` and a named escape.

Spec: [A DuckDB source](../../decisions/2026-11-20-duckdb-source-design.md)

## D391. Pages follow the primary key, or else the rowid as a tiebreak only

After the reader's own sort a page is ordered by the primary key, or else by
`rowid`, unless a column takes that name or the relation is a view. DuckDB
gives an updated row a new `rowid`, so it orders pages and never names a row:
a table without a primary key is read only.

Spec: [A DuckDB source](../../decisions/2026-11-20-duckdb-source-design.md)

## D392. Statements are read with DuckDB's own parser

Boundaries come from `duckdb.tokenize`: a semicolon ends a statement unless it
is inside a string, a dollar-quoted body, a quoted name or a comment. Each
statement's class comes from the type `duckdb.extract_statements` names, and
from its first word where one type covers several things: `SELECT`, `PIVOT`,
`CALL` and a reporting `PRAGMA` read; `CHECKPOINT`, `VACUUM` and `ANALYZE` are
maintenance; `EXPLAIN ANALYZE` is the class of what it runs. A statement that
does not parse is refused with DuckDB's sentence before anything runs.

`ATTACH`, `DETACH`, `COPY`, `EXPORT` and `IMPORT DATABASE`, `INSTALL`, `LOAD`,
`SET`, `RESET`, `USE`, a setting pragma, `PREPARE`, `EXECUTE`, `DEALLOCATE` and
a secret are refused by family, each with its reason. Structure changes are
tables, views, indexes, schemas, sequences, types and macros. Parameters are
`$name`.

Spec: [The DuckDB console](../../decisions/2026-11-20-duckdb-console-design.md)

## D393. Runs and transactions are PostgreSQL's, without savepoints

DuckDB changes structure inside a transaction, so a run is one transaction, a
held one may change structure, and a destructive change is rehearsed and
rolled back. A read is its class plus a transaction rolled back: one
connection cannot be made read-only without a second configuration. Every run
is on the catalog's engine, locked to the owner's home (D388). The search path
is DuckDB's `search_path`, each name checked against the file's schemas.

Any failed statement aborts the transaction, which is then broken. A held
transaction keeps the file open, so no other program can open it meanwhile.

Known deviations:

- DuckDB has no savepoints, so a change is not rehearsed inside a held
  transaction; the rehearsal is refused, and a destructive change runs in
  auto-commit.

Spec: [The DuckDB console](../../decisions/2026-11-20-duckdb-console-design.md)

## D394. A result crosses as DuckDB's text; a failure in DuckDB's words

A `SELECT` is bound once for its column types and run wrapped, each column
cast by position as the grid's are (D390). Any other statement with a result is
read as the driver gives it and written as text here; one holding a moment
with a time zone asks for a `SELECT`, which the driver cannot convert without
`pytz`. A row change answers with its affected rows. A failure is DuckDB's
sentence without its `LINE` excerpt, the owner's home written as `~`, its
category from the exception's class. Explain reads `EXPLAIN (FORMAT JSON)` as
a tree, with DuckDB's own drawing as the raw text.

Known deviations:

- A result that is not a `SELECT` is written by Python's types rather than
  DuckDB's: an interval as a duration, `1 day, 3:00:00`, and a nested value as
  JSON of what the driver handed over.

Spec: [The DuckDB console](../../decisions/2026-11-20-duckdb-console-design.md)

## D395. A row is named by its primary key alone, and checked by a digest

A row's handle carries its primary key's values as the page shows them, and a
row is found by `key = ?` with that text bound, which DuckDB casts to the
key's type; a binary key is compared as its text. A table without a primary
key takes new rows and is otherwise read only: DuckDB moves an updated row
(D391), and a table may hold two identical rows. A view is read only.

The version is a digest of the row as shown, checked in the change's own
transaction; DuckDB refuses a second writer of the same row as a conflict,
and `RETURNING` hands back the row as written. A value is bound as its shown
text and DuckDB converts it, a binary one as bytes from `0x…`. A list, a struct,
a map, a union, a variant, a geometry and a generated column are not written.

A value DuckDB cannot read fails the whole change, since any failure aborts
the transaction; only then is each value tried alone in a temporary table of
the target's column types, outside any transaction, to name the refused
cells. A refused change is named by DuckDB's sentence, read and not shown.
Keys arriving at a table are read from `duckdb_constraints()` in its schema.

Known deviations:

- DuckDB carries out a change to a key or unique column as a delete and an
  insert, so a row other rows refer to cannot have one changed at all; the
  refusal says so.

Spec: [Editing DuckDB rows](../../decisions/2026-11-20-duckdb-rows-design.md)

## D396. A structure change is DuckDB's ALTER TABLE in place, views bound after

DuckDB's ALTER TABLE adds, drops, renames and retypes a column, sets and
drops its default and `NOT NULL`, and adds a primary or unique key in place,
so every change is one statement in a transaction (D393) and nothing is
rebuilt. What the rows contradict is counted first, up to 1000: rows with no
value before `SET NOT NULL`, values `TRY_CAST` cannot convert before a type
change, repeating groups before a unique key or unique index. A default is
tried with `TRY_CAST` to the column's type before it is set, since DuckDB
stores one it cannot convert, and is written `CAST('…' AS type)`.

DuckDB renames and drops a column without looking at the views that read it,
so inside the change's transaction every view of the file is bound with
`SELECT * FROM … LIMIT 0`, and one that bound before and does not after
refuses the change by name. What DuckDB refuses itself is said in its own
sentence; its "entries that depend on it", which names nothing, is reworded
to say that the table's index or another table's foreign key is in the way.

Indexes are DuckDB's ART, named `<table>_<columns>_idx` and made unique in
the schema; constraints are named by DuckDB (D389). The types offered are a
closed vocabulary of DuckDB's own, spelt as `duckdb_columns()` reads them
back.

Known deviations:

- **No foreign key or check is added to an existing table, and no constraint
  is dropped**, the primary key included: DuckDB's ALTER TABLE has neither.
  A rebuild as SQLite's (D255) was rejected, because DuckDB refuses to drop a
  table a view or a foreign key depends on, so it would fail exactly where
  keys matter. The refusal says to copy the table into one designed with the
  structure wanted.
- **A table with an index of its own, or one another table's foreign key
  names, takes only a new column, a default and an index.** Every other
  change is refused by DuckDB.
- **No partial index.**

Spec: [Changing DuckDB structure](../../decisions/2026-11-20-duckdb-structure-design.md)

## D397. A designed table is PostgreSQL's plan, its identity a sequence

The designer's plan is a `CREATE TABLE`, one `CREATE INDEX` per index and
`COMMENT ON` the table and its columns, run in one transaction; a table made
from rows is the table and its rows in one transaction, the values bound as
text and converted by DuckDB (D395), one it cannot read leaving the table
unmade.

DuckDB has no identity column, so an identity is a sequence of its own,
`<table>_<column>_seq`, made first, the column's default `nextval` of it; it
starts anywhere and steps by any non-zero amount, and ALWAYS is a plan
problem, since DuckDB takes a value written into the column. A stored
generated column is made as DuckDB's virtual one, with a warning. A literal
default is tried with `TRY_CAST` while planning.

What DuckDB lacks is a plan problem on the object asking for it (D117): an
unlogged or partitioned table, a hypertable, a foreign key that cascades,
sets null or a default, is deferrable, matches fully or points into another
schema (D389), a deferrable unique key, nulls not distinct, INCLUDE, an
operator class, a predicate. A constraint name given is a warning, since
DuckDB names constraints itself. Collations are DuckDB's built-in `NOCASE`,
`NOACCENT` and `NFC`.

Spec: [Changing DuckDB structure](../../decisions/2026-11-20-duckdb-structure-design.md)

## D398. Reports are DuckDB's catalog functions; search reads the catalog whole

A **System** section after the schemas, id `\system`, holds the file's
reports: Database (DuckDB's version and `pragma_database_size()` without the
memory figures), Sequences, Types and Macros of the file, and DuckDB's
built-in Functions. Each is a statement of the package read as a subquery
with the page's filters, sorting and paging, its columns typed by `DESCRIBE`
and its values cast to text as a relation's (D390). Nothing is written through
a report, no table is made of one, and a row of one is not a record.
Sequences, types and macros are reports rather than catalog nodes: nothing
here acts on them but the console.

Settings and extensions are not reported: the settings name paths of the
server (D388), and `duckdb_extensions()` reads the extension directory, which
the lock refuses.

Search reads every relation of every schema, and for a column search every
column, in one inspection and classes names with the shared word rule in
Python; it is cheap for every field. It starts at the top, in a schema, or
among the reports, found by their titles. An export takes the page's read on
one connection a batch at a time.

Spec: [DuckDB reports, search, export and catalog actions](../../decisions/2026-11-21-duckdb-actions-design.md)

## D399. A drop is rehearsed; a table with a foreign key is not renamed

The catalog offers New schema, Drop schema, Rename, Drop, Load from CSV,
Create table and Model as code. A schema is not renamed and nothing moves
between schemas: DuckDB parses neither.

A rename is `ALTER TABLE` or `ALTER VIEW … RENAME TO`, every view bound after
it in its transaction (D396), so one that read the old name refuses it. A
table with an index of its own, or one another table's key points at, is
refused by DuckDB, and the refusal says why. A drop — of relations together,
or of a schema with `CASCADE` — is rehearsed: carried out, every view bound,
and rolled back; the preview names each view that would stop working. Views
go first, then tables, one pointing at another of the selection before it; a
key from outside the selection blocks the drop. A sequence only the dropped tables
take values from, as the designer's identity, goes with them. `main` is not dropped. A
loaded CSV file is a table of `VARCHAR` columns made with its rows in one
transaction (D397).

Known deviations:

- **A table with a foreign key of its own is not renamed.** DuckDB renames
  it but keeps the old name as the dependent of the table the key points at,
  which can then neither delete a row nor be dropped, even after the renamed
  table is gone and the file reopened.

Spec: [DuckDB reports, search, export and catalog actions](../../decisions/2026-11-21-duckdb-actions-design.md)

## D400. A copied table is described from the catalog, its rows as DuckDB's text

A table is described from DuckDB's catalog: each column's type as
`duckdb_columns()` spells it — an enum with its labels, so a user type needs no
description of its own — its requirement, default and generation, the keys and
checks of `duckdb_constraints()`, foreign keys as links, each index's keys read
after `ON` in its `CREATE INDEX`, and the comments. A default that is exactly
`nextval` of a sequence of the file travels as an identity, and the copy makes
`<table>_<column>_seq` for it, starting where the original would go next
(D397). A view is refused, and so is a table with a `UNION` column.

Rows travel as JSON lines of the text DuckDB casts each value to, and the
destination casts them back by the column's type, which is exact for every
type but a union. The copy is one transaction: sequences and tables first,
each table after every table of the copy it points at, since DuckDB checks a
key at once against a table that must exist; then rows in that order, then
indexes and comments. Inside one file the rows are copied by `INSERT … SELECT`.
A link may keep its original only inside one file and one schema (D389).

Spec: [Copying DuckDB tables, backing a file up, the lab, and a file seen from a file source](../../decisions/2026-11-21-duckdb-copy-design.md)

## D401. A file is backed up as itself, its log checkpointed into it

The backup program is a script for plain Python in `python:3.14-slim`, as
SQLite's (D260), with no DuckDB in it: before it is named, the connection runs
`CHECKPOINT`, which writes the log into the file, and the script copies the
file byte by byte. It refuses while a `.wal` lies beside the file, since
another program is then writing. A restore must begin with DuckDB's header,
`DUCK` after eight bytes, is refused while the file it replaces has a log, and
is written beside the file and moved into place.

Known deviations:

- **The copy is not DuckDB's own.** A program that opens the file between the
  checkpoint and the copy and writes leaves a `.wal`, which the script sees;
  one that writes and closes in that moment is copied as it left the file.

Spec: [Copying DuckDB tables, backing a file up, the lab, and a file seen from a file source](../../decisions/2026-11-21-duckdb-copy-design.md)

## D402. The lab is a file

A DuckDB source starts no server, so its sample is `lab.duckdb`, the lab of
the other samples told in DuckDB's terms — enums, a struct, a list, a map,
`HUGEINT`, `TIMESTAMPTZ`, intervals, JSON, a blob, sequences behind
identities, a virtual generated column, checks, foreign keys, an index, a
view, a macro, a second schema and a table with no key — written by
`app.seed_storage` into the development superuser's storage and opened by the
`duckdb-lab` connection `bun run seed:connectors` adds.

Spec: [Copying DuckDB tables, backing a file up, the lab, and a file seen from a file source](../../decisions/2026-11-21-duckdb-copy-design.md)

## D403. A DuckDB file in a file source shows its tables and connects

A file named `.duckdb` or `.ddb` offers the `database` representation, as a
SQLite file does (D262): its tables and views with DuckDB's estimates, the
engine and the size, at most a thousand, one outside `main` named with its
schema. It is opened read only by an engine sealed to the file's folder
(D388), under a clock; a file without DuckDB's header says so. The explorer
asks for the reader by the engine its name says; this package registers it.

**Connect as DuckDB** drafts a DuckDB connection to the file, owner only, in
personal storage only, as Connect as SQLite does; each is offered for its own
engine's files, and the database panel offers whichever the server does.

Spec: [Copying DuckDB tables, backing a file up, the lab, and a file seen from a file source](../../decisions/2026-11-21-duckdb-copy-design.md)

## D404. A DuckDB database is made here as a file

**Create DuckDB here** is Create SQLite here (D263) for a `.duckdb`: left to
the server, `databases/dataplayer.duckdb` with the lab of D402; chosen, the
folder, the name, and the lab or an empty database. Where and under what name
is one shared rule, `adapters/made_here.py`. DuckDB always keeps its log, so
the type says it has no write-ahead log to choose and the form leaves the
choice out; the type also says which file the server would make. A connection
deleted with its file takes the `.wal` beside it.

Spec: [Copying DuckDB tables, backing a file up, the lab, and a file seen from a file source](../../decisions/2026-11-21-duckdb-copy-design.md)
