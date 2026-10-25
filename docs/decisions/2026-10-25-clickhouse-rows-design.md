# Editing ClickHouse rows

Decision D272. The third slice of the ClickHouse source: rows edited, inserted
and deleted in the grid.

## What names a row

ClickHouse has no unique key (D269). Three ways to name a row were weighed:

- the virtual `_part` and `_part_offset` columns — rejected: a merge renumbers
  them, so a handle read before a background merge names another row after it,
  and nothing in the handle could say so;
- insert-only, as MySQL is for a table with no usable key — rejected:
  ClickHouse tables have no unique key at all, so no ClickHouse row could ever
  be edited;
- the whole row — chosen, the rule MySQL already has for a keyless table
  (D242). The handle carries every value as shown and a digest of them; the
  row is found again by the columns that compare exactly, and the digest says
  whether what was found is still the row on screen.

Rows the same in every value cannot be told apart by anything a person or the
server has. MySQL changes one of them with `LIMIT 1`; ClickHouse's `UPDATE`
and `DELETE` have no limit, so here they change together, and the delete's
count says how many went.

A float is left out of the match because NaN equals nothing; a map because no
cast from text produces one; JSON, a variant and an aggregate state because
they are no single value. Rows alike in everything that compares and different
in one of those are refused with a sentence rather than changed together by
mistake.

## No transaction

ClickHouse cannot hold the row still between the check and the change. The
choice was between refusing to edit at all and a check that leaves a window;
the window is taken and recorded as a deviation. The digest still catches
every change made before the page was read, which is the case a person
actually meets — two tabs, one stale.

## Lightweight changes, and the mutation behind them

`DELETE FROM` is lightweight on every MergeTree table. `UPDATE` is lightweight
only on a table created with `enable_block_number_column` and
`enable_block_offset_column`, which is not the default; on any other it is
refused with `NOT_IMPLEMENTED`. Asking the table's settings first was rejected:
the refusal is exact and costs one round trip only on the tables that give it.
The fallback is the `ALTER TABLE … UPDATE` mutation with `mutations_sync=1`,
which rewrites the parts it touches — slow for a paste of many rows, and
recorded as such.

A column of the sorting, primary or partition key is not editable: ClickHouse
refuses to update one, since it decides where the row is kept.

## Values back to the server

The grid shows ClickHouse's own text (D268), and the server is the one that
knows how to read it back: `accurateCast(text, type)` refuses `300` for a
`UInt8` instead of wrapping it, and `parseDateTime64BestEffort` reads the `Z`
every moment is shown with. The type is the server's own text from
`system.columns`, and it travels as a parameter rather than in the statement,
so not even the catalog's words are composed into SQL. Arrays and tuples are
shown as JSON, which the server does not cast from, so they are written into
its text format first.

Every value is tried with a `SELECT` of the same expressions before the change,
and a refused batch is halved until each refused value is named: the grid then
marks the cells, as it does for MySQL and SQLite.

Inserts travel as `JSONEachRow`, one statement for the block: thousands of
values as URL parameters would pass the server's limit on an address, and
JSON takes numbers in quotes, maps and arrays as they are shown, and a missing
column as its default. A boolean is the one value it takes only bare.

## The escaped text of a parameter

Writing values back found a fault from the first slice: the server reads a
`param_<name>` value in its escaped text format, so a backslash or a tab in a
database name or a filter value was read as an escape or ended the value. Every
value the adapter sends is now escaped; an array written as the server's text
and a value typed for the console are marked as already in the server's
format and sent as they are.
