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
- Every matching row, downloaded as a file
- What the server is doing: processes, variables, status, users, routines,
  triggers, events and engines

## What you can change

- Table data: edit cells, paste blocks, insert and delete rows
- Columns, indexes, unique keys and foreign keys
- New tables, designed object by object or made from rows
- Data and structure, through SQL in the console
- What another connection is running: its statement can be stopped, or the
  connection closed
- Databases: create and drop them
- Tables and views: rename, move a table to another database, drop
- Tables copied with their structure to another MySQL or MariaDB connection
- Backups of the connection's database, and the database put back from one

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
- **System**, after the databases, is a section of reports the server gives
  about itself (see **Reports** below).
- The search in the header finds databases and tables by name, and tables by
  their columns and the comments on them and their columns.

## Reading rows

A table opens as a grid, one page at a time, sorted and filtered by the server
as a PostgreSQL table is. What a column offers depends on its type: comparisons
for numbers, dates and text; contains and starts with for text; equality and
"one of a list" for enums; empty or not empty for every column.

- Pages follow the primary key. A table without one follows a unique key over
  columns that cannot be empty, the order InnoDB keeps such a table in. A table
  with neither, and a view, is in whatever order the server returns.
- A `%` or `_` typed into a text filter is looked for as itself.
- **Download** asks for **Current page** or **All matching rows**. Every row is
  read from the server as it is written to the file, in the page's order and
  with its filters.

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
  that cannot be empty. A row of a table with neither is found by all its
  values, and one row is changed at a time: rows the same in every value are
  interchangeable. Two rows that differ only in a floating-point, JSON or
  geometry column cannot be told apart, and a change to one is refused with
  that reason.
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

## Changing the structure

**Structure** of a table changes it as it changes a PostgreSQL table: add,
rename and drop a column, set or remove its default, require a value or stop
requiring one, change its type, add and drop indexes, unique keys and foreign
keys.

- Everything else about a column — its default, comment, character set,
  AUTO_INCREMENT — is kept when its type or nullability changes.
- A change the rows already contradict is not made, and the count is shown:
  rows with no value, values that repeat, rows that point at nothing, values
  the new type cannot hold. MySQL can only count the last after it has tried
  the change and been refused; nothing is changed either way.
- The types offered are MySQL's: text, long text, integer, big integer,
  decimal, floating point, boolean as 0 or 1, date, date and time, timestamp,
  JSON, and a UUID as text.
- Indexes are B-tree, full text (text columns only) or spatial (one geometry
  column that requires a value). MySQL names a new index or key itself.
- A unique key and its index are one thing in MySQL; drop it as the key.
- `SET DEFAULT` is not offered for a foreign key: InnoDB does not carry it
  out.

## Creating a table

**Create table** in the actions menu of a database opens the table designer,
as for PostgreSQL. The plan is one `CREATE TABLE` with every key, check,
foreign key and index inside it, so the table is made whole or not at all.

- What MySQL does not have is marked on the object that asks for it before
  you can review the plan: a deferrable key, extra columns carried by an
  index, an index on part of the rows, nulls ordered first or last, an
  unlogged or partitioned table.
- An identity column is AUTO_INCREMENT: one per table, leading a key, with a
  start but no step of its own.
- A primary key is always called PRIMARY.
- Rows kept as a table, or a file loaded into one, are checked against the
  chosen types before the table is made; if they are still refused, the new
  table is removed again.

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

## Reports

**System** in the catalog holds eight reports about the server. They are read
like tables, and can be sorted, filtered, downloaded and charted. **View the
statement** shows the SQL a report runs.

- **Processes**: the connections open now and what each is running. Each row
  has **Cancel query**, which stops the statement and keeps the connection,
  and **Terminate**, which closes the connection. The report re-reads itself
  every five seconds.
- **Variables**: every global setting of the server.
- **Status**: the counters the server keeps since it started. It re-reads
  itself every ten seconds.
- **Users**: the accounts that may connect, and from which hosts. **New user**
  above the rows makes one: a name, the host it may connect from (`%` for
  anywhere) and a password. It is granted nothing, or, if ticked, reading of
  the connection's database. Only the connection's owner has it.
- **Routines** and **Triggers** outside the server's own databases, and the
  **Events** its scheduler runs.
- **Engines**: the storage engines the server offers, and which is the default.

A report shows only what the connection's user may see: a user without the
`PROCESS` privilege sees only its own connections, and **Users** is refused to
one that cannot read the `mysql` database.

## Catalog actions

- **New database**, at the top of the catalog.
- **Drop database** asks first. A database that holds anything is dropped only
  with **Also drop everything in it** ticked, and what it holds is counted
  before you confirm.
- **Rename** a table or a view. Foreign keys pointing at a table follow it.
- **Move to database** moves a table. A view, and a table with triggers, stay
  in their database.
- **Drop** one relation or several together. A table that a table outside the
  selection refers to is not dropped, and the tables that refer to it are
  named. On MySQL the views that read a dropped table are named too.
- **Load from CSV** makes a table of a file, every column as `TEXT`.
- **Model as code** writes a database or a selection out for an ORM or a
  diagram.

Changes to the structure are not rehearsed first, as on PostgreSQL: MySQL
commits them at once.

## Copying tables

**Copy** tables in the catalog and **Paste** them into a database of another
MySQL or MariaDB connection, or of this one. They arrive with their columns,
keys, indexes, checks and options; the window asks the same things as on
PostgreSQL, shows every statement and runs nothing before **Copy**.

- Triggers stay behind, named in the window. Views and partitioned tables are
  not copied this way.
- The tables are made first and the rows arrive afterwards. If the copy fails
  or is stopped, the tables it made are dropped again.
- MariaDB uses a collation MySQL does not have, so a table copied from
  MariaDB to MySQL may be refused; the window says which step refused it.

Rows pasted into another kind of connection go the way rows of any table do.

## Backups

**Backups**, in the catalog's actions menu, works as on PostgreSQL, for the
database the connection names. A connection that names no database is not
offered one.

- The backup is a SQL file written by `mysqldump`, or by `mariadb-dump` for
  MariaDB, of the server's own release, with routines, triggers and events.
- **Restore** drops and makes again every table, view and routine the backup
  holds. A backup made from MariaDB is restored only into MariaDB, and one made
  from MySQL only into MySQL.

## Dashboards

A MySQL connection can report to dashboards. The layout is **MySQL server**:
connections, statements, rows, buffer pool reads, network traffic, slow
queries and aborted connections, and the size of the connection's database.
The counters are the whole server's: MySQL does not keep them per database.

## A server of your own

**New connection** offers **Start MySQL here** and **Start MariaDB here**: a
server started on this machine, saved as a connection signed into as its
root. With sample data, it opens on `demo_lab` — organizations, people,
projects, a few hundred tasks and measurements — with something on it for
every screen: generated columns, JSON, a partitioned table, full-text and
spatial keys, a view, a trigger, and a table with no key.

## What MySQL does not have here yet

- A database cannot be renamed; MySQL has no way to do it.
