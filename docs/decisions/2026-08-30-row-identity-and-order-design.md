# What identifies a row, and what order rows arrive in

## Problem

Two defects with one cause: nothing said which row is which, or which comes
first, so both answers were left to whatever the query plan happened to do.

**A row moves when it is edited.** The fetch adds `ORDER BY` only when the user
has chosen a sort. Without one PostgreSQL returns rows in plan order, which for
a sequential scan is physical order — and an `UPDATE` in MVCC does not change a
row in place, it writes a new version further along and marks the old one dead.
So editing a cell sends its row to the end of the page. Measured on the demo
data: a row at `ctid (0,1)`, first of two, came back at `(0,3)`, last.

It is worse than it looks. `LIMIT`/`OFFSET` without an order does not promise
that page two omits what page one showed, even when nobody is editing. And a
sort the user did choose settles nothing between rows that tie on it, so an edit
still moves a row within its group.

**A row without a primary key cannot be edited or deleted at all.** The handle
that versions a row (D25) is built from the key, so a source with no key
answers that editing is unsupported. That is not a property of the data — such
a table is perfectly editable — it is a property of how the handle was built.

## One answer to both: the source decides, and says so

A row's identity and a page's order are the source's business, not the plan's.
PostgreSQL has a second way to name a row and it serves both purposes.

`ctid` is a tuple's physical position. It is not stable — an update moves it,
and a rewrite of the table moves every one of them — but it does not need to be.
The handle already carries `xmin` and every operation checks it, so the handle
means "this exact version of this row", and `ctid + xmin` says that at least as
precisely as `key + xmin` does. An update by somebody else changes both; a
rewrite changes the ctid; either way the handle matches nothing and the answer
is the conflict it already is. What cannot happen is writing to the wrong row.

On a partitioned parent `ctid` alone is ambiguous — two rows in different
partitions share `(0,1)` — so the physical identity is `tableoid` and `ctid`
together.

## The key is still preferred where there is one

Not because ctid would be wrong, but because a ctid handle is fragile in a way
a reader cannot see: `VACUUM FULL`, `CLUSTER` or `pg_repack` move every row and
invalidate every open page's handles at once, and the reader is told their row
changed when it did not. A key survives all of that. So the key is the identity
wherever the relation has one, and physical identity is what a keyless relation
gets instead of nothing.

## Order is part of the answer

Every fetch ends with a deterministic tiebreaker, appended after whatever the
user asked for rather than instead of it:

- the primary key, ascending, where there is one;
- `tableoid, ctid` where there is not.

That makes paging honest — page two no longer overlaps page one — and stops an
edited row from moving, because its key did not change. A keyless relation is
the exception it has to be: with nothing stable to sort by, its rows are in
their physical order, and editing one moves it. That is said in the same breath
as the fragile handle, because it is the same fact.

The cost is an `ORDER BY` on every read. Where a key exists it is the primary
key index, which is the cheapest ordering the table has.

## Deliberate boundary

- No keyset paging. `LIMIT`/`OFFSET` with a stable order is correct, if not
  fast on a deep page; making the tenth page cheap is a separate change with a
  contract of its own.
- No hidden identity column offered to the reader. `ctid` stays inside the
  handle, which is opaque, and never becomes something to filter or sort by.
- A view is still not editable. It has neither a key nor a ctid of its own.
