# Editing MySQL rows

Decision D234. The third slice of the MySQL source: changing, inserting and
deleting rows in the grid, and following foreign keys from a row either way.

## What PostgreSQL's editing rests on, and what MySQL has instead

PostgreSQL's handle (D25) is a key and `xmin`, a row's version that the server
keeps. A keyless row falls back on `ctid`, its physical address (D42). Every
change ends in `RETURNING`, so the row that was written is the row that comes
back. MySQL has none of the three.

**Naming a row.** The key InnoDB keeps a table in is the primary key, or else
its first unique key over non-null columns, which is also the key pages are
ordered by (D231). That key names a row. A table with neither has no name for
a row, since there is no physical address a client can use, and it takes new
rows and no edits. The alternative — matching a row by every column and
`LIMIT 1` — edits whichever of two identical rows the server finds first, and
is the kind of guess D42 exists to avoid.

**Versioning a row.** The alternatives were a revision column, which a table
may not have and which this application must not add; comparing every column
in the UPDATE's WHERE, which needs every type to compare equal to the text it
was shown as, and floats and binary do not; and a digest of the shown values.
The digest is cheap, needs nothing of the table, and compares exactly what the
person saw. It is checked after `SELECT … FOR UPDATE` in the same transaction,
so nothing can change between the check and the write.

**Reading back.** The row is read again by its key after the UPDATE, by the new
key if a key column was edited. An inserted row is read by the key it was
given or by `LAST_INSERT_ID()` for an AUTO_INCREMENT key. MariaDB has
`INSERT … RETURNING`, MySQL does not, and one path for both is simpler than
a branch that saves a round trip.

## Values

A server not in strict mode stores `abc` written to an integer column as 0 and
says so in a warning. Each change therefore adds `STRICT_ALL_TABLES` to the
session's mode for its transaction and puts the mode back afterwards, since a
pooled connection carries its session to the next request and the console
must see the server's own mode.

D37–D40 name values a column cannot hold rather than half-applying a block.
PostgreSQL asks whether each value casts to the column's type. MySQL has no
equivalent cast for every type it has, so each value goes into a temporary
table with the same column types as the target. A batch the server refuses is
halved until the refused values are found. A temporary table costs no
implicit commit. MariaDB reads WKT it cannot parse as NULL rather than an
error, so a shape is checked with `ST_GeomFromText(…) IS NOT NULL` instead.

A value is written back from the text it was shown as. Hexadecimal goes
through `UNHEX` and WKT through `ST_GeomFromText`. A TIMESTAMP with an offset
is turned into UTC, the zone the session reads in (D230).

Binary is sent as hexadecimal rather than as bytes for a second reason.
aiomysql 0.3.2 escapes a bytes parameter with `escape_bytes_prefixed`, which
PyMySQL 1.2 replaced with a string that says not to import it, so any bytes
parameter fails. Pinning PyMySQL below 1.2 was the alternative. Avoiding bytes
keeps the dependency current and loses nothing.

## Following keys

D110 unchanged. The target's database is read from `KEY_COLUMN_USAGE`,
because a MySQL foreign key may point into another database on the server. An
arriving key is handed out as `name@source`, since a constraint's name is
unique only within its own database.
