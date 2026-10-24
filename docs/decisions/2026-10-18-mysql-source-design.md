# A MySQL source

Decisions D228–D231. The first slice of a MySQL source type that is meant to
reach what PostgreSQL does. This slice reads: a connection, the catalog, a
relation's model, its summary and DDL, and its rows. Writing rows, the SQL
console, structure changes, actions and reports, exports, table copies,
backups and metrics follow in later slices, each in its own commit.

## Why one type for two servers (D228)

MySQL and MariaDB are separate products that share a wire protocol, a driver
and almost all of a dialect. Two source types would duplicate a package to keep
a handful of differences apart, and would ask a person to know which one their
server is. The server already says it in `VERSION()`. So one type, one session
reading the profile once, and a branch on it where the catalog differs:

- checks: MySQL names a check's table only in `TABLE_CONSTRAINTS` and states
  `ENFORCED` there; MariaDB names the table in `CHECK_CONSTRAINTS` and says
  whether a check belongs to a column;
- JSON: MariaDB's is LONGTEXT with a column check `json_valid(col)`, which is
  read as the type and not listed as a constraint;
- functional indexes: MySQL's `STATISTICS.EXPRESSION` does not exist in
  MariaDB;
- defaults: MariaDB writes an expression (`'abc'`, `NULL`), MySQL writes a
  literal bare and marks an expression `DEFAULT_GENERATED`.

The floor is MySQL 8.0.16 and MariaDB 10.6. Supporting older servers would
mean a version gate on every read that uses `CHECK_CONSTRAINTS` or a window
function, for servers out of support. A server below it is refused by the
connection check, with its version named.

Driver: aiomysql. The alternatives were asyncmy, a compiled extension whose
wheels have to keep up with each new Python, and PyMySQL in a thread pool,
which holds a thread per open query. aiomysql is pure Python over PyMySQL, and
PyMySQL is typed by `types-PyMySQL`; aiomysql has no type information, and the
session and pool, the only modules importing it, hand nothing of it on.

Two driver traps are handled in the session:

- the password is encoded as Latin-1, so a password outside Latin-1 is handed
  over as its UTF-8 bytes spelt as Latin-1;
- the pool waits for a free connection without a limit, so the wait is bounded
  by the same five seconds a direct attempt has, and a pool that waited out is
  answered with what one direct attempt says.

TLS: requested and not required, with no certificate check. PostgreSQL
connections get exactly this by libpq's default `prefer`; MySQL 8's
`caching_sha2_password` additionally avoids fetching the server's public key
over a plain connection when TLS is up. Requiring and verifying TLS is an
option to add when somebody needs it.

## A database is a schema (D229)

MySQL calls a namespace a database, and `SCHEMA` is a synonym in its own
grammar. A statement can join tables in two of them on one connection, which
is what a schema is in this project; a `database` node is a key space that
shares nothing with the next one. So a MySQL database is a `schema` node, and
the connection's database is optional and only says where the catalog opens.

A database name may contain a dot. Splitting a node id on the first dot, as
PostgreSQL's ids are split, would misread `a.b.t`; the database part escapes
its dots instead, and a relation's name keeps all of its own.

Row counts are `TABLE_ROWS`, an estimate, on every listing and page. Counting
`COUNT(*)` per page is a full scan on InnoDB, and a filtered page that counts
with a window function would fail on any server without one. `has_more` comes
from reading one row past the page, as PostgreSQL's does.

## Values (D230)

Read carelessly, several types are lost or corrupted on the way: a `DECIMAL`
turned into a float loses digits, bytes decoded as UTF-8 with replacements
corrupt binary and geometry, and an unsigned BIGINT over 2^53 loses digits in a
browser as a number. Every value already crosses as text
(D23), so each is written exactly here: decimals and integers by `str`, `BIT`
as an integer from its bytes, binary as hex, geometry selected through
`ST_AsText`, `TIME` from its `timedelta` with sign and hours past 24, a zero
date as the text the driver could not parse.

`TIMESTAMP` is stored in UTC and shown in the session's zone; DataPlayer's
session runs in UTC, so the value is known to be UTC and carries `+00:00`, the
way a PostgreSQL `timestamptz` does. `DATETIME` is not converted by the server
and is shown as written. `information_schema.TABLES.CREATE_TIME` follows the
session zone on both servers, so the summary's times are UTC as well.

Quoting: double quotes are a string literal unless `ANSI_QUOTES` is set, and a
filter quoted with them compares two constants and matches everything or
nothing without an error. Backticks always. PyMySQL formats the whole
statement with `%` whenever parameters are passed, so every statement is sent
with parameters and a `%` in a name is doubled; one rule, rather than one that
depends on whether a statement happens to have a placeholder. ruff's S608 is
kept on: statements are composed from fixed text and quoted names by a small
composer, the shape of psycopg's `sql` module.

`LIKE` escapes `%` and `_` with `!` and says `ESCAPE '!'`: a backslash means
something else under `NO_BACKSLASH_ESCAPES`.

## Pages (D231)

Without a stable order, page two can repeat page one. PostgreSQL falls back on
`ctid`; InnoDB has no row address a client can read. It does keep a table
without a primary key in the order of its first unique key over non-null
columns, so that key is the tiebreak, chosen by name for determinism. A table
with neither, and a view, gets none.

## What this slice leaves out

Writing, the console, structure changes, following a foreign key from a cell,
exporting every row, reports about the server, metrics, backups, sample data,
a service template and copying tables between connections. Each is a later
slice and is listed in the user's guide page as not there yet.
