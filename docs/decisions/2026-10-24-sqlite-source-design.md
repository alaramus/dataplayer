# A SQLite source

Decisions D247–D251. The first slice of a SQLite source type that is meant to
reach what PostgreSQL does. This slice reads: a database file, its catalog, a
relation's model, its summary and DDL, and its rows. Writing rows, the SQL
console, structure changes, actions, exports, table copies, backups and sample
data follow in later slices, each in its own commit. What SQLite has no notion
of — users, sessions of other clients, server counters — is not planned.

## A file in its owner's storage (D247)

SQLite is a library and a database is a file, so a source is a path rather
than an address. Three places were possible for it:

- any path on the server's disk — rejected: it is D8's rule broken by a form
  field, since anybody could open another person's files or the server's own;
- a file inside another connection's storage, an SSH server's included —
  postponed: SQLite needs random access and locks, which SFTP cannot give, so
  it would mean copying the file and writing it back, a feature of its own;
- a file in the owner's personal storage — chosen. The path is judged by the
  file source's own containment rule (`LocalStorage.place`), symlinks
  followed, on every open, so there is no second rule and a link swapped in
  later is caught.

A missing file is a failed check unless **Create the file if it is missing**
is ticked; a typo should not leave an empty database behind silently. The
folder it goes into must exist.

Driver: the standard library's `sqlite3`. aiosqlite was the alternative; it is
the same module behind a thread of its own per connection, and it would hide
`interrupt()` and `setconfig()`, both needed below. Every call opens its own
connection inside a worker thread, does its work and closes it: opening a file
costs microseconds, and a pool of connections tied to threads would buy
nothing for a page of rows. A cancelled request interrupts its statement from
the event loop, which `interrupt()` allows from any thread.

The file is the user's but its content is untrusted: anybody can upload a
database made to hurt. Every connection is opened with:

- `SQLITE_LIMIT_ATTACHED` at 0, which refuses `ATTACH` and `VACUUM INTO`,
  both of which name a second file anywhere on the disk;
- an authorizer refusing `ATTACH`, `DETACH`, `load_extension`,
  `fts3_tokenizer` and the pragmas that move temporary files elsewhere — the
  library Debian ships is built with `SQLITE_ENABLE_FTS3_TOKENIZER`, whose
  two-argument form takes a function pointer from SQL;
- `SQLITE_DBCONFIG_DEFENSIVE`, so the schema cannot be corrupted on purpose,
  and `trusted_schema` off, so a view or a trigger in the file cannot call a
  function with side effects;
- `query_only` for every read, so a read cannot write even if a statement
  would.

The floor is SQLite 3.37, for `pragma_table_list` and STRICT tables. The
library is the server's own, so the check refuses a deployment below it.

## One schema, `main` (D248)

A connection to SQLite has `main`, `temp` and whatever was attached. `temp` is
empty in a connection opened per call, and attaching is refused (D247), so
`main` is the only schema. It stays a node of its own rather than the catalog
listing tables at its root: the table designer, copying tables and loading a
file pick a schema node from the first level, and a later `ATTACH` of another
file in the same storage would be a second one.

Relations are read from `pragma_table_list`: tables, views, virtual tables and
their shadow tables. `sqlite_schema`, `sqlite_sequence` and `sqlite_stat*` are
the library's own, and shadow tables belong to their virtual table; both are
marked system. A node id is `main.<relation>`, split on the first dot, since
the schema part is a fixed name with none.

There are no row estimates unless `ANALYZE` has written `sqlite_stat1`, and
nothing counts rows: a count is a full scan of the smallest index. Sizes are
not read either — `dbstat` walks every page of a table to sum them.

## What the pragmas do not say is read from the table's text (D249)

The pragmas give columns, the primary key, foreign keys and indexes. They do
not give CHECK constraints, a column's collation, the expression of a
generated column or the name a constraint was given. Those are in the
`CREATE TABLE` text SQLite keeps in `sqlite_schema`, and are read from it by a
tokenizer written for SQLite's grammar of names, strings and comments; an
expression is the original text between its parentheses, not a reformatting.

sqlglot was tried first and fell back to an opaque command on `NOT NULL
COLLATE NOCASE CHECK (…)`, which is ordinary SQLite. A reader that keeps what
it cannot place rather than failing the whole table is what a catalog needs:
an unreadable clause leaves out what it would have said, and the pragmas'
facts stand.

A constraint SQLite was not told the name of has none. Unnamed, it is named
for what it is — `PRIMARY KEY`, `UNIQUE (a, b)`, `FOREIGN KEY (a)`, `CHECK 1`
— rather than after the index SQLite made for it, which a person never wrote.

## Values (D250)

SQLite stores a value in one of five classes whatever the column says; a
column's declared type is only an affinity. So a column's category follows the
affinity rules, with the names people use for dates, booleans, JSON and UUIDs
read as those, and each value is written by what it is: an integer exactly, a
real as the shortest text that reads back to it, a blob in hexadecimal in any
column, text as stored. Text that is not valid UTF-8 is shown as hexadecimal
rather than decoded with replacements, which would show a value that is not
there. A boolean is `true` or `false` only when it is 0 or 1.

Filters bind a number as a number and everything else as text, which a column
with numeric affinity converts the way the comparison would. A column with no
declared type compares as text.

Names are written in double quotes. SQLite reads a double-quoted name that
matches no column as a string literal; every name here is first found among
the relation's columns, so the fallback is never reached. `LIKE` escapes `%`,
`_` and its escape character with `ESCAPE '!'`; it is case-insensitive for
ASCII, as the other sources' `contains` is.

## Pages (D251)

After the reader's sort, a page is ordered by the primary key, or else by
`rowid`: every table but a `WITHOUT ROWID` one has it, it is unique, and a
`WITHOUT ROWID` table always has a primary key. Only a view, and a table whose
columns take all three of `rowid`, `oid` and `_rowid_`, get no tiebreak.

## What this slice leaves out

Writing, the console, structure changes, following a foreign key from a cell,
exporting every row, catalog actions, backups, sample data and copying tables.
Each is a later slice and is listed in the user's guide page as not there yet.
