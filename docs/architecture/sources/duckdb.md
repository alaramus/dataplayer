# DuckDB

What a DuckDB source is, how it opens its file and locks the engine to the
owner's storage, how it reads its catalog, and how its values and pages cross
to the grid. The contract every source type follows is in
[contract.md](contract.md); reading a relation in general is in
[relations.md](relations.md); the other DuckDB in the server, the sandbox
behind SQL over files, is in [file-sql.md](file-sql.md). Read this before
changing the `duckdb` adapter.

Decisions here: D387, D388, D389, D390, D391.

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
