# SQLite

A SQLite database file in your personal storage. You browse its tables and
views, read and edit their rows a page at a time, see how a table is built, read the
DDL the file keeps for it and run SQL in a console.
How connections work in general is on the [Connections](connections.md) page.

## What you can see

- Tables, views and virtual tables, and their rows sorted and filtered
- A table's columns, keys, checks and indexes, and the tables it refers to
- A relation's DDL, as the file keeps it, with its indexes and triggers
- The results of SQL you write, and SQLite's plan for a query
- Every matching row, downloaded as a file
- What the file says about itself: layout, integrity, broken keys, triggers
- Where a row's foreign key leads, and what points at it

## What you can change

- Table data: edit cells, paste blocks, insert and delete rows
- Columns, indexes, unique keys and foreign keys
- New tables, designed object by object or made from rows
- Tables and views: rename, drop
- Tables copied with their structure, into another SQLite file or this one
- The whole file, backed up and restored
- Data and structure, through SQL in the console

## Connecting

The **Connection** page of the window asks for:

- **Database file**: the path of the file inside your personal storage, such
  as `data/shop.db`. Put the file there first, through a **Files** connection.
  A path outside your storage is refused.
- **Create the file if it is missing**: tick it to start an empty database.
  Without it, a file that is not there fails the check, so a mistyped path
  does not leave an empty file behind. The folder must already exist.

A database file you already see in a **Files** connection can be connected
from there: **Connect as SQLite** fills this window in for you.

The file is opened afresh for every request, so a file replaced through
**Files** is read as it is now.

What a connection to the file cannot do, whatever the file holds: open a
second file (`ATTACH`, `VACUUM INTO`), load an extension, or reach anything
else on the server. A file is anybody's to upload, so a view or a trigger in
it cannot call a function with side effects either.

## A database of your own

**New connection** offers **Create SQLite here**, with the same two ways a
server is started. **Set it up for me** makes `databases/dataplayer.db` in your
storage, filled with a lab of organizations, people, projects and tasks, and
saves the connection for you. **Let me choose** asks for the name, the folder,
whether to fill it, and whether to use the write-ahead log (WAL). A name
already taken gets a number rather than replacing the file. The file is an
ordinary one: rename, download or delete it in **Files**.

## The catalog

- The first level is `main`, the file's one schema.
- Inside it are its tables, views and virtual tables. Pressing one opens its
  rows in a tab.
- SQLite's own tables (`sqlite_schema`, `sqlite_sequence`, `sqlite_stat1`)
  and the tables a virtual table keeps for itself, such as those of a full-text
  index, are marked as system tables.
- A table says roughly how many rows it holds only after `ANALYZE` has been
  run on the file. Nothing counts the rows.
- **Details** says how many columns, indexes and constraints a relation has.
- **View DDL** shows the `CREATE TABLE` or `CREATE VIEW` statement the file
  keeps, followed by the table's indexes and triggers.
- A virtual table made with a module this server does not have is listed, and
  says so when it is opened.
- **System**, after `main`, is a section of reports (see **Reports** below).
- The search in the header finds tables and views by name, and by their
  columns.

## Reading rows

A table opens as a grid, one page at a time, sorted and filtered as a
PostgreSQL table is. Every column can be sorted. What a column offers depends
on the type it was declared with: comparisons for numbers, dates and text;
contains and starts with for text; empty or not empty for every column.

- Pages follow the primary key, or else the order the rows were written in
  (the `rowid`). A view is in whatever order SQLite returns.
- A `%` or `_` typed into a text filter is looked for as itself. Text filters
  ignore the case of Latin letters.
- A column declared with no type is filtered as text.

How values are shown:

- a value as what it is, whatever its column says: SQLite lets an `INTEGER`
  column hold text, and text is shown as text;
- binary values in hexadecimal, such as `0x00FF`, in any column;
- a `BOOLEAN` column as `true` or `false` where it holds 0 or 1;
- text that is not valid UTF-8 in hexadecimal, rather than with characters
  that are not there;
- large integers exactly.

## Changing rows

With **Edit rows** access, a table is edited in its grid as a PostgreSQL table
is: double-click a cell, paste a block, **Insert row**, tick rows and
**Delete selected rows**. Views, virtual tables and SQLite's own tables are
read only, and a generated column is computed rather than written.

- A row is found again by its primary key, or by its `rowid` when the table
  has none.
- If somebody changed a row after you read it, in any column, your change is
  refused rather than written over theirs. Reload and try again.
- Write values the way the grid shows them: binary as `0x…` in a `BLOB`
  column, `true` or `false` in a `BOOLEAN` one. A column with no type keeps a
  number a number. SQLite stores what any other column is given, converted as
  its type says.
- A `STRICT` table refuses a value of the wrong type before anything is
  written, and the cells that hold such values are named. Nothing of a pasted
  block lands until all of it can.
- A change the table's keys, checks or required columns refuse is not made,
  and says which rule refused it. The file's foreign keys are enforced.
- A cell in a foreign key has an arrow that opens the row it points at, and
  **What points at this row** opens the rows that point here.

## Changing the structure

**Structure** of a table changes it as it changes a PostgreSQL table: add,
rename and drop a column, set or remove its default, require a value or stop
requiring one, change its type, add and drop indexes, unique keys and foreign
keys.

