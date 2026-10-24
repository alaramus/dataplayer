# Copying SQLite tables, backing a file up, and the lab

Decisions D259, D260 and D261. The sixth slice of the SQLite source: tables
copied with their structure between two SQLite connections or inside one file,
a file copied out into the backups folder and put back, and a sample file for
a development stack.

## Copying tables (D259)

The copy is the shared one (D182): the source describes each table, the window
decides where each foreign key points, and the destination composes and runs
its own statements from the description. Only the dialect's words are SQLite's.

### The description

A SQLite table has its own text, and that text is the only place some of it is
said: AUTOINCREMENT, a conflict clause, a collation, the expression of a
generated column. The structure changes already edit that text rather than
compose it again (D255), and the copy describes a table the same way:

- **A column** is its definition as written after its name, its inline foreign
  key left out. The tokens are joined again with comments dropped: a `--`
  kept in a part composed into a longer statement would swallow what follows.
- **A table constraint** — a primary key, a unique key or a check — is its
  item as written, its name with it. A constraint's name belongs to its table
  in SQLite, so the copy keeps it.
- **An index** made by CREATE INDEX is what follows `ON <table>`: its keys and
  its WHERE. An index's name belongs to the schema, so the copy's is the
  original's with the table's name at its front replaced, and numbered when
  the file has it already.
- **Options** are what follows the closing parenthesis: STRICT, WITHOUT ROWID.
- **A foreign key** is a link, inline or not. Triggers are left behind and
  named in the window; views, virtual tables and SQLite's own tables are
  refused, each with its reason.

Every part is checked to stand alone — one token stream with no semicolon, no
comment, every quote closed and every parenthesis matched — before it is
composed into anything. A column that does not is a refusal, since a table
without it is another table; a constraint, an index or options that do not are
left out with a warning.

### Carrying it out

SQLite cannot add a foreign key to a table that exists, so a link is written
into its table's CREATE TABLE rather than added after the rows as PostgreSQL
and MySQL do. The structure changes are transactional (D253), so the copy is
one transaction: the tables, then the rows, then the indexes, committed
together. Foreign keys are deferred to the commit, so the rows of a table may
arrive before the rows they point at, and a row pointing at nothing fails the
commit — "Some rows point at rows that were not copied" — and leaves nothing
behind. A failure or a stop at any step rolls everything back; there is no
undo of tables already made, because none are made until the commit.

The rows travel as JSON lines of values tagged by their storage class, as a
row handle tags its keys (D254): an integer stays an integer whatever its
size, a blob a blob. Text another program stored in no encoding is tagged
apart and written back through a CAST, because the driver binds bytes as a
blob. Rows are written in the order they arrive, so a table without a key of
its own numbers them in that order.

Two connections to one file are one database: the database a copy is said to
be in is the file's path on this server's disk. Inside one file the rows are
not streamed. A reader keeps a writer from committing in a file without a
write-ahead log, and here the reader and the writer would be the same copy;
so the file copies them itself, by INSERT … SELECT in the same transaction.

Rejected: ALTER TABLE ADD COLUMN … REFERENCES after the rows. It adds a
column, not a key, and the copy's columns are already there.

## Backing a file up (D260)

The backup is the shared one (D87): the source names a program, the job runs
it in a container of its own with the storage volume mounted, and the backup is
a file in the owner's backups folder.

SQLite needs no dump program of a matching version. Its online backup copies
the database page by page under its own locks, so the copy is one state of the
file even while somebody writes to it, and Python's `sqlite3` reaches it. So
the program is a short script for the official `python:3.14-slim` image, the
family this application's own image comes from: one script that copies a file
out, copies a backup in, or checks one.

- **The file's path is its path in the container.** The storage volume is
  mounted where this application has it (D87), so the source names the file it
  already judged by the containment rule (D8) and nothing is translated.
- **A backup is offered when the connection check passes.** A file that is not
  there, or not a database, is not offered.
- **A restore is checked before it is written.** A file in the backups folder
  is anything somebody put there: it must begin with SQLite's header before it
  is staged, and `quick_check` must say "ok" of it before anything is written.
- **A restore writes the storage.** Elsewhere a restore writes a server and
  mounts the storage read-only. A SQLite database is a file in that storage, so
  the program says it writes the storage (`writes_storage`) and the job mounts
  it writable for that program alone.
- **A restore replaces the file's contents** page by page, as the online backup
  does, which is why the restore insists on being told so, as every restore
  does.

Rejected: copying the file with the file source. A copy of a file somebody is
writing to is a torn file, and only SQLite's own locks avoid that.

## The lab (D261)

A source this application started is filled by its driver's installer (D80).
A SQLite source starts nothing: it opens a file. So its sample is a file,
`lab.db`, written into the development superuser's storage beside the other
sample files, and `bun run seed:connectors` adds a connection `sqlite-lab` to
it.

The file holds the lab the PostgreSQL and MySQL samples describe, told in what
SQLite has: STRICT and WITHOUT ROWID tables, AUTOINCREMENT, generated columns,
checks, foreign keys, a partial index, JSON kept as text, blobs, a view, a
trigger, a full-text table and a table with no key. It is written beside its
place and moved into it, so a connection reading the old one never sees half
of the new one.

SQLite does not declare the sample-data capability: no server of it is ever
started here for the offer to belong to.
