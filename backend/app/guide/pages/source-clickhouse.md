# ClickHouse

A ClickHouse server, reached over its HTTP interface. You browse its
databases, read tables and views a page at a time, see how a table is built,
read the server's own DDL for it and run SQL in a console.
How connections work in general is on the [Connections](connections.md) page.

## What you can see

- Databases, tables, views and materialized views
- Rows sorted and filtered on the server, every value exactly as stored
- A table's columns, its primary and sorting key, skipping indexes and checks
- A relation's DDL, as the server writes it
- How big a table is, how it is partitioned and when it was last written to
- The results of SQL you write, and the server's plan for a query

## What you can change

- Data and structure, through SQL in the console, one change at a time

## Connecting

The **Connection** page of the window asks for:

- **Host** and **Port** of the HTTP interface: 8123, or 8443 with TLS. The
  native port, 9000, is not the one;
- **TLS**: HTTPS, with the server's certificate checked. ClickHouse Cloud
  needs it;
- **Authentication**: a user and a password, or a user that has no password.
  The user is `default` unless you name another;
- **Database**: where the catalog opens. It may be left empty. Every database
  the user may see is in the catalog either way.

A connection string such as `clickhouse://ann@ch.example.com:8123/logs`
pasted into **URL** fills these fields; `https://ch.example.com:8443` is read
too, and `?secure=true` turns on TLS. A password in the pasted string goes
into the password field and leaves the string.

ClickHouse 23.8 and later is supported. An older server is refused when the
connection is checked, with its version named. A user whose profile is
`readonly = 1` cannot be used: every read here sends settings of its own,
which such a user may not.

## The catalog

- The first level is databases. The one the connection names comes first;
  `system` and `information_schema` belong to the server and are marked as
  such.
- Inside a database are its tables, views and materialized views. The table a
  materialized view keeps its rows in is not listed beside it: you read it
  through the view.
- A table says how many rows it holds and how big it is, as the server counts
  them for its MergeTree tables. Other engines say nothing.

## Rows

- Numbers arrive exactly as stored, to the last digit of a `UInt256` or a
  `Decimal`.
- Every moment is shown in UTC with a `Z`, whatever time zone its column
  keeps. A filter value without an offset is read as UTC too.
- Arrays, maps and tuples are shown as JSON.
- A text column holding bytes that are not UTF-8 shows them as replacement
  characters.
- No key of ClickHouse is unique, so a page of a table is ordered by its
  sorting key and then by every other column: the next page never repeats the
  last one. A table whose engine reads from outside — a URL, a file, a stream —
  or that never ends, such as `system.numbers`, is read in the order the
  engine gives.

## SQL console

**New query** under **Queries** on the left rail starts one on the connection,
and **Open as a query** above a table starts one on that table. It works as
the PostgreSQL console does — reads, changes, **Explain**, completion and
formatting — with these differences:

- The database chosen above the editor is the default one; one database at a
  time.
- There is no **Manual** transaction, and nothing is tried out first:
  ClickHouse keeps every change the moment it is made and cannot take it back.
  For the same reason a statement that inserts, deletes, alters or creates
  anything runs on its own. Run a script of changes a statement at a time;
  reads can run together.
- A read runs with the server's `readonly` setting, so the server itself
  refuses anything that would write.
- `ALTER TABLE … DELETE` and `UPDATE` finish before the statement does, so the
  next read already sees the rows changed.
- Parameters are written as ClickHouse writes them, `{name:Type}`. The server
  reads the value as that type and refuses one that does not fit; **SQL null**
  sends NULL to a `Nullable` type.
- `INSERT INTO t FORMAT JSONEachRow` followed by its rows works, as do `SHOW`,
  `DESCRIBE`, `EXISTS`, `CHECK TABLE`, and `EXPLAIN AST`, `SYNTAX`, `PIPELINE`
  and `ESTIMATE`. A plain `EXPLAIN` is **Explain**.
- Not run from here: `SET` and `USE` — put `SETTINGS` on the statement and
  choose the database above the editor instead — `SYSTEM`, `DETACH` and
  `ATTACH`, users, roles, grants, functions, and a `FORMAT` on a `SELECT`, since
  the console shows the result itself.
- **Stop** and the time limit end a statement with `KILL QUERY`.
