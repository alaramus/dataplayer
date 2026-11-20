# Editing DuckDB rows

Decision D395. The third slice of the DuckDB source (D387–D394): changing,
inserting and deleting rows in the grid, and following foreign keys from a row
either way. Facts marked *checked* were tried on DuckDB 2.0.0 on 2026-11-20.

## Naming a row

PostgreSQL names a row by its key and falls back on `ctid` (D42), SQLite on its
rowid (D254), MySQL on all its values (D242). DuckDB's `rowid` cannot stand in:
an update that rewrites a row gives it a new one (D391). Naming a keyless row
by all its values, as MySQL does, was considered and rejected: DuckDB allows
duplicate rows, and a row that has a twin cannot be changed alone — `DELETE …
WHERE` every value equal takes both, and DuckDB has no `LIMIT` on a delete.
So a table without a primary key takes new rows and is otherwise read only,
with the reason shown. A view is read only.

A row's handle carries its primary key's values as the page shows them (D390),
and a row is found by `key = ?` with that text bound: DuckDB casts the text to
the key column's type, as it does for a filter, and reads back its own text
exactly — a decimal, a moment with a time zone, a 128-bit integer, an interval
(*checked*). A binary key is matched by the text it is shown as.

## Versioning a row

DuckDB keeps no version a client can read. The version is a digest of the row
as shown, as MySQL's and SQLite's are (D234, D254), checked in the transaction
that makes the change. DuckDB's transactions are optimistic: two connections
changing the same row conflict, and the second is refused with `Conflict on
update` (*checked*) — which is a conflict here too. Since another program
cannot open the file while this one holds it (D387), the only other writer is
another request of this server. The change ends in `RETURNING` the row's text,
so what comes back is what was written, generated columns and defaults
included.

## Values

A value is bound as the text it was shown as, and DuckDB converts it to the
column's type on writing it, by the same rules it reads its own text with
(*checked*, for every scalar type the grid shows). A binary column takes the
`0x…` hexadecimal back as bytes. A list, a struct, a map, a union, a variant
and a geometry are shown as JSON or DuckDB's text but are not written back in
this slice: turning JSON into a struct needs the column's type in the
statement, and nothing else here writes a type. A generated column is computed.

Any failed statement aborts a DuckDB transaction (D393), so values are not
tried one by one inside the change. The change runs whole; if DuckDB refuses a
value as unreadable, the transaction is gone, and only then each value of the
block is tried in a temporary table made `AS SELECT` the target's columns
`LIMIT 0` — the column types without writing one — each in a statement of its
own outside any transaction, so the refused cells are named. A temporary table
lives in memory and costs the file nothing.

A refused change is named by DuckDB's own sentence, read for its kind and
never shown: a missing value, a duplicate, a check, a foreign key — a missing
target on a write, rows still pointing here on a delete (*checked*).

DuckDB carries out a change to a key or unique column as a delete and an
insert, so a row other rows refer to cannot have such a column changed at
all, even to a value nobody holds; any other column changes (*checked*). On a
write that refusal says so in those words, rather than as the delete it is
inside DuckDB.

## Following keys

D110 unchanged. DuckDB keeps a foreign key on the table that declares it, in
`duckdb_constraints()`, with the table it names; the keys arriving at a table
are those naming it, within its schema, since a key into another schema is
refused (D389). An arriving key is handed out as `name@source`.
