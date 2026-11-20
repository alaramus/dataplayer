# DuckDB

A DuckDB database file in your personal storage. You browse its schemas,
tables and views, read their rows a page at a time, see how a table is built
and read the DDL the file keeps for it.
How connections work in general is on the [Connections](connections.md) page.

## What you can see

- Schemas, tables and views, and their rows sorted and filtered
- A table's columns, keys, checks and indexes, and the tables it refers to
- A relation's DDL, as the file keeps it, with its indexes
- Lists, structs and maps, shown as JSON
- The results of SQL you write, and DuckDB's plan for a query

## What you can change

- Data and structure, through SQL in the console

## Connecting

The **Connection** page of the window asks for:

- **Database file**: the path of the file inside your personal storage, such
  as `data/shop.duckdb`. Put the file there first, through a **Files**
  connection. A path outside your storage is refused.
- **Create the file if it is missing**: tick it to start an empty database.
  Without it, a file that is not there fails the check, so a mistyped path
  does not leave an empty file behind. The folder must already exist.

The file is opened afresh for every request and closed after it, so between
requests your own DuckDB, a notebook or a script can open it too. While
another program holds it open, this connection says the file is in use.

A file written by a newer DuckDB than this server's may not open, and a file
written by this server, a DuckDB 2, may not open in DuckDB 1.

What a connection to the file cannot do, whatever the file holds: read a file
outside your personal storage, reach the network, install or load an
extension, or spill a large sort to disk. A view in the file that reads a file
elsewhere is refused when it is opened. Files of your own storage are named
from its top with `~/`, such as `~/data/sales.parquet`.

## The catalog

- The first level is the file's schemas, `main` among them.
- Inside each are its tables and views. Pressing one opens its rows in a tab.
- A table says roughly how many rows it holds, as DuckDB estimates without
  counting.
- **Details** says how many columns, indexes and constraints a relation has.
- **View DDL** shows the `CREATE TABLE` or `CREATE VIEW` statement the file
  keeps, followed by the table's indexes.
- DuckDB names constraints itself, such as `items_id_pkey`, even when the
  statement gave one a name.

## Reading rows

A table opens as a grid, one page at a time, sorted and filtered as a
PostgreSQL table is. What a column offers depends on its type: comparisons for
numbers, dates and text; equal or not for UUIDs, enums and intervals; contains
and starts with for text, JSON, lists and structs; empty or not empty for
every column.

- Pages follow the primary key, or else the order DuckDB keeps the rows in.
  A view is in whatever order DuckDB returns.
- A list, a struct or a map cannot be sorted.
- A filter value is read by DuckDB as the column's type: a date as
  `2026-01-02`, a moment with its time zone, a decimal to its last digit. A
  value DuckDB cannot read as that type is refused.
- A `%` or `_` typed into a text filter is looked for as itself. Text filters
  ignore case.

How values are shown, as DuckDB writes them:

- large integers and decimals exactly;
- a moment with a time zone in UTC;
- binary values in hexadecimal, such as `0xAA00`;
- an interval as `1 year 2 days 03:00:00`;
- a list, a struct, a map or a union as JSON.

## SQL console

**New query** under **Queries** on the left rail starts one on the connection,
and **Open as a query** above a table starts one on that table. It works as
the PostgreSQL console does — reads, changes committed at once or held in a
**Manual** transaction, **Explain**, completion and formatting. DuckDB changes
structure inside a transaction, so a `CREATE`, `ALTER` or `DROP` is part of the
transaction around it, and a drop is tried out first and undone before the
console asks you about it.

- Files of your storage are read as `~/…`, such as
  `SELECT * FROM '~/data/sales.parquet'`. Load one into a table with
  `INSERT INTO t SELECT * FROM '~/data/sales.csv'`.
- Parameters are written `$name`.
- The schema is chosen above the editor; `USE` and `SET` are not run.
- Not run, each with its reason: `ATTACH`, `COPY`, `EXPORT` and
  `IMPORT DATABASE`, `INSTALL` and `LOAD`, `PREPARE`, and secrets.
- A failed statement inside a transaction you hold ends it: only **Rollback**
  is left.
- While you hold a transaction the file stays open, and no other program can
  open it.
- Inside a held transaction a drop cannot be tried out first, since DuckDB has
  no savepoints; run it in auto-commit.
- **Explain** shows DuckDB's plan: its operators and the rows it expects.
- **Stop** and the time limit end a statement where it is.

## What DuckDB does not have here yet

- Editing rows, changing the structure, catalog actions, downloading every
  row, backups and copying tables. They come later.
- A table without a primary key will be read only even then: DuckDB moves a
  row when it is updated, so nothing else names it.
- A file on an SSH server, or inside another connection, cannot be opened as a
  database.
