# Designing ClickHouse tables

Decision D274. The second half of the fourth slice of the ClickHouse source:
the table designer and a table made from rows.

## One statement

ClickHouse has no transaction to make several structure statements one, so
the plan is one `CREATE TABLE`, as MySQL's is (D236): columns, checks and
skipping indexes are all written inside it. The engine is MergeTree. Other
engines were not offered: Log, Memory and the rest cannot be changed later
(D273), and a designer that made tables the structure screen could not touch
would be making a trap.

## The primary key

The designer's primary key is a set of columns that names a row. ClickHouse's
`PRIMARY KEY` is a sparse index over the sorting key and names nothing (D269).
Three readings were weighed:

- refuse the primary key as ClickHouse has none — rejected: every table needs
  a sorting key to be read efficiently, and the primary key is where a person
  says which columns matter;
- write it as `PRIMARY KEY` beside a separate `ORDER BY` — rejected: the two
  must agree, and the designer has one list to give;
- write it as `ORDER BY` — chosen, which makes it the primary key as well.
  The plan carries a warning that it does not stop two rows from sharing it,
  so nobody reviews it believing otherwise.

A key column cannot be `Nullable` unless a server setting allows it, so a key
column that may be empty is a problem on that column, as it is for MySQL.

## What ClickHouse has not got

A unique key, a foreign key, an identity column, a collation, an index with an
order or a predicate or extra columns, a partition by range, list or hash, an
unlogged table and a hypertable are problems on the objects that ask for them.
An identity's problem says what fills the gap — a random UUID or the time as a
default — because a person asking for one wants a value they did not have to
type.

## Values that may be missing

A column whose value is not required is `Nullable(T)`; `LowCardinality(String)`
becomes `LowCardinality(Nullable(String))`, the only order the server accepts.
An array and JSON cannot be `Nullable`; rather than a problem, the plan warns
that such a column will always have a value, since an empty array is what a
missing one is in ClickHouse.

## A table from rows

A page's rows have no order of their own, so a table made from them is a
MergeTree with `ORDER BY tuple()`, every column `Nullable` because any cell of a
page may be empty. Every value is tried as its column's type first, by the
same probe edits use (D272), and the table is dropped if its rows are refused
after it exists — the promise D45 makes, kept without a transaction.
