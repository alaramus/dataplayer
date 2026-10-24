# SQLite

A SQLite database file in your personal storage. You browse its tables and
views, read their rows a page at a time, see how a table is built and read the
DDL the file keeps for it.
How connections work in general is on the [Connections](connections.md) page.

## What you can see

- Tables, views and virtual tables, and their rows sorted and filtered
- A table's columns, keys, checks and indexes, and the tables it refers to
- A relation's DDL, as the file keeps it, with its indexes and triggers

## What you can change

- Nothing yet: rows and structure are read only for now

## Connecting

The **Connection** page of the window asks for:

- **Database file**: the path of the file inside your personal storage, such
  as `data/shop.db`. Put the file there first, through a **Files** connection.
  A path outside your storage is refused.
- **Create the file if it is missing**: tick it to start an empty database.
  Without it, a file that is not there fails the check, so a mistyped path
  does not leave an empty file behind. The folder must already exist.

The file is opened afresh for every request, so a file replaced through
**Files** is read as it is now.

What a connection to the file cannot do, whatever the file holds: open a
second file (`ATTACH`, `VACUUM INTO`), load an extension, or reach anything
else on the server. A file is anybody's to upload, so a view or a trigger in
it cannot call a function with side effects either.

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

## What SQLite does not have here yet

- Editing rows, the SQL console, changing the structure, catalog actions,
  downloading every row, backups and copying tables. They come later.
- A file on an SSH server, or inside another connection, cannot be opened as a
  database.
