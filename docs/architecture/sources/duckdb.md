# DuckDB

What a DuckDB source is, how it opens its file and locks the engine to the
owner's storage, how it reads its catalog, how its values and pages cross
to the grid and how its rows are changed there, and how its SQL console
differs from PostgreSQL's. The contract every source type follows is in
[contract.md](contract.md); reading a relation in general is in
[relations.md](relations.md); the other DuckDB in the server, the sandbox
behind SQL over files, is in [file-sql.md](file-sql.md). Read this before
changing the `duckdb` adapter.

Decisions here: D387, D388, D389, D390, D391, D392, D393, D394, D395.

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
