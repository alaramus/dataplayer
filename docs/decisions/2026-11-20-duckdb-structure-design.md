# Changing DuckDB structure and designing DuckDB tables

Decisions D396 and D397. The fourth slice of the DuckDB source (D387–D395):
columns, indexes and constraints changed from the structure screen, the table
designer, and a table made from rows. Facts marked *checked* were tried on
DuckDB 2.0.0 on 2026-11-20.

## What ALTER TABLE does in place, and what it cannot (D396)

DuckDB's ALTER TABLE does in place most of what SQLite needed a rebuild for
(D255): it adds, drops and renames a column, sets and drops a default, sets
and drops `NOT NULL`, changes a type, and adds a primary key and a unique key
(*checked*). So every change here is one statement, in a transaction, since
DuckDB's structure changes are transactional (D393).

What it cannot do is refused before anything is tried, with the reason:

- add a foreign key or a check to an existing table (*checked*: "No support
  for adding FOREIGN_KEY constraints with ALTER TABLE");
- drop any constraint, the primary key included (*checked*: "No support for
  that ALTER TABLE option yet");
- a partial index.

A rebuild, as SQLite's, was considered for those and rejected. It would drop
and remake the table, and DuckDB refuses to drop a table that a view or a
foreign key depends on (*checked*: "Cannot alter entry … because there are
entries that depend on it") — so the rebuild would fail exactly for the
tables where keys matter, and work only where it is least needed. Copying a
table with the structure wanted is the honest way, and the copying slice
brings it. The guide says so.

What DuckDB refuses itself — dropping a column a constraint or an index
depends on, changing the type of an indexed column — is said in DuckDB's own
sentence, as SQLite's is (D255): it names the thing in the way.

One refusal is DuckDB's and wider than it looks. A table with an index of its
own, or one another table's foreign key names, takes only a new column, a
default and a new index: renaming a column, a requirement, a type, dropping a
column and adding a unique key are all refused with "Cannot alter entry …
because there are entries that depend on it" (*checked*). That sentence names
no dependency, so this one is reworded to say what depends and what still
works.

**Views are read after a column change.** DuckDB renames and drops a column
without looking at the views that read it, which then fail when opened
(*checked*). Every view of the file is bound with `SELECT * FROM … LIMIT 0`
inside the change's transaction, and one that no longer binds refuses the
change by name, as SQLite's rebuild does.

**Counts before changes**, as D37–D40 ask: rows with no value before
`SET NOT NULL`, values that would not convert before a type change
(`TRY_CAST`), repeating groups before a unique key or unique index — each up
to a ceiling of 1000 before anything is changed.

**A default** is checked by `TRY_CAST` of the text to the column's type before
it is set, because DuckDB stores a default it cannot convert and fails only
at the next insert (*checked*). It is written as `CAST('…' AS type)` with the
column's type as DuckDB names it, so the stored default is of that type.

**Names and vocabulary.** An index is named in PostgreSQL's pattern,
`<table>_<columns>_idx`, made unique in the schema. DuckDB names constraints
itself and drops a name given (D389). The types offered are DuckDB's own:
text, integers of four widths, double, decimal, boolean, date, time,
timestamp, timestamp with time zone, interval, UUID, JSON and blob. The one
index method is ART.

## The table designer (D397)

The plan is PostgreSQL's shape: a `CREATE TABLE`, then one `CREATE INDEX` per
index, then comments, run in one transaction; what DuckDB lacks is a problem
on the object asking for it before the review (D117):

- **No identity columns** (*checked*: `GENERATED … AS IDENTITY` does not
  parse). An identity is a sequence of its own, `<table>_<column>_seq`,
  made first, with the column's default `nextval` of it. It may start
  anywhere and step by any amount; ALWAYS is a problem, since DuckDB takes a
  value written into the column.
- **A generated column is computed when read** (*checked*: "Can not create a
  STORED generated column"), so a stored one is written as DuckDB's virtual
  one, with a warning.
- **Foreign keys** take no `CASCADE`, `SET NULL` or `SET DEFAULT` (*checked*),
  are not deferrable, match simply, and point into the same schema (D389).
- **Unique keys** are not deferrable and treat nulls as different.
- **Indexes** have no `INCLUDE`, no operator classes, and no predicate.
- **No unlogged or partitioned table**, and no hypertable.
- **Constraint names** are DuckDB's own; a name given is a warning, not kept.
- **Comments are kept**: `COMMENT ON TABLE` and `COMMENT ON COLUMN` follow
  the table in the plan.
- A literal default is checked with `TRY_CAST` while planning, so a default
  DuckDB would fail on is a problem on its column, not a broken insert later.

Collations offered are DuckDB's built in: `NOCASE`, `NOACCENT` and `NFC`.

## A table made from rows

The table and its rows in one transaction, as on PostgreSQL (D45). A value is
bound as text and DuckDB converts it by the column's type (D395); one it
cannot read refuses the whole table, which is then not made.
