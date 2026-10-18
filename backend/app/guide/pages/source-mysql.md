# MySQL

A MySQL or MariaDB server. You browse its databases, read tables and views a
page at a time, see how a table is built and read the server's own DDL for it.
How connections work in general is on the [Connections](connections.md) page.

## What you can see

- Databases, tables and views, and their rows sorted and filtered on the server
- A table's columns, keys, checks and indexes, and the tables it refers to
- A relation's DDL, as the server writes it
- How big a table is, and when it was created and last written to

## What you can change

- Nothing yet: rows and structure are read only for now

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

## What MySQL does not have here yet

- Rows cannot be edited, inserted or deleted.
- Columns, indexes and keys cannot be changed, and tables cannot be created,
  renamed or dropped.
- There is no SQL console.
- A foreign key is shown in the table's structure, but a cell does not lead to
  the row it points at.
- Only the page on screen can be downloaded, not every matching row.
- Reports about the server, metrics, backups and copying tables between
  connections are not available.
