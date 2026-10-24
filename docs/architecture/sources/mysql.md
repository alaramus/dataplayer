# MySQL and MariaDB

What a MySQL source is, how it reads its catalog, how its values and pages
cross to the grid, how its rows and structure are changed, and how its SQL
console differs from PostgreSQL's. The contract every source type follows is in
[contract.md](contract.md); reading a relation in general is in
[relations.md](relations.md). The console every source shares is in [querying.md](../querying.md). Read this
before changing the `mysql` adapter.

Decisions here: D228, D229, D230, D231, D232, D233, D234, D235, D236, D237, D238, D239, D240, D241, D242, D243, D244, D245.

## D228. One source type for MySQL and MariaDB, from a stated floor

`mysql` speaks to both servers. They share a protocol, a driver and nearly
all of a dialect, and a person connecting does not choose between them: the
server says which it is in `VERSION()`, and the session reads that once and
keeps it. The catalog shows it as two cards, MySQL and MariaDB, of this one
type ([D264](contract.md#d264-a-source-type-may-show-a-card-per-product)).
Where the two differ — how `information_schema` keeps checks, that
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
`performance_schema` and `sys` are marked as the server's. The node says that
its source calls it a database (`term`), and every screen that picks one —
the catalog's selector, the table designer, copying tables, loading a file,
saving rows as a table — says "database" where it would say "schema".

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
  neither is named by its whole row (D242); there is no `ctid` to fall back
  on as D42 does.
- **No row version.** The version in a handle is a digest of the row's values
  as its page showed them. A change locks the row with `FOR UPDATE`, digests
  it the same way, and goes ahead only when the two agree, so a change by
  somebody else to any column refuses this one instead of being written over.
- **No `RETURNING` on an UPDATE.** The row is read again by its key in the
  same transaction — by its new key when a key column was among the cells
  changed — and an inserted row by what was given or by `LAST_INSERT_ID()`.
  A row inserted into a keyless table comes back as what was given.

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

## D235. A column is changed in the definition the server printed

Columns, indexes and constraints are changed through the same requests as
PostgreSQL's (D27–D40), in MySQL's own statements.

A type or a nullability change is `MODIFY COLUMN`, which takes the whole
definition and keeps nothing it is not given. Rebuilt from the catalog, a
definition loses whatever the rebuild forgot — a default, a comment,
AUTO_INCREMENT, ON UPDATE, a character set. So the definition is the line
`SHOW CREATE TABLE` prints for the column, and the type or the `NULL` marker
in it is replaced, found by the dialect's tokens so a word inside a quoted
default or comment is not touched. The character set stays when text becomes
text and goes when text becomes something else. `DEFAULT NULL` goes when the
column is to require a value.

Every structure statement runs with STRICT_ALL_TABLES added and the session's
mode put back, the rule D234 has for rows: in the server's default mode a
`MODIFY` to a narrower type stores the nearest value it can hold. MySQL has no
TRY_CAST, so how many values a new type refuses is counted only once the
change has been refused: the column is copied with `INSERT IGNORE` into a
temporary column of the new type, and the warnings are the count.

A default is a literal bound by the driver, as D30 has it. The type vocabulary
is MySQL's own: text, long text, integer, big integer, decimal(20,6), double,
boolean as tinyint(1), date, datetime, timestamp, JSON and a UUID as
char(36). The index methods are B-tree, full text and spatial; HASH is not
offered, since InnoDB accepts it and builds a B-tree.

The server names what it makes — `ADD INDEX (…)` and `ADD UNIQUE (…)` by the
first column, a foreign key `<table>_ibfk_<n>` — and the new name is read back
from the table. A unique key and a unique index are one object in MySQL, so a
unique constraint is dropped as its index and the index is dropped through the
constraint. A check is dropped with `DROP CHECK` on MySQL and `DROP
CONSTRAINT` on MariaDB. `SET DEFAULT` on a foreign key is refused, because
InnoDB accepts it and does not carry it out. Rows in the way of NOT NULL, a
unique key or a foreign key are counted first and bounded at a thousand, as
PostgreSQL's are.

Spec: [Changing MySQL structure](../../decisions/2026-10-23-mysql-structure-design.md)

## D236. A designed table is one statement, and a table from rows is undone

The table designer (D117) plans a MySQL table in the same vocabulary as a
PostgreSQL one, and the same composer writes the plan and the statement that
runs, checked by the fingerprint of what was reviewed. The plan is one
`CREATE TABLE` with every key, check, foreign key and index written inside
it: MySQL commits each structure statement by itself (D233), so a plan of
several statements could stop half way and leave a table nobody reviewed.

What MySQL has not got is a problem on the object that asks for it, rather
than a statement the server refuses after the review: a deferrable key, MATCH
FULL, SET DEFAULT, NULLS FIRST or LAST, an operator class, INCLUDE, a partial
index, an unlogged or partitioned table, an array, nulls not distinct, an
identity that is ALWAYS or steps by more than one, and on MariaDB an index on
an expression. The options offer no such choice where a list carries them —
one persistence, one match mode, no SET DEFAULT — and the plan refuses the
checkboxes the designer still draws. An identity is AUTO_INCREMENT, on one
column, leading a key, and its start is the table's `AUTO_INCREMENT=`. A
primary key is always called PRIMARY. A VARCHAR or VARBINARY given no length
is 255 long, since MySQL has no length of its own for them. A literal default is written as MySQL
reads it in the session that will run it, with or without backslash escapes
by NO_BACKSLASH_ESCAPES; an expression default is in parentheses. The clock
and UUID() fill a default only, since MySQL refuses a function that is not
deterministic in a generated column, a check or an index.

A table made from rows (D45) cannot be one transaction with its rows either.
Every value is checked against the chosen types first, as an insert's are
(D234); if the rows are still refused once the table exists, the table this
request made is dropped again.

Known deviations:

- The designer leaves out the hypertable, which its options say MySQL has not
  got at all, but still draws the deferrable and INCLUDE choices, and
  the plan refuses them, rather than the options saying they are not there.

Spec: [Designing MySQL tables](../../decisions/2026-10-23-mysql-design-design.md)

## D237. The server's reports are statements written here, read like a page

A MySQL server's reports (D55) sit in a **System** section after the
databases: processes, variables, status, users, routines, triggers, events and
engines. The section's id begins with a backslash, which no database id can,
since a backslash in a name is written as two (D229). Every report is one
statement in this package, chosen by node id and never composed from a
request. Where the two servers keep an answer in different places — variables
and status in `performance_schema` on MySQL and `information_schema` on
MariaDB, a lock flag that MariaDB's `mysql.user` does not have — a report has
a statement per flavour, and the processes have one more for a MySQL before
8.0.22, which has no `performance_schema.processlist` yet and warns on every
read of the list that replaced it.

A report is paged as a relation is (D231): its statement is a subquery, its
columns are what the server describes for it with `LIMIT 0`, and filters,
sorting and the page are applied over it, in an order of columns the report
names so that page two does not repeat page one. Nothing is written through a
report, a row of one is not a record, and it cannot be made into a relation:
it is a moment of the server. Processes are read again every five seconds and
status every ten.

The processes offer **Cancel query** and **Terminate** (D70) as `KILL QUERY`
and `KILL CONNECTION`, with each id checked to be a whole number and bound. A
connection that has already ended, or one this user may not stop, is reported
by the server's error number rather than its text.

Search by name and by column (D202) is one query of `information_schema`,
words found with `INSTR` under `utf8mb4_bin` and each bound twice, folded by
the word rule and as typed, so the server's accent-blind collations find
nothing the rule does not, and its ranks are ordered before the `LIMIT`. An
export (D45) reads with an unbuffered cursor and closes a connection whose
reader stopped early rather than returning it to the pool mid-result.

Spec: [MySQL reports, search and export](../../decisions/2026-10-23-mysql-reports-design.md)

## D238. Catalog actions are read first, since nothing can be rehearsed

A MySQL catalog offers PostgreSQL's actions where MySQL has them: a new
database at the top, dropping a database, renaming a table or a view, moving a
table to another database, dropping relations, loading a CSV file, a designed
table (D236) and the model as code. MySQL commits every structure statement by
itself (D233), so where PostgreSQL rehearses a drop and rolls it back, a
MySQL preview reads `information_schema` for what the change would meet.

- A drop is blocked while a table outside what is being dropped refers into it
  by a foreign key, and the preview names each key. MySQL would refuse the
  drop; MariaDB drops the tables before the one it refuses, so the check comes
  first on both.
- What is dropped together is one statement per kind, views first, run with
  foreign key checks off for that statement alone: the keys left are only
  between the tables being dropped, and MariaDB refuses a parent named before
  its child.
- A database with anything in it is dropped only with **Also drop everything
  in it** ticked, and its preview counts its tables, views, routines,
  triggers and events. A drop of relations names the triggers that go with
  them and, on MySQL, the views that read them; MariaDB keeps no list of what
  a view reads.
- A view cannot leave its database and a table with triggers cannot either;
  both are refused before the server says so. MySQL has no CASCADE.
- A loaded file's columns are all TEXT: VARCHAR(255) would refuse the first
  long cell. The form, its ceilings and the choice of columns are shared with
  PostgreSQL's in `adapters/csv_load.py`.

Known deviations:

- A database cannot be renamed. MySQL has no statement for it, and moving
  every table leaves the views, routines, triggers and events behind.

Spec: [MySQL catalog actions](../../decisions/2026-10-23-mysql-actions-design.md)

## D239. A table is copied in the lines the server prints

Copy tables (D182) works between MySQL and MariaDB connections in one dialect,
`mysql`. The source describes a table in what `SHOW CREATE TABLE` prints: each
column's definition whole, the primary key, unique keys and indexes as their
lines, checks without their names, and the table's options without its
counter. Those lines keep what separate fields lose — ON UPDATE, a character
set, a prefix length, a functional key. The destination checks that each is one
part of a statement, with no semicolon, comment or open parenthesis, before it
composes its own CREATE TABLE. Foreign keys travel as links, since the window
decides where each one points; one server is one database for keeping a link
on the original, because a MySQL foreign key reaches across databases.

- **Not one transaction.** MySQL commits CREATE TABLE by itself (D233). The
  tables are made, the rows arrive in one transaction, then the links; if
  anything fails or is stopped, the tables this copy made are dropped again.
- **Rows as JSON lines of text.** MySQL has no COPY. A value travels as the text
  the server prints and reads back; a date, a time, a timestamp and JSON as
  the server casts them to text, so a zero date and a negative TIME survive;
  binary values and shapes as the hexadecimal of their stored bytes; a BIT as
  its number. Both ends read and write in UTC (D230), and a zero in an
  AUTO_INCREMENT column stays a zero.
- **Names.** A check and a link are named after the copy, as PostgreSQL's
  are, and kept free in the database, where MySQL wants each once.
- **Left behind:** triggers, named per table. A view, a partitioned table and
  the server's own tables are refused with the reason.

Known deviations:

- MySQL and MariaDB do not know all of each other's words. A definition the
  destination refuses — MariaDB's default collation on MySQL — is refused when
  the copy runs, not when it is planned, and the tables are dropped again.
- A copied table's id in the finished job is composed as
  `database.table` by the shared job, which is wrong for a table whose name
  holds a dot.

Spec: [Copying MySQL tables](../../decisions/2026-10-23-mysql-table-copy-design.md)

## D240. A database is backed up by its own family's dump program

Backups (D87) of a MySQL connection run `mysqldump` and the `mysql` client
from the image of the server's own release, `mysql:8.4`, and MariaDB's own
`mariadb-dump` and `mariadb` from `mariadb:11.4`: a dump by the other family
or an older release may not restore. The password travels in `MYSQL_PWD`,
which both clients read; TLS is as the connection has it (D228), so MariaDB's
client is told not to check the certificate.

- **One database: the one the connection names.** A connection that names
  none is not offered a backup, since a dump of everything its user sees would
  restore into databases the restoring connection never named. A database
  whose name begins with a dash is not offered either: the dump program takes
  it as an argument of its own.
- **The dump** is SQL in one transaction, with routines, triggers and events,
  binary values in hexadecimal, no tablespaces and, on MySQL, no GTID
  statement. **A restore** is the client reading it into the connection's
  database; each table, view and routine in it is dropped and made again.
- **Before a restore** the first lines of the file are read: it must be a dump
  by the same family of server, or nothing runs. Whether a file is a backup at
  all is each source's to say from its first bytes (`restore_archive_reason`),
  since a MySQL dump is text and carries no signature like PostgreSQL's.

Spec: [MySQL backups and metrics](../../decisions/2026-10-23-mysql-backups-metrics-design.md)

## D241. A MySQL connection reports its server's counters

Dashboards (D128) poll a MySQL connection with one `SHOW GLOBAL STATUS`,
which every user may run on both servers, and one read of the database's
size. MySQL keeps its counters for the whole server, so the layout is
*MySQL server*: connections, statements, rows, buffer pool reads, network
traffic, slow queries and aborted connections, and the size of the database
the connection names, or of every database not the server's own.

- **A series may be read from another variable on MariaDB**, which keeps no
  `Innodb_rows_*`: rows read come from `Rows_read` and rows written from its
  handlers' counters.

Spec: [MySQL backups and metrics](../../decisions/2026-10-23-mysql-backups-metrics-design.md)

## D242. A row of a table with no key is named by its values

A table with no primary key and no unique key over columns that cannot be
null is edited all the same. A row's handle carries every value its page
showed, and a change finds the row again by them under `FOR UPDATE`, checks
its digest (D234) and changes it with `LIMIT 1`. Rows that are the same in
every value are the same row to anybody looking, so whichever one the server
finds is the one meant.

- **Found by the columns that compare exactly.** Text, an enum and a set are
  compared as their bytes, since a collation that ignores case would find `A`
  for `a`. A floating-point number, JSON and a shape are left out, since none
  equals the text it was shown as. The digest then tells apart the rows they
  leave alike, and rows alike in every other column but not the same are
  refused with the reason, rather than guessed between.
- **Rows the same in every value** get handles of their own, so a page and a
  selection tell them apart; picking two of three deletes two.
- **A row whose values exceed 64 KB** gets no handle and cannot be edited.

Spec: [MySQL review fixes](../../decisions/2026-10-23-mysql-review-fixes-design.md)

## D243. A MySQL account is made from the Users report

**New user**, above the Users report, makes an account that can sign in: a
name, the host it may connect from (`%` for anywhere) and a password, all
bound as parameters. It grants nothing, or, if asked, SELECT on the database
the connection names. Global privileges, roles and GRANT OPTION are not
offered. Like PostgreSQL's New role (D79) it needs `own`: an account is the
server's, and can sign in through every other connection to it. An account
that exists is a conflict, and a grant the server refuses drops the account
it was meant for.

Spec: [MySQL review fixes](../../decisions/2026-10-23-mysql-review-fixes-design.md)

## D244. A MySQL or MariaDB server is started here signed into as root

**Start MySQL here** and **Start MariaDB here** are service templates (D80):
`mysql:8.4` and `mariadb:11.4`, the releases the source type is tested
against, with their data in `/var/lib/mysql`. The connection a ready service
becomes signs in as the server's root, with a password made up here or
chosen, and opens on the one database the image makes, `dataplayer` unless
another is named.

Root rather than an ordinary account the image could make: PostgreSQL's
template signs in as the superuser its image makes, and a server started for
somebody is theirs whole — New user (D243) and backups (D240) need what only
root holds. The images refuse an ordinary user called root, and make a root
reachable from any host, which on this machine's service network is what the
connection needs. No template runs without a password, as PostgreSQL's does
not.

Spec: [MySQL services](../../decisions/2026-10-23-mysql-services-design.md)

## D245. A server started here may open on a lab of sample data

A MySQL or MariaDB server started with sample data is filled with the lab
PostgreSQL's samples describe — organizations, people, teams, projects, a few
hundred tasks, measurements and an audit trail — in a database of its own,
`demo_lab`, which the script drops first. It is told in what both servers
have, so every screen has something of its own to show: ENUM and SET, JSON,
virtual and stored generated columns, checks, a table partitioned by year,
full-text, prefix and spatial keys, binary values, BIT, TIME and
fractional timestamps, foreign keys with cascades, a view, a function, a
trigger, and a table with no key (D242).

The script ships beside the driver and is split where a line ends in a
semicolon, which it is written so that only a statement's end does; each
statement is sent without parameters, on a connection of its own that is
closed afterwards, since the script chooses its database with USE.

Spec: [MySQL sample data](../../decisions/2026-10-23-mysql-samples-design.md)