- SQLite itself can only add a column that may be empty and rename one. For
  everything else the table is rebuilt, the way SQLite's documentation
  describes: a new table, the rows copied with their `rowid`, the old one
  replaced, its indexes and triggers made again. What the change does not
  touch — `AUTOINCREMENT`, `DEFERRABLE`, comments — is kept as written.
- A change the rows already contradict is not made, and the count is shown:
  rows with no value, values that repeat, rows that point at nothing.
- A column with a type takes any value in SQLite, so a type change is refused
  only in a `STRICT` table, with the values it cannot hold counted.
- Dropping a column drops the keys and indexes over it. A check or a view that
  reads the column refuses the drop, and says which.
- The types offered are SQLite's: text, integer, floating point, number,
  boolean, date, date and time, JSON, UUID and binary. A `STRICT` table is
  offered its own: text, integer, floating point, binary and any value.
- SQLite builds one kind of index, a B-tree, and names what it makes after the
  table and its columns.

## Creating a table

**Create table** in the actions menu of `main` opens the table designer, as
for PostgreSQL. The plan is a `CREATE TABLE` and one `CREATE INDEX` per index,
run together: the table is made whole or not at all.

- An identity column is SQLite's own row number: an integer that is the whole
  primary key, written `INTEGER PRIMARY KEY AUTOINCREMENT`. It may start
  anywhere, counts one at a time, and takes a value you write into it.
- What SQLite does not have is marked on the object that asks for it before
  you can review the plan: an unlogged or partitioned table, a unique key
  checked at commit, nulls ordered first or last, extra columns carried by an
  index.
- SQLite has what MySQL lacks: an index on part of the rows, a foreign key
  checked at commit, `SET DEFAULT` and an index on an expression.
- Comments are not kept; the plan says so.
- Collations are SQLite's own: `BINARY`, `NOCASE` and `RTRIM`.
- Rows kept as a table, or a file loaded into one, arrive with the table in
  one go.

## Reports

**System** in the catalog holds eight reports. They are read like tables, and
can be sorted, filtered, downloaded and charted. **View the statement** shows
the SQL a report runs.

- **File**: the page size and count, the file's size, free pages, encoding,
  journal mode, auto-vacuum, and the version numbers the file keeps.
- **Integrity**: SQLite's quick check of every page: `ok`, or what is damaged.
  It reads the whole file, so it is read only when opened.
- **Broken foreign keys**: rows whose key points at nothing, written by a
  program that did not enforce them.
- **Triggers**, with their definitions.
- **Functions**, **Modules** and **Collations** this server's SQLite offers,
  and the **Compile options** it was built with.

## Catalog actions

- **Rename** a table or a view. What refers to a table follows it. A view is
  made again under the new name; a view that reads it by its old name refuses
  the rename and is named.
- **Drop** one relation or several together. The drop is tried out first and
  undone, so the question shows what it would do: the triggers that go with
  it, the tables that point at it, the views that read it. If a table that
  points at it still has rows and does not cascade, the drop is refused with
  that reason. Tables that point at each other can be dropped together.
- **Load from CSV** makes a table of a file in `main`, every column as `TEXT`.
- **Model as code** writes `main` or a selection out for an ORM or a diagram.

## Copying tables

**Copy** tables in the catalog and **Paste** them into `main` of another
SQLite connection, or of this one. They arrive with their columns as the file
writes them, their keys, checks, indexes and options such as `STRICT`; the
window asks the same things as on PostgreSQL, shows every statement and runs
nothing before **Copy**.

- Triggers stay behind, named in the window. Views and virtual tables are not
  copied this way.
- An index is named after the new table, since two indexes of one file cannot
  share a name.
- The copy is one transaction: the tables, their rows and their indexes arrive
  together or not at all. A row whose foreign key points at nothing in the copy
  fails it at the end, and nothing is left behind.

Rows pasted into another kind of connection go the way rows of any table do.

## Backups

**Backups**, in the catalog's actions menu, works as on PostgreSQL, for the
file the connection opens.

- The backup is a copy of the file made by SQLite itself, so it is whole even
  while somebody writes to the file.
- **Restore** replaces everything in the file with the backup. A file that is
  not a SQLite database, or that SQLite finds damaged, is refused before
  anything is written.

## SQL console

**New query** under **Queries** on the left rail starts one on the connection,
and **Open as a query** above a table starts one on that table. It works as
the PostgreSQL console does — reads, changes committed at once or held in a
**Manual** transaction, **Explain**, completion and formatting. SQLite changes
structure inside a transaction, so a `CREATE`, `ALTER` or `DROP` is part of
the transaction around it, can be held in a **Manual** one, and is tried out
first and undone before the console asks you about it.

- The schema is always `main`.
- Parameters are written `:name`.
- `ANALYZE`, `VACUUM` and `REINDEX` run on their own, outside a transaction.
- A `PRAGMA` that reports something, such as `PRAGMA table_info(items)` or
  `PRAGMA integrity_check`, is a read. A `PRAGMA` that sets a value is not run.
- Foreign keys the file declares are enforced, which SQLite on its own does
  only when a program asks it to.
- Triggers are not changed from the console, and no other file can be opened
  from it (`ATTACH`).
- **Explain** shows SQLite's plan: one line per step, with no costs, since
  SQLite gives none.
- **Stop** and the time limit end a statement where it is.
- A failed statement inside a transaction you hold leaves the transaction
  open.

## What SQLite does not have here yet

- A file on an SSH server, or inside another connection, cannot be opened as a
  database.
