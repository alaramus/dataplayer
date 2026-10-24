# Changing SQLite structure

Decision D255. The first half of the fourth slice of the SQLite source:
columns, indexes and constraints changed from the structure screen. Designing
a new table and making one from rows follow in the second half.

## What ALTER TABLE does, and the rest

SQLite's ALTER TABLE renames a table, renames a column, adds a column that may
be empty, and drops a column that no key, index or view uses. A type, a
requirement, a default, a unique key or a foreign key cannot be changed in
place. SQLite documents the way to do any of them: make a new table with the
definition wanted, copy the rows, drop the old table, give the new one the old
name, and make the indexes and triggers again — inside one transaction, with
foreign keys switched off for its duration. That is what this source does.

Two refinements of that procedure:

- **Foreign keys off.** With them on, dropping the old table would act on the
  rows that point at it: `ON DELETE CASCADE` in another table would delete
  them. They are switched off outside the transaction, as SQLite requires,
  by the application rather than a statement — the authorizer that keeps a
  statement from turning them off (D253) is lifted for that one pragma.
- **The rename in the legacy way.** Since SQLite 3.26 a rename checks every
  view against the schema, and in the middle of a rebuild the old name is
  gone, so a view that reads the table refuses the rename. SQLite's own
  procedure uses `legacy_alter_table` for that step; every view is then read
  once with `SELECT … LIMIT 0`, and a view that reads what the change took away
  refuses the change by name.

The rows keep their rowids, copied explicitly, and with them their order and
the handles a page holds (D251, D254). The counter `AUTOINCREMENT` keeps in
`sqlite_sequence` is put back, since it may be past the largest rowid copied.

## The new definition is the old text, edited

The alternative was to write the new `CREATE TABLE` from the catalog, as the
relation model describes the table. The catalog has no word for
`AUTOINCREMENT`, a conflict clause, `DEFERRABLE`, the order of a key's columns
as written, or a comment, and a rebuild that wrote the table out again would
drop each of them without a word — the same failure MySQL's `MODIFY` invites
and D235 avoids by editing the line `SHOW CREATE TABLE` prints.

So the reader of a table's text (D249) keeps where each clause is: a column's
type, its `NOT NULL`, its `DEFAULT`, each constraint inline or as an item of
its own. A change edits one of those places: replaces a type, removes a `NOT
NULL`, writes `DEFAULT` after the type, appends a constraint, or removes an
item with the comma that joined it. Everything else is the text as it was.

A dropped column takes the unique keys, primary key, foreign keys and indexes
over it along, as PostgreSQL's does. A check that reads it stays in the text,
and SQLite refuses the new table in its own sentence, which names the column.

## Counts before changes

D37–D40 answer a change the rows contradict with a count: rows with no value
for a requirement, groups of repeating values for a unique key or index, rows
pointing at nothing for a foreign key — each counted up to a ceiling of 1000
before anything is changed. Only a STRICT table refuses a value for its type;
its values are tried in a temporary STRICT column of the new type. Any other
column takes every value, by SQLite's affinity, so a type change is never
blocked there.

## Names and vocabulary

The source names what it makes, in PostgreSQL's pattern: `<table>_<columns>`
with `_idx`, `_key` or `_fkey`, made unique against the file. A constraint is
dropped by the name the catalog shows it under, which for an unnamed one is
what it is (D249).

The types offered are declared types whose affinity and name read back as the
category offered (D250): text, integer, real, numeric, boolean, date,
datetime, JSON, UUID and blob. A STRICT table takes only INTEGER, REAL, TEXT,
BLOB and ANY, and is offered those. The one index method is the B-tree.

A literal default is written as SQLite reads one of the column's kind: a
number bare where the column holds numbers, `true` and `false` as 1 and 0,
`0x…` as a blob, anything else as a quoted string.
