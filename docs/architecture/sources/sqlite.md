# SQLite

What a SQLite source is, how it opens its file, how it reads its catalog and
the parts of a table the pragmas do not give, and how its values and pages
cross to the grid and are changed there, how its structure is changed and a table designed, its reports, search and catalog actions, and how its SQL console differs from PostgreSQL's. The contract every source type follows is in
[contract.md](contract.md); reading a relation in general is in
[relations.md](relations.md). Read this before changing the `sqlite` adapter.

Decisions here: D247, D248, D249, D250, D251, D252, D253, D254, D255, D256, D257, D258, D259, D260, D261, D262.

## D247. A SQLite source is one file of its owner's storage, opened defensively

The only option is a path below the owner's home, judged by the file source's
own containment rule (`LocalStorage.place`, D8) on every open, symlinks
followed. A missing file fails the check unless **Create the file if it is
missing** is ticked, and is then made only in a folder that exists.

The driver is the standard library's `sqlite3`. Every call opens its own
connection in a worker thread and closes it; a request that goes away stops
its statement through the progress handler, and catalog reads share one
five-second clock (D246). There is no read cache: an upload can replace the
file without any connection hearing of it.

The file's content is untrusted. Every connection is opened with at most one
attached database and an authorizer refusing any attachment that names a file
(so `ATTACH` and `VACUUM INTO` are refused and VACUUM's own temporary database
is not), `load_extension`, `fts3_tokenizer` and the pragmas that move temporary
files, `SQLITE_DBCONFIG_DEFENSIVE`, `trusted_schema` off,
the two-argument `fts3_tokenizer` and extension loading switched off,
`cell_size_check` on, and `query_only` for every read. `sqlite3` is imported by
this package alone (`lint-imports`).

The library is the server's own; below 3.37 the check refuses it, with its
version named.

Known deviations:

- A file on an SSH server or inside another connection cannot be opened: SQLite
  needs random access and locks that SFTP does not give.

Spec: [A SQLite source](../../decisions/2026-10-24-sqlite-source-design.md)

## D248. One schema, `main`

The catalog's first level is one schema node, `main`: `temp` is empty in a
connection opened per call and attaching is refused. It is a node rather than
the relations at the root, because the screens that pick a schema read the
first level. Relations come from `pragma_table_list`: tables, views, virtual
tables and their shadow tables. `sqlite_*` tables and shadow tables are system
tables. A node id is `main.<relation>`, split on the first dot.

A row estimate is what `sqlite_stat1` holds, the largest count among a table's
indexes, and nothing when `ANALYZE` never ran; nothing counts rows or reads
`dbstat` for sizes, since both walk the whole table.

A virtual table whose module the library lacks is listed, and its description
says so as a configuration failure.

Spec: [A SQLite source](../../decisions/2026-10-24-sqlite-source-design.md)

## D249. What the pragmas do not say is read from the table's own text

Columns, the primary key, foreign keys and indexes come from the pragmas.
Checks, a column's collation, a generated column's expression and the names
constraints were given come from the `CREATE TABLE` text in `sqlite_schema`,
read by the adapter's own tokenizer of SQLite's names, strings and comments.
An expression is the original text between its parentheses. A clause the
reader cannot place is passed over, and what the pragmas say stands.

A constraint with no name of its own is named for what it is: `PRIMARY KEY`,
`UNIQUE ("a", "b")`, `FOREIGN KEY ("a")`, `CHECK 1`. An index SQLite made for a
key keeps no text, and its definition is written the same way. A foreign key
that names no target columns points at the target's primary key, and is shown
with them.

An `INTEGER PRIMARY KEY` of a rowid table is the rowid under another name: it
cannot be null and is an identity column.

Spec: [A SQLite source](../../decisions/2026-10-24-sqlite-source-design.md)

## D250. A value is shown by what it is, a column by its affinity

A column's category follows SQLite's affinity rules, with `BOOLEAN`, the date
and time names, `JSON` and `UUID` read as those first; a column with no type,
or `ANY`, is `other`. A value is written by its storage class whatever the
column says: an integer exactly, a real as the shortest text that reads back,
a blob in hexadecimal in any column, text as stored, text that is not UTF-8 in
hexadecimal. A boolean is `true` or `false` only where it is 0 or 1.

Every column sorts. A filter binds a number as a number and anything else as
text; a column of no type, and JSON, are compared as `CAST(… AS TEXT)`, since a
value there keeps its own class. Names are double-quoted after they are found
among the relation's columns, which is what keeps SQLite's double-quoted string
fallback from being reached. `LIKE` names its escape character, and like the
other sources' `contains` it ignores the case of Latin letters.

Spec: [A SQLite source](../../decisions/2026-10-24-sqlite-source-design.md)

## D251. Pages follow the primary key, or else the rowid

After the reader's own sort, a page is ordered by the primary key, or else by
the rowid, under whichever of `rowid`, `oid` and `_rowid_` no column takes. A
`WITHOUT ROWID` table always has a primary key; only a view, and a table whose
columns take all three names, get no tiebreak.

