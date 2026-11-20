# A DuckDB source

Decisions D387–D391. The first slice of a DuckDB source type that is meant to
reach what SQLite does (D247–D263). This slice reads: a database file, its
catalog, a relation's model, its summary and DDL, and its rows. The later
slices are listed at the end; each gets its own decisions and its own commit.
What DuckDB has no notion of — users, sessions of other clients, server
counters — is not planned.

Facts below marked *checked* were tried against DuckDB 2.0.0, the version the
backend already ships for SQL over files (D78), on 2026-11-20.

## A file in its owner's storage, opened per call (D387)

DuckDB is a library and a database is a file, so a source is a path, judged as
SQLite's is (D247): a path below the owner's home, through the file source's
containment rule (`LocalStorage.place`, D8) on every open, symlinks followed.
Any path on the server's disk is D8's rule broken by a form field; a file in
another connection's storage needs random access that SFTP and S3 do not give.

A missing file is a failed check unless **Create the file if it is missing**
is ticked, and is then made only in a folder that exists. `duckdb.connect`
creates a file it does not find, so the adapter looks first rather than
letting the driver decide.

The driver is the `duckdb` package already in the backend. It is imported by
the explorer's SQL sandbox and by this adapter, and by nothing else
(`lint-imports`).

**Every call opens the file, works and closes it**, in a worker thread. The
alternative was one open database per file, kept by the process. It was
rejected for what DuckDB's lock does to everybody else:

- a file open for writing in one process cannot be opened at all, not even
  read-only, by another (*checked*), so a held database locks the person's own
  DuckDB CLI or notebook out of their file for as long as the server lives;
- within one process, a second open of the same file with a different
  configuration is refused (*checked*), so a held database would also decide
  the configuration of every later open — the explorer's view of the file
  included.

Opening and closing costs about 20 ms (*checked*, on Windows), which a page of
rows can afford. Concurrent calls in this process open the same file with the
same configuration and share DuckDB's instance, which DuckDB allows. A file
held by another program is a failed call that says the file is in use, not a
wait.

A file DuckDB cannot read — not a database, written by a newer DuckDB, damaged
— is a configuration failure naming what it is, never the driver's text: the
driver's message for a SQLite file names an extension path on the server
(*checked*). The library version is the server's own and is shown in the
summary; a file written by DuckDB 2.x may not open in 1.x, which the user's
guide says.

A cancelled request interrupts its statement from the event loop through the
connection's `interrupt()`, which works from another thread (*checked*); a
timeout is the same interrupt from a watchdog, as in D78.

## The engine is locked to the owner's storage (D388)

The file's content is untrusted, and from the second slice so is the
console's text. DuckDB has no authorizer like SQLite's; what it has is a
configuration that can be closed and locked. Every connection is opened with
extensions neither installed nor loaded automatically, community and unsigned
extensions refused, and then, before anything from the file runs:

- `home_directory` is the owner's home, so `~/sales/2026.parquet` names a file
  of their storage;
- `allowed_directories` is the owner's home and nothing else;
- the HTTP and S3 filesystems are disabled;
- `enable_external_access` is off — what turns the allowed directory from a
  list into a restriction;
- `temp_directory` is empty, and memory and threads are bounded, so a runaway
  sort fails rather than spilling into the person's storage, where DuckDB
  would otherwise put `<file>.tmp`;
- `lock_configuration` is on, so nothing the file or the user's SQL says can
  reopen any of the above.

*Checked* with this configuration: a file under the home reads through `~/`;
a path outside it, a `..` out of it, an HTTPS address, `INSTALL` and `LOAD`
are all refused; `SET enable_external_access=true` is refused as locked; and
`json`, `parquet` and time zones work, being built into the package. A
relative path is refused even with `file_search_path` set, so `~/` is the one
way to name a file, and the guide says so.

This is the engine's containment rather than D8's, which D77 refused for the
file source. The difference is what the engine is asked to contain: D77's
sandbox reads a file source's own nodes, so the source's one rule can judge
every name before the engine sees it; here the point of the console is
DuckDB's own SQL over the person's files, where a path is any string any
function takes. What stands behind the engine is that the server never makes a
symbolic link in a home (`users/storage.py`), so the engine's prefix check and
D8's symlink-following check judge the same tree.

Known deviations:

