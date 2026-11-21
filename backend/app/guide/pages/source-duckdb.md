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
- Reports on the file: its size, sequences, types, macros and DuckDB's
  functions
- Every row of a table, a view or a report, downloaded

## What you can change

- Table data: edit cells, paste blocks, insert and delete rows
- Columns, indexes and unique keys
- New tables, designed object by object or made from rows
- Schemas made and dropped; tables and views renamed and dropped
- Tables copied with their structure, into another DuckDB file or this one
- The whole file, backed up and restored
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

## A database of your own

**New connection** offers **Create DuckDB here**, with the same two ways a
server is started. **Set it up for me** makes `databases/dataplayer.duckdb` in
your storage, filled with a lab of organizations, people, projects and tasks,
and saves the connection for you. **Let me choose** asks for the name, the
folder and whether to fill it. A name already taken gets a number rather than
replacing the file. The file is an ordinary one: rename, download or delete it
in **Files**.

A DuckDB file you already see in a **Files** connection can be connected from
there: **Connect as DuckDB** fills this window in for you.

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

## Changing rows

With **Edit rows** access, a table is edited in its grid as a PostgreSQL table
is: double-click a cell, paste a block, **Insert row**, tick rows and
**Delete selected rows**.

- A row is found again by its primary key. A table without one takes new rows
  and is otherwise read only, since DuckDB moves a row when it is updated and
  may hold two identical rows. A view is read only.
- If somebody changed a row after you read it, your change is refused rather
  than written over theirs. Reload and try again.
- Write values the way the grid shows them: a date as `2026-01-02`, a moment
  with its time zone, binary as `0x…`. DuckDB reads them by the column's type,
  and a value it cannot read is refused; in a pasted block the refused cells
  are named and nothing lands.
- Lists, structs, maps and generated columns are not edited in the grid; change
  them with SQL in the console.
- A change the table's keys, checks or required columns refuse is not made,
  and says which rule refused it.
- DuckDB cannot change a key or a unique column of a row that other rows refer
  to, even to a value nobody holds; other columns of that row change.
- A cell in a foreign key has an arrow that opens the row it points at, and
  **What points at this row** opens the rows that point here.

## Changing the structure

**Structure** of a table changes it as it changes a PostgreSQL table: add,
rename and drop a column, set or remove its default, require a value or stop
requiring one, change its type, add and drop indexes, add a unique key.

- DuckDB makes each change in place, in one transaction; nothing is rebuilt.
- A change the rows already contradict is not made, and the count is shown:
  rows with no value, values that would not convert to the new type, values
  that repeat.
- A default is checked against the column's type before it is set.
- DuckDB cannot add a foreign key or a check to a table that already exists,
  and cannot drop any constraint of one, the primary key included. Copy the
  table into one designed the way you want instead.
- A table with an index of its own, or one that another table's foreign key
  points at, takes only a new column, a default and a new index. Renaming,
  dropping or retyping a column, requiring a value and adding a unique key are
  refused.
- DuckDB renames and drops a column without looking at the views that read it,
  so every view is read again after the change, and one the change would break
  refuses it by name.
- What DuckDB refuses itself, such as dropping a column an index covers, is
  said in DuckDB's own words.
- The types offered are DuckDB's: text, integers of four widths, floating
  point, decimal, boolean, date, time, date and time with or without a time
  zone, interval, UUID, JSON and binary.
- DuckDB builds one kind of index, an adaptive radix tree, named after the
  table and its columns. Constraints are named by DuckDB itself.

## Creating a table

**Create table** in the actions menu of a schema opens the table designer, as
for PostgreSQL. The plan is a `CREATE TABLE`, one `CREATE INDEX` per index and
the comments, run together: the table is made whole or not at all.

- An identity column is a sequence of its own, `<table>_<column>_seq`, made
  before the table, and the column's default takes the next value of it. It may
  start anywhere and step by any amount. It takes a value you write into it, so
  it cannot be ALWAYS.
- A generated column is computed whenever it is read; one asked to be stored is
  made that way, with a warning.
- What DuckDB does not have is marked on the object that asks for it before you
  can review the plan: an unlogged or partitioned table, a foreign key that
  cascades, sets null or sets a default, or points into another schema, a key
  checked at commit, an index on part of the rows or carrying extra columns.
- A default is checked against its column's type while the plan is made.
- Constraint names you give are not kept; DuckDB names constraints itself.
- Comments on the table and its columns are kept.
- Collations are DuckDB's own: `NOCASE`, `NOACCENT` and `NFC`.
- Rows kept as a table, or a file loaded into one, arrive with the table in one
  go. A value DuckDB cannot read as its column's type leaves the table unmade.

## Reports

**System** in the catalog holds five reports. They are read like tables, and
can be sorted, filtered, downloaded and charted. **View the statement** shows
the SQL a report runs.

- **Database**: DuckDB's version, the file's size, its blocks used and free,
  and the write-ahead log.
- **Sequences**, with where each starts, its step and bounds. An identity made
  by the table designer is one.
- **Types** of the file's own: enums, structs and other names for a type.
- **Macros**: functions written in SQL and kept in the file, with their
  parameters and body.
- **Functions** DuckDB has built in, and how many signatures each has.
- The engine's settings are not shown: they name folders of the server, and
  they are fixed here.

## Catalog actions

- **New schema** at the top of the connection. **Drop schema** drops any schema
  but `main`; one that holds anything needs **Also drop everything in it**, and
  the question counts what goes. A schema cannot be renamed in DuckDB.
- **Rename** a table or a view. Every view is read again afterwards, and one
  that read the old name refuses the rename and is named. DuckDB refuses to
  rename a table with an index of its own or one another table's key points at.
- A table with a foreign key of its own is not renamed: DuckDB would keep the
  old name in the table it points at, which could then neither delete its rows
  nor be dropped.
- **Drop** one relation or several together. The drop is tried out first and
  undone, so the question names the views that would stop working. A table
  another table's key points at is refused unless that table is dropped with
  it. A sequence only the dropped tables take values from, as an identity's,
  goes with them.
- **Load from CSV** makes a table of a file in the schema, every column as
  `VARCHAR`.
- **Model as code** writes a schema or a selection out for an ORM or a diagram.
- Nothing is moved between schemas: DuckDB cannot.

## Copying tables

**Copy** tables in the catalog and **Paste** them into a schema of another
DuckDB connection, or of this one. They arrive with their columns, defaults,
keys, checks, indexes and comments; the window asks the same things as on
PostgreSQL, shows every statement and runs nothing before **Copy**.

- Every value arrives exactly as it was, lists, structs and maps included. A
  table with a `UNION` column is not copied: its text does not say which member
  a value is.
- A column whose default takes the next value of a sequence, as an identity's,
  gets a sequence of its own in the copy, continuing where the original's
  would.
- DuckDB checks a foreign key at once, so a table is made and filled after the
  tables of the copy it points at. A key can point only into its own schema.
- The copy is one transaction: the tables, their rows and their indexes arrive
  together or not at all.

## Backups

**Backups**, in the catalog's actions menu, works as on PostgreSQL, for the
file the connection opens.

- The backup is a copy of the file, taken after DuckDB has written its log into
  it. While another program writes to the file, the backup is refused.
- **Restore** replaces everything in the file with the backup. A file that is
  not a DuckDB database is refused before anything is written.

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

- A file on an SSH server, or inside another connection, cannot be opened as a
  database.