Spec: [A SQLite source](../../decisions/2026-10-24-sqlite-source-design.md)

## D252. Statements are classed by SQLite's first keyword

The console reads text with the adapter's own tokenizer (D249). A semicolon
ends a statement only where `sqlite3.complete_statement` says the text before
it is complete, so a trigger's body is not split. The keyword after an optional
`EXPLAIN` or `WITH` clause decides the class: SELECT and VALUES read; INSERT,
UPDATE, DELETE and REPLACE change rows; CREATE, DROP and ALTER change
structure, within the vocabulary of tables, views and indexes, a trigger
refused by name; ANALYZE, VACUUM and REINDEX are maintenance; BEGIN, COMMIT
and their kind are transaction statements; anything else is unknown and not
run.

A PRAGMA that only reports is a read, one given a value is a session
statement, `optimize`, `incremental_vacuum` and `wal_checkpoint` are
maintenance, and the rest is unknown. ATTACH and DETACH are session statements
refused by name. Parameters are `:name`, bound by SQLite itself. Formatting is
sqlglot's, for reads and row changes only.

Spec: [The SQLite console](../../decisions/2026-10-24-sqlite-console-design.md)

## D253. Structure changes are transactional, so the console is PostgreSQL's

A run is one transaction, structure changes included; a held transaction may
change structure; a destructive change is rehearsed by carrying it out and
rolling it back, in a savepoint when a transaction is held, waiting at most
three seconds for another connection's lock before saying it is blocked.
Maintenance runs alone, outside a transaction. A read runs with `query_only`.

Every connection turns `foreign_keys` on, and the authorizer refuses setting
it, `query_only`, `writable_schema`, `trusted_schema` or `cell_size_check`
from a statement. A held transaction keeps its connection between requests and
uses it from any worker thread, one call at a time. The time limit and Stop
interrupt a statement through the progress handler. A failure that rolled the
transaction back by itself marks it broken.

A result column's type is what its values are. `EXPLAIN QUERY PLAN` gives the
tree, with SQLite's sentence per step and no costs; reads and row changes are
planned.

Spec: [The SQLite console](../../decisions/2026-10-24-sqlite-console-design.md)

## D254. A row is named by its primary key or its rowid

A row's handle carries its primary key, or else its rowid, with each value as
SQLite stores it and tagged with its class, so a key is found again whatever
the column's affinity would make of text; it is matched by `IS`, and a row
whose primary key holds NULL is not named. The version is a digest of the row
as shown, checked in a transaction opened with `BEGIN IMMEDIATE`, and the
change ends in `RETURNING`.

A value is bound as shown text, except that a binary column takes hexadecimal
back as bytes, a boolean one `true` and `false` as 1 and 0, and a column with
no type a number as a number when the text is its own spelling. A STRICT
table's values are tried in a temporary STRICT table first, so a block lands
whole or the refused cells are named. A broken constraint is named by its
extended result code.

Views, virtual tables and SQLite's own tables are read only, and a generated
column cannot be written. The keys that point at a table are found by asking
every table for its own.

Spec: [Editing SQLite rows](../../decisions/2026-10-24-sqlite-rows-design.md)

## D255. A structure change is a rebuild of the table's own text, edited

Adding a column that may be empty, renaming a column and renaming a table are
SQLite's ALTER TABLE. Every other change rebuilds the table as SQLite
documents it: a new table, the rows copied with their rowids, the old one
dropped, the new one renamed, its indexes and triggers made again, the
`sqlite_sequence` counter put back — in one transaction, with foreign keys
switched off by the application for its duration and the rename done in the
legacy way, after which every view is read once and one that reads what was
taken away refuses the change by name.

The new definition is the table's `CREATE TABLE` text with one clause edited,
by the positions the reader of that text keeps (D249): a type replaced, a `NOT
NULL` removed, a `DEFAULT` or a constraint written in, an item removed with its
comma. AUTOINCREMENT, conflict clauses, DEFERRABLE and comments survive
because nothing writes them out again. A dropped column takes its keys and
indexes along; a check that reads it refuses the change in SQLite's words.

Requirements, unique keys and indexes and foreign keys are counted against the
rows first, up to 1000. Only a STRICT table refuses a value for its type, and
its values are tried in a temporary STRICT column. Names are made in
PostgreSQL's pattern; a constraint is dropped by its shown name. The types are
declared types that read back as their category (D250), a STRICT table's own
five for a STRICT table, and the one index method is the B-tree.

Spec: [Changing SQLite structure](../../decisions/2026-10-24-sqlite-structure-design.md)

## D256. A designed table is statements in one transaction, its identity the rowid

The designer's plan is a `CREATE TABLE`, one `CREATE INDEX` per index and, for
an identity that starts elsewhere than 1, a row of `sqlite_sequence`, run in
one transaction. An identity is the table's rowid under the column's name: an
integer that is the whole primary key, written `INTEGER PRIMARY KEY
AUTOINCREMENT`; a second identity, one that is not the whole key, ALWAYS, or a
step other than one is a plan problem on the column.