- A link put into a home by an operator would be followed by the engine.
- `glob('~/**')` and a reader's `filename` column return the server's absolute
  path of the home (*checked*). The owner learns where their own storage lives;
  rewriting result values to hide it would show data that is not there.
- `COPY … TO` and `ATTACH` write inside the home under this configuration
  (*checked*). Neither is reachable in this slice, which runs no client SQL;
  the console slice refuses them by statement class.

## Schemas and relations (D389)

The catalog's first level is the file's schemas from `duckdb_schemas()`,
`main` included even when empty: the screens that pick a schema read the
first level. `information_schema` and `pg_catalog` are DuckDB's own views and
are system schemas. The `system` and `temp` databases are not the file's and
are not listed.

Relations are tables from `duckdb_tables()` and views from `duckdb_views()`,
internal ones left out. A row estimate is `estimated_size`, which DuckDB keeps
without a scan; there is no per-table size. Node ids are D229's: the schema's
dots escaped, the first unescaped dot the separator.

Columns, their defaults and nullability come from `duckdb_columns()`;
constraints — primary key, unique, foreign key, check, not null — from
`duckdb_constraints()`, with the text DuckDB keeps for each; indexes from
`duckdb_indexes()`. A relation's DDL is the `sql` DuckDB keeps for it.
Sequences, types and macros are catalog nodes of the actions slice.

## Values (D390)

DuckDB is typed, unlike SQLite, so a column's category is its type: integer
widths up to `HUGEINT` and `UHUGEINT`, `DECIMAL`, floats, text, `BLOB`,
`BOOLEAN`, dates, times, timestamps with and without a time zone, `INTERVAL`,
`UUID`, `JSON`, `ENUM`, `BIT`, and the nested types `LIST`, `ARRAY`, `STRUCT`,
`MAP` and `UNION`.

A value crosses as what it is: a 128-bit integer and a decimal exactly, as
text; a float as the shortest text that reads back; a blob in hexadecimal; an
interval in DuckDB's own text; an enum as its label; a nested value as compact
JSON with its numbers as written, as ClickHouse's arrays, maps and tuples
cross. A map is a JSON object when
every key is text and a list of `{key, value}` pairs otherwise, since JSON has
no other keys.

Every column sorts but a nested one, whose order DuckDB defines and nobody
reading a grid expects. A filter binds its value as text and casts it to the
column's type in SQL, so DuckDB parses the date, the decimal or the UUID by its
own rules and a bad one is the reader's error rather than a wrong match;
`contains` on a nested column compares its text. Names are double-quoted after
they are found among the relation's columns. `ILIKE` names its escape
character.

## Pages (D391)

After the reader's own sort a page is ordered by the primary key, or else by
`rowid`. DuckDB's `rowid` is not an identity: an `UPDATE` that rewrites a row
gives it a new one (*checked*: updating a list column moved row 2 to rowid 5),
while a delete followed by `CHECKPOINT` and `VACUUM` kept the others
(*checked*). So it is a tiebreak that holds while nobody writes between two
pages, which is what a tiebreak is for, and nothing more: from the third slice,
a row is named for an edit by its primary key, and a table without one is read
only, with the reason shown.

## Later slices

Each is its own commit with its own decisions, and the user's guide lists what
is not there yet.

1. **This slice.** Read only.
2. **Console.** Statement classes come from DuckDB's own parser
   (`extract_statements`), not a first word. `ATTACH`, `DETACH`, `COPY`,
   `EXPORT`, `IMPORT`, `INSTALL`, `LOAD`, `SET`, `RESET` and setting pragmas
   are refused with their family named: each writes a file outside the
   database, changes the engine, or is refused by the lock anyway. Loading a
   file is `INSERT … SELECT * FROM '~/file.csv'`. DDL is transactional
   (*checked*), so the console's transactions are PostgreSQL's (D253's
   argument).
3. **Row edits** by primary key; a table without one is read only (D391).
4. **Structure changes and the table designer**, within what `ALTER TABLE`
   accepts — DuckDB refuses dropping a column a constraint names (*checked*).
5. **Reports, search, export, catalog actions**, with sequences, types and
   macros in the catalog.
6. **Copying tables, backups, the lab, a `.duckdb` file in a file source, and
   Create DuckDB here** — SQLite's D259–D263 counterparts.
