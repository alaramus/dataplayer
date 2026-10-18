# MySQL

A MySQL or MariaDB server. You browse its databases, read tables and views a
page at a time, see how a table is built, read the server's own DDL for it and
run SQL in a console.
How connections work in general is on the [Connections](connections.md) page.

## What you can see

- Databases, tables and views, and their rows sorted and filtered on the server
- A table's columns, keys, checks and indexes, and the tables it refers to
- Where a row's foreign key leads, and what points at it
- A relation's DDL, as the server writes it
- How big a table is, and when it was created and last written to
- The results of SQL you write, and the server's plan for a query

## What you can change

- Table data: edit cells, paste blocks, insert and delete rows
- Data and structure, through SQL in the console

## Connecting

The **Connection** page of the window asks for:

- **Host** and **Port**, 3306 unless the server says otherwise;
- **Authentication**: a user and a password, or a user that has no password;
- **Database**: where the catalog opens. It may be left empty. Every database
  the user may see is in the catalog either way.

A connection string such as `mysql://ann@db.example.com:3306/sales` pasted into
**URL** fills these fields; `mariadb://` is read the same way. A password in
the pasted string goes into the password field and leaves the string.

The connection is encrypted when the server offers TLS, and stays plain when it
does not. The server's certificate is not checked.

MySQL 8.0.16 and later and MariaDB 10.6 and later are supported. An older
server is refused when the connection is checked, with its version named.

## The catalog

- The first level is databases. The one the connection names comes first;
  `mysql`, `information_schema`, `performance_schema` and `sys` belong to the
  server and are marked as such.
- Inside a database are its tables and views. Pressing one opens its rows in a
  tab.
- A table says roughly how many rows it holds. The number is the server's
  estimate, which MySQL may keep for up to a day, and nothing counts the rows.
- **Details** says how many columns, indexes and constraints a relation has,
  how big it is, and when it was created and last written to.
- **View DDL** shows the `CREATE TABLE` or `CREATE VIEW` statement the server
  itself gives.

## Reading rows

A table opens as a grid, one page at a time, sorted and filtered by the server
as a PostgreSQL table is. What a column offers depends on its type: comparisons
for numbers, dates and text; contains and starts with for text; equality and
"one of a list" for enums; empty or not empty for every column.

- Pages follow the primary key. A table without one follows a unique key over
  columns that cannot be empty, the order InnoDB keeps such a table in. A table
  with neither, and a view, is in whatever order the server returns.
- A `%` or `_` typed into a text filter is looked for as itself.

How values are shown:

- `DECIMAL` and large unsigned integers exactly as stored;
- `BIT` as a number;
- `TIMESTAMP` in UTC, with `+00:00`. `DATETIME` as it was written, without a
  time zone, because it has none;
- `TIME` as MySQL writes it, which may be negative or more than 24 hours;
- a zero date such as `0000-00-00` as the server writes it;
- geometry as text, such as `POINT(1 2)`;
- binary columns in hexadecimal, such as `0x00FF`.

## Changing rows

With **Edit rows** access, a table is edited in its grid as a PostgreSQL table
is: double-click a cell, paste a block, **Insert row**, tick rows and
**Delete selected rows**.

- A row is found again by its primary key, or by a unique key over columns
  that cannot be empty. A table with neither accepts new rows and cannot be
  edited or have rows deleted from the grid; the grid says why.
- If somebody changed a row after you read it, in any column, your change is
  refused rather than written over theirs. Reload and try again.
- A value the column cannot hold is refused before anything is written, and
  the cells that hold such values are named. Nothing of a pasted block lands
  until all of it can.
- Write values the way the grid shows them: binary as `0x…`, geometry as WKT
  such as `POINT(1 2)`, a `TIMESTAMP` with its offset.
- A cell in a foreign key has an arrow that opens the row it points at, and
  **What points at this row** opens the rows that point here, in this database
  or another one on the server.

## SQL console

**New query** under **Queries** on the left rail starts one on the connection,
and **Open as a query** above a table starts one on that table. It works as
the PostgreSQL console does — reads, changes committed at once or held in a
**Manual** transaction, **Explain**, completion and formatting — with these
differences:

- The database chosen above the editor is the default one, as `USE` would
  make it; one database at a time.
- Parameters are written `:name`. Every value is sent as text, so a number the
  server needs as a number, such as after `LIMIT`, cannot be a parameter.
- A structure change — `CREATE`, `ALTER`, `DROP`, `TRUNCATE`, `RENAME` — runs
  on its own. MySQL commits it at once, together with anything before it, so
  it cannot share a run with other statements, cannot run inside a transaction
  you are holding, and cannot be tried out first. The console asks before it
  runs one, and says that.
- A statement that fails inside a transaction you hold leaves the transaction
  open; a deadlock ends it.
- **Stop** and the time limit end a statement with `KILL QUERY`.
- Users, grants, routines, triggers and events are not changed from the
  console. `LOAD DATA`, `SELECT … INTO OUTFILE` and `CALL` are not run.

## What MySQL does not have here yet

- Columns, indexes and keys cannot be changed, and tables cannot be created,
  renamed or dropped.
- Only the page on screen can be downloaded, not every matching row.
- Reports about the server, metrics, backups and copying tables between
  connections are not available.
