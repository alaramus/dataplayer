# MySQL and MariaDB

What a MySQL source is, how it reads its catalog, and how its values and
pages cross to the grid. The contract every source type follows is in
[contract.md](contract.md); reading a relation in general is in
[relations.md](relations.md). Read this before changing the `mysql` adapter.

Decisions here: D228, D229, D230, D231.

## D228. One source type for MySQL and MariaDB, from a stated floor

`mysql` speaks to both servers. They share a protocol, a driver and nearly
all of a dialect, and a person connecting does not choose between them: the
server says which it is in `VERSION()`, and the session reads that once and
keeps it. Where the two differ — how `information_schema` keeps checks, that
MariaDB's JSON is LONGTEXT with a `json_valid` check of the column's own, that
MariaDB has no functional index — the module that asks branches on the profile,
and nowhere else does. The server's version is shown as `MySQL 8.4.11` or
`MariaDB 11.4.13`.

Supported from MySQL 8.0.16 and MariaDB 10.6. Below them the catalog lacks
what is read — `CHECK_CONSTRAINTS` arrived in 8.0.16 — and the connection check
refuses the server with its version named rather than leaving it half working.

The driver is aiomysql, on PyMySQL. It encodes a password as Latin-1 while the
server compares UTF-8 bytes, so the session hands it the UTF-8 bytes spelt as
Latin-1. The connection asks for TLS and takes plain TCP when the server offers
no TLS, without verifying the certificate: libpq's `prefer`, which a
PostgreSQL connection gets unasked.

Known deviations:

- There is no option to require TLS or to verify the server's certificate.

Spec: [A MySQL source](../../decisions/2026-10-18-mysql-source-design.md)

## D229. A MySQL database is a schema

One connection reaches every database its user may see, and a statement can
name tables in several, so a database is a `schema` node — a namespace on one
connection — and not a `database` node, which is a key space sharing nothing
but the port (D91). The connection's database is optional and says where the
catalog opens: it is listed first. `mysql`, `information_schema`,
`performance_schema` and `sys` are marked as the server's.

A node id is the database, or the database and a relation. MySQL accepts a dot
in a database's name, so the database part escapes its dots and backslashes and
the first unescaped dot separates it from the relation.

Relations are read from `information_schema.TABLES` by `TABLE_TYPE`, so a view
is listed once, as a view. Their row counts are `TABLE_ROWS`: InnoDB's
estimate, which MySQL 8 may cache for a day. Nothing counts rows, on a listing
or on a page. Relations are ordered in Python, because the two servers' catalog
collations put `_` in different places.

Every column of a catalog query is aliased in lower case: MySQL 8 names those
columns in capitals and MariaDB does not.

Spec: [A MySQL source](../../decisions/2026-10-18-mysql-source-design.md)

## D230. Values cross as the canonical text of their type

Every value reaches the grid as text, as PostgreSQL's do (D23), and none is
lost on the way: `DECIMAL` and an unsigned `BIGINT` are exact, `BIT` is a
number, binary is hexadecimal, geometry is the server's WKT. `TIME` is written
as MySQL writes it, since it may be negative and past a day. A value the driver
cannot parse, such as a zero date, is kept as the server wrote it.

The session runs in UTC. A `TIMESTAMP` is therefore read in UTC and carried
with its offset, and a filter on one is converted to UTC first. A `DATETIME`
has no zone and is shown as written.

A name reaches a statement only quoted in backticks: double quotes are a string
literal unless the server runs with `ANSI_QUOTES`. Statements are composed by a
small composer in the adapter, as psycopg's `sql` module composes PostgreSQL's,
and every statement is sent with parameters, so a `%` in a name is doubled. A
text filter escapes `%` and `_` and names its escape character, since the
meaning of a backslash changes with `NO_BACKSLASH_ESCAPES`.

Spec: [A MySQL source](../../decisions/2026-10-18-mysql-source-design.md)

## D231. Pages follow a key the table has

After the reader's own sort, a page is ordered by the primary key, or else by a
unique key over columns that cannot be null — the key InnoDB keeps such a table
in — taken by name when there are several. A table with neither, and a view,
gets no tiebreak, because there is nothing honest to add. There is no physical
row address to fall back on as PostgreSQL's `ctid` is.

Spec: [A MySQL source](../../decisions/2026-10-18-mysql-source-design.md)
