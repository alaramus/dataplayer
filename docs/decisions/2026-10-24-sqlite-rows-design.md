# Editing SQLite rows

Decision D254. The third slice of the SQLite source: changing, inserting and
deleting rows in the grid, and following foreign keys from a row either way.

## Naming a row

PostgreSQL names a row by its key and falls back on `ctid` (D42); MySQL has
no address and names a keyless row by all its values (D242). SQLite has the
rowid: every table but a `WITHOUT ROWID` one has it, it is unique, and a
`WITHOUT ROWID` table always has a primary key. So a row is named by its
primary key, or else by its rowid, and no table is left with rows that cannot
be told apart — except one whose columns take all three of the rowid's names.

The rowid of a table without an `INTEGER PRIMARY KEY` may change when the file
is vacuumed. The version check below catches that as a conflict, which is what
it is: the row read is not the row at that address any more.

The key's values travel in the handle as SQLite stores them, each tagged with
its class, not as the text a page shows. A column's affinity converts a bound
text the way a comparison would, but a column with no type does not, and an
integer key in such a column would never be found by the text `1`. Matching is
by `IS`, since a primary key of a rowid table may hold NULL; a row whose key
holds NULL is not named.

## Versioning a row

SQLite keeps no version a client can read. The version is a digest of the
row's values as shown, as MySQL's is (D234), checked inside a transaction
opened with `BEGIN IMMEDIATE`: the file's write lock is taken by the first
statement, so nobody writes between the check and the change. The change ends
in `RETURNING`, so the row that comes back is the one written, generated
columns and defaults included.

## Values

A value is bound as the text it was shown as, except where the column says
what the page did to it: hexadecimal goes back as bytes into a binary column,
`true` and `false` as 1 and 0 into a boolean one, and a column with no type
takes a number back as a number when the text is that number's own spelling.
Any other column converts the text by its affinity, as SQLite always does.

Only a STRICT table refuses a value for its type. Its values are tried first in
a temporary STRICT table with the same column types, as MySQL's are in a
temporary table (D234), so a block lands whole or the refused cells are named.
A temporary table lives in `temp` and costs the file nothing.

A refused change is named by SQLite's extended result code: a missing value, a
duplicate, a check, a foreign key — which reads as a missing target on a write
and as rows still pointing here on a delete.

## Following keys

D110 unchanged. SQLite keeps foreign keys only on the table that declares them,
so the keys arriving at a table are found by asking every table for its own;
the target a key names is matched without case, as SQLite matches it. An
arriving key is handed out as `name@source`, its name being the declaring
table's own, or the one D249 gives an unnamed key.