What SQLite lacks is a plan problem on the object: an unlogged or partitioned
table, a hypertable, a deferrable unique key, MATCH FULL, NULLS FIRST or LAST,
an operator class, INCLUDE, an array, nulls not distinct. A partial index, SET
DEFAULT, a deferrable foreign key and an index on an expression are SQLite's
and are written. A comment is a warning, since SQLite keeps none. A primary
key column must have a value. Collations are BINARY, NOCASE and RTRIM.

A table made from rows is made with its rows in one transaction; no value is
refused for its type.

Known deviations:

- A designed table is never STRICT: the designer has no choice for it.

Spec: [Designing SQLite tables](../../decisions/2026-10-24-sqlite-design-design.md)

## D257. Reports are the file's pragmas; search reads the catalog whole

A **System** section after `main`, id `\system`, holds the file's reports:
File (page size and count, size, free pages, encoding, journal, auto-vacuum,
user version, application id, schema version), Integrity (`quick_check`),
Broken foreign keys, Triggers, Functions, Modules, Collations and Compile
options. Each is a statement of the package read as a subquery with the page's
filters, sorting and paging; its columns are named by SQLite and typed `other`,
since a result says no type. Nothing is written through a report and no table
is made of one.

Search reads every relation, and for a column search every column, in one
inspection and classes names with the shared word rule in Python; it is cheap
for every field. Reports are found by their titles. An export takes the page's
read from one connection a batch at a time.

Spec: [SQLite reports, search, export and catalog actions](../../decisions/2026-10-24-sqlite-actions-design.md)

## D258. A drop is rehearsed; a view is renamed from its own text

The catalog offers Rename, Drop, Load from CSV, Create table and Model as code;
no schema is created, renamed, dropped or moved into. SQLite's own tables offer
only the model. A table is renamed by ALTER TABLE; a view is made again under
the new name from its own text, and every view is read afterwards, so one that
read the old name refuses the rename.

A drop's preview is the drop carried out and rolled back, with foreign keys on:
dropping a table deletes its rows, so a cascade follows and a refusal blocks
the drop with SQLite's reason. The preview also names the table's triggers,
other tables' keys pointing at it, and the views whose text names it, read by
tokens. In a selection, tables that point at others of it go first. A loaded
CSV file is a table of TEXT columns made with its rows in one transaction.

Known deviations:

- A view that names a column called like the dropped table is listed as a
  reader of it.

Spec: [SQLite reports, search, export and catalog actions](../../decisions/2026-10-24-sqlite-actions-design.md)

## D259. A table is copied in its own words, in one transaction

A copied table is described from its own text (D255): each column's definition
as written without its inline foreign key, its table constraints with their
names, its indexes' keys and WHERE, and its options. Every part must stand
alone before it is composed; a column that does not refuses the table, anything
else is left out with a warning. Triggers are left behind; views, virtual
tables and SQLite's own tables are refused.

SQLite adds no foreign key to a table that exists, so links are written into
each CREATE TABLE and deferred to the commit. Tables, rows and indexes are one
transaction: a row pointing at nothing fails the commit, and a failure or a
stop leaves nothing. An index's name is the schema's, so the copy's is renamed
after the new table and kept free. Rows travel as JSON lines of values tagged
by class; text in no encoding arrives as text. The database is the file's path,
and inside one file the rows are copied by INSERT … SELECT, since a reader would
keep the copy's own commit waiting.

Spec: [Copying SQLite tables, backing a file up, and the lab](../../decisions/2026-10-24-sqlite-copy-design.md)

## D260. A file is backed up by SQLite's online backup, in a Python image

The backup program is a script for Python's `sqlite3` in `python:3.14-slim`:
the online backup copies the file page by page as one state of it, whatever
writes to it meanwhile. The file's path here is its path in the tool's
container (D87). A backup is offered when the connection check passes; a
restore must begin with SQLite's header and pass `quick_check` before it is
written. A restore writes a file of the storage, so its program says so and
only it gets the storage writable.

Spec: [Copying SQLite tables, backing a file up, and the lab](../../decisions/2026-10-24-sqlite-copy-design.md)

## D261. The lab is a file

A SQLite source starts no server, so it has no sample-data capability (D80).
Its sample is `lab.db`, the lab of the other samples told in SQLite's terms,
written into the development superuser's storage by `app.seed_storage`
and opened by the `sqlite-lab` connection `bun run seed:connectors` adds.

Spec: [Copying SQLite tables, backing a file up, and the lab](../../decisions/2026-10-24-sqlite-copy-design.md)

## D262. A SQLite file in a file source shows the tables it holds

A file named `.db`, `.db3`, `.sqlite` or `.sqlite3` offers one representation,
`database`: its tables, views and virtual tables with what ANALYZE counted, the
engine and the size; SQLite's own tables are left out, at most a thousand are
listed. No rows: they belong to a connection to the file. It is opened read
only under D247's guard and a clock; a file without SQLite's header says so.
The driver stays in this package, which registers a reader for database files
in the content module as it is imported; the file source asks for it by engine.

Spec: [A SQLite file seen from a file source](../../decisions/2026-10-24-sqlite-in-files-design.md)
