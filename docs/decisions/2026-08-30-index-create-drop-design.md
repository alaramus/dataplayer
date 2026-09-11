# Creating and dropping an index

## Problem

A relation already describes its indexes — D22 put them in the model, and the
structure tab lists them — and nothing can be done with one. Making an index is
the commonest reason a person needs a database console at all, and the old
application had no way to do it either: its PostgreSQL templates cover rename,
add and drop column and stop there.

`CREATE INDEX` is almost entirely syntax. Its grammar takes a name, an access
method, a list of expressions with operator classes and sort options, a
partial predicate and included columns. Handing a client any of that as text is
the same defect three times over. So the question of this round is which small
part of that grammar can be reached without a client ever writing SQL, and what
happens to the rest.

## Nobody types a name

An index name is an identifier, and identifiers from a client are not new here
— a column is added under a name the user chose. But an index is different in
kind: it has no meaning to the person beyond the columns it covers, so asking
for a name is asking for a fact that has no answer, and the answer people
invent is a copy of the columns anyway.

PostgreSQL already names one, from the table and the columns, and uniquifies it
against the schema — which no client could do without reading the catalog. So
the statement carries no name and the server picks it.

That leaves the answer to say which index was made, because `CREATE INDEX`
reports nothing. The source reads the relation again and finds the index that
was not there before and whose columns, method and uniqueness are the ones that
were asked for. Dropping needs no such trick: it names an index the model
already showed, the way dropping a column names a column.

## What the request may carry

Columns of this relation, in the order they should be indexed; an access method
by code; and whether the index is unique. Everything else in the grammar is
out, and the reasons differ:

- **A partial predicate and an expression index are expressions.** They are the
  thing D2c exists to refuse, and no amount of parsing on the way in changes
  that.
- **Operator classes, collations, sort direction and NULLS ordering** are a
  vocabulary of their own, per method and per type. They belong to a round that
  has one.
- **Included columns** (`INCLUDE`) are cheap to add and mean nothing until
  someone is reading query plans, which this application cannot yet show.

## The methods come from the server, and so do their limits

The registry of offered methods is closed — btree, hash, BRIN, GIN, GiST — but
what each can do is not restated here. PostgreSQL answers
`pg_indexam_has_property(am, 'can_unique')` and `'can_multi_col'`, and the
relation model carries those two flags beside each method. So the screen can
grey out a unique hash index, and the source refuses the same combination
without asking the server to fail on it.

What is left to the server is whether a method suits the column's type at all:
GIN over an integer has no default operator class. That is a matter of
operator classes and extensions, it changes with what is installed, and the
answer is a refusal named by its SQLSTATE — `42704` — rather than a table of
type-method pairs kept here and wrong within a release.

## Rows in the way are counted, as everywhere else

A unique index is the third command that can be stopped by the data, after D37
and D38, and it is the one where counting is easiest and most useful: the rows
that break uniqueness are exactly the groups that repeat, and PostgreSQL can
count them with a plain aggregate. The source counts them before creating
anything, bounded and reported as in D37, and answers with the number.

The count excludes any group with a null in it, because PostgreSQL's default is
`NULLS DISTINCT` and two rows that are null in a key column do not collide.
Getting this wrong would refuse an index the server would happily have built.

A non-unique index cannot be stopped by data at all, so nothing is counted for
one.

## A drop takes nothing with it

Dropping names one index of this relation and issues no `CASCADE`, the rule D27
set for a column. Two indexes are refused before the statement: the one behind
the primary key and the one behind a unique constraint. PostgreSQL refuses them
too — `2BP01` — but it is better to say "it belongs to constraint X, drop that
instead", which the relation model already knows, than to relay a code.

## Waiting for the build

`CREATE INDEX` holds a lock against writers for the whole build, and the
request waits for it. `CREATE INDEX CONCURRENTLY` is the alternative and is not
used: it cannot run inside a transaction block, it can leave an invalid index
behind for somebody to find and clean up, and a request that returns before the
work is finished needs durable jobs with progress — which is the subject of
Phase 4, not of this round. The model already reports `valid`, so an invalid
index left by any means is at least visible.

## On screen

The Indexes section grows a button and each row a drop control, matching the
Columns section above it. The dialog picks columns in order, offers the methods
the relation published, and disables unique where the method cannot do it,
using the flag that came with the method rather than a rule of its own. A
blocked answer keeps the dialog open and states how many groups repeat.

## Deliberate boundary

- No name from a client, and none composed here.
- No predicate, no expression, no `INCLUDE`, no operator class, no sort or
  nulls ordering, no storage parameters, no tablespace.
- No `CONCURRENTLY`, and no rebuild or reindex command.
- No constraint creation. A unique index and a unique constraint are different
  objects, and the second one is the next round.
