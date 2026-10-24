# SQLite

What a SQLite source is, how it opens its file, how it reads its catalog and
the parts of a table the pragmas do not give, and how its values and pages
cross to the grid, and how its SQL console differs from PostgreSQL's. The contract every source type follows is in
[contract.md](contract.md); reading a relation in general is in
[relations.md](relations.md). Read this before changing the `sqlite` adapter.

Decisions here: D247, D248, D249, D250, D251, D252, D253.

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
