# Designing SQLite tables

Decision D256. The second half of the fourth slice of the SQLite source: the
table designer, and a table made from rows. It brings the source's first
catalog action, creating a designed table.

## Statements in one transaction

The plan is PostgreSQL's shape rather than MySQL's: a `CREATE TABLE`, then one
`CREATE INDEX` per index, run in one transaction. MySQL had to fit everything
into one statement because it commits each structure statement by itself
(D236); SQLite does not (D253), so the reviewed statements are the ones that
run and they land together or not at all.

## The identity is the rowid

SQLite numbers every row of a rowid table itself, and a column declared
`INTEGER PRIMARY KEY` is that number under the column's name. An identity
column is therefore written as one: an integer that is the table's whole
primary key, inline, with AUTOINCREMENT so a number given once is never given
again. The plan names what that rules out — a second identity, one that is
not the whole key, one that is ALWAYS, since SQLite takes a value written into
its rowid, or one that steps by more than one. A start is a row in
`sqlite_sequence`, written as a statement of its own in the plan.

## What SQLite lacks is named before the review

As D236 decided for MySQL, a choice the designer offers and SQLite does not
have is a problem on the object asking for it:

- an unlogged or partitioned table, and a hypertable;
- a deferrable unique key — SQLite defers foreign keys only, and those are
  offered with it;
- MATCH FULL, which SQLite parses and does not apply;
- NULLS FIRST or LAST, an operator class and INCLUDE in an index;
- an array, and nulls not distinct.

SQLite has what MySQL lacked here: a partial index, `SET DEFAULT`, a deferrable
foreign key and an index on an expression.

A comment is a warning rather than a problem: SQLite keeps no comments, and
the table is still made. A primary key column must have a value, as on the
other sources, although SQLite would accept NULL in one of a rowid table — an
old quirk the plan does not invite. Collations are SQLite's three built in.

## A table made from rows

The table and its rows in one transaction, as on PostgreSQL (D45). A column of
the published types takes any value by its affinity, so no value is refused
for its type and nothing has to be checked before the table is made.
