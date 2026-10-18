# MySQL and MariaDB

What a MySQL source is, how it reads its catalog, how its values and pages
cross to the grid, how its rows are changed, and how its SQL console differs
from PostgreSQL's. The contract every source type follows is in
[contract.md](contract.md); reading a relation in general is in
[relations.md](relations.md). The console every source shares is in [querying.md](../querying.md). Read this
before changing the `mysql` adapter.

Decisions here: D228, D229, D230, D231, D232, D233, D234.

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

## D232. Statements are read by sqlglot's MySQL dialect

The console (D62) reads MySQL text with sqlglot: its tokenizer draws the
boundaries, so a semicolon in a string, a backtick name or a comment is not
one, and its parser decides the class. `read` is granted to a SELECT, a set
operation, SHOW, VALUES and DESCRIBE of a table, and to nothing else; EXPLAIN
is `explain`. Where sqlglot falls back to a bare command, the keyword it kept
decides for a few — REPLACE is a write, OPTIMIZE maintenance, CREATE, ALTER,
RENAME, GRANT and REVOKE structure changes judged by the vocabulary — and
everything else is `unknown` and not run: `FLUSH PRIVILEGES` and `TABLE t`
parse as aliases, which is why a parse is not taken as a read by shape.
`SELECT … INTO OUTFILE`, `LOAD DATA`, `CALL` and `HANDLER` are unknown.

The vocabulary of structure changes is PostgreSQL's (D66) with databases in it,
since a database is a schema here (D229): tables, views, indexes and databases.
Altering a database, users, grants, routines, triggers and events are refused
by name.

Parameters are `:name`, the spelling PostgreSQL's console takes, read from
tokens so that `:=` is an assignment. They are bound by the driver, which
escapes each value for the server it is talking to; a literal `%` is doubled
once anything is bound. A value is always a string, so `LIMIT :n` is refused
by the server.

Formatting lays a statement out again only when its class is known and the
result parses back to the same tree: `FLUSH PRIVILEGES` has the same tree as
`FLUSH AS PRIVILEGES`.

Spec: [The MySQL console](../../decisions/2026-10-18-mysql-console-design.md)

## D233. A structure change commits by itself, so it runs alone

MySQL commits a structure change the moment it runs, together with whatever
the transaction held before it, and cannot roll it back. Three rules follow.

- In a run, a structure change or maintenance command is the only statement;
  with others beside it the run is refused at its first statement, because
  "the run is one transaction" (D66) would be false.
- In a transaction somebody holds open, it is refused: it would end that
  transaction behind their back.
- There is no rehearsal. The source does not claim it, the console says in its
  question that the change cannot be tried out first, and a held transaction
  answers a rehearsal with that sentence.

A failed statement does not end a MySQL transaction, so a held transaction
stays usable after one; a deadlock does, since MySQL has already rolled it
back, and the transaction is then marked as one that can only be rolled back.

A read runs in `START TRANSACTION READ ONLY`, which refuses writes to tables
but not a structure change; the class keeps those out of a read. The time
limit is kept by the adapter rather than by `max_execution_time`, which bounds
a SELECT only: past it, and on Stop, the statement is killed with
`KILL QUERY` from a second connection. `SELECT SLEEP(n)` answers a kill by
returning early rather than failing, so the outcome is what the adapter did,
not what the server said.

A document's database is the connection's default database, set with
`COM_INIT_DB` after it is found on the server and put back before the pool has
the connection again; a connection that named none is closed instead, since
none cannot be selected again. Warnings the server leaves are the statement's
notices. Results are read as rows of positions, so two columns called `id`
stay two.

Spec: [The MySQL console](../../decisions/2026-10-18-mysql-console-design.md)

## D234. A row is named by its key and versioned by what it showed

The grid edits a MySQL table as it edits a PostgreSQL one (D25, D26), within
three things MySQL lacks.

- **No row address.** A row is named by the key its pages follow (D231): the
  primary key, or a unique key over columns that cannot be null. A table with
  neither takes inserted rows and no edits or deletes, and says why; there is
  no `ctid` to fall back on as D42 does.
- **No row version.** The version in a handle is a digest of the row's values
  as its page showed them. A change locks the row with `FOR UPDATE`, digests
  it the same way, and goes ahead only when the two agree, so a change by
  somebody else to any column refuses this one instead of being written over.
- **No `RETURNING` on an UPDATE.** The row is read again by its key in the
  same transaction — by its new key when a key column was among the cells
  changed — and an inserted row by what was given or by `LAST_INSERT_ID()`.
  A row of a keyless table comes back as what was given.

Every change is one transaction with `STRICT_ALL_TABLES` added for its
duration and the session's own mode put back after: without it MySQL stores
the nearest value a column can hold and says so only in a warning. Values are
checked before anything is written by putting each into a temporary table of
the same column types, a refused batch halved until the refused values are
found, so a block lands whole or the values that cannot are named (D37–D40's
rule of naming rather than counting). A shape is checked on its own, because
MariaDB answers WKT it cannot read with NULL rather than an error.

A value is written back from the text it was shown as: hexadecimal through
`UNHEX`, WKT through `ST_GeomFromText`, a TIMESTAMP's offset to UTC. Binary is
never sent as bytes: aiomysql escapes bytes with a PyMySQL function that
PyMySQL 1.2 replaced by a string. Constraint refusals — a duplicate, a missing
or still referenced row, a required value, a check — are said in words by
their error number.

Following a key works as D110 states, with the target's database read from
the catalog, since a key may point into another database; an arriving key's
handle names the relation it comes from, because a constraint's name is unique
only within its database.

Spec: [Editing MySQL rows](../../decisions/2026-10-18-mysql-rows-design.md)
