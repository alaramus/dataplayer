# PostgreSQL

A relational database. You browse its schemas, read tables a page at a time,
edit rows and structure, run SQL in a console, and copy data in and out. How
connections work in general is on the [Connections](connections.md) page.

## What you can see

- Schemas, tables and views, and their rows sorted and filtered on the server
- A table's columns, keys and the tables it refers to
- Every matching row, downloaded as a file
- What the server is doing: processes, settings, roles, extensions
- Server metrics on dashboards

## What you can change

- Table data and columns
- Tables and schemas: create, rename, move, drop
- A CSV file loaded into a table
- Roles
- A backup of the whole database
- TimescaleDB hypertables, compression and retention, when it is installed

## Connecting

The **Connection** page of the window asks for:

- **Host** and **Port**, 5432 unless the server says otherwise;
- **Authentication**: a user and a password, or no password for a server that
  trusts the address you connect from;
- **Database**, **User** and **Password**.

A connection string such as `postgresql://ann@db.example.com:5432/sales`
pasted into **URL** fills these fields. A password in the pasted string goes
into the password field and leaves the string.

## The catalog

Pressing the connection opens its catalog.

- The schema control at the top chooses which schemas are listed. Several can be
  listed together; the list then says which schema each row belongs to. The
  choice is remembered in this browser.
- Rows are tables, partitioned tables, views and materialized views. Pressing
  one opens its rows in a tab.
- The filter box narrows the level by name.
- **System** is a section of reports the server gives about itself (see
  **Reports** below).
- Ticking relations and choosing **Relationships** in the actions menu draws
  them and the keys between them as a diagram.
- **Details** says how a relation is stored, who owns it, how many columns,
  indexes and constraints it has, how big it is on disk, and when the server
  last measured it.

Tables in the `pg_` schemas and in `information_schema` belong to the server.
They are read like any other table and are never changed from here.

## Reading rows

A table opens as a grid, one page at a time. The row of commands above it is in
five groups: **The view**, **Read it as**, **Take it out**, **Change the rows**
and **This tab**. A command that cannot be used here stays in its place, greyed,
and says why when you point at it.

- **Sort**: the arrow in a column's header. Several columns can be sorted
  together, in order.
- **Filter**: conditions on columns, joined by AND. What a column offers depends
  on its type: comparisons for numbers, dates and text; contains and starts
  with for text; equality and "one of a list" for booleans, UUIDs and enums;
  empty or not empty for every column.
- **Columns**: pin a column to the left, hide it, change the order, drag its
  edge to resize it, double-click the edge to fit it.
- **Per page**, next to the pager at the foot: up to 500 rows.
- **Refresh automatically** re-reads the page every 1 s to 5 min. It waits while
  a cell is being edited or rows are ticked.
- A cell whose column is part of a foreign key has an arrow. Pressing it shows
  where it leads, and choosing that opens the row it points at.
- **What points at this row** lists the tables whose keys point here and opens
  the matching rows in them.
- **Read this row downwards**, in the corner of a row, shows one row as a
  column of names and values. Its arrows walk to the next and previous rows.
- A JSON or array value opens whole in a viewer when you double-click it;
  Shift + double-click edits it. **Copy the full value** copies it.
- Ticking cells and pressing Ctrl+C copies them as tab-separated text.

The filters, sort and columns of a table are remembered in this browser.

## The structure of a table

**Structure** opens the columns, keys, indexes and constraints of the table
beside its rows.

With **Change structure** access you can:

- add a column, rename it, drop it, change its type;
- set or drop its default value, and allow or forbid empty values. Forbidding
  them first counts the rows that are empty and stops if there are any;
- add or drop an index;
- add or drop a unique key or a foreign key.

**View DDL**, above the rows, shows the SQL that would create the table again.
**Model as code**, in the catalog's actions menu, writes a schema or a table as
a SQLAlchemy model, a Django model or a DBML document and downloads it.

## Editing rows

With **Edit rows** access:

- double-click a cell to change it. **Set SQL NULL** stores an empty value,
  which is not the same as empty text;
- **Insert row** adds a row at the end of the page. Columns with a default can
  be left alone;
- tick whole rows and press **Delete selected rows**. All of them are deleted,
  or none;
- paste a block of copied cells into a selection with
  **Paste into the selection**. Every value is checked against its column's
  type first, and nothing is written if one fails.

If somebody changed a row after you read it, your change is refused rather than
written over theirs. Reload and try again.

Rows can be deleted only from a table with a primary key. Views are read only.

## Tables and schemas

The catalog's actions menu, on a schema or on ticked relations, offers:

- **New schema**, **Rename schema**, **Drop schema**;
- **Create table**: design the columns, keys and indexes, review the SQL it
  will run, then create it;
- **Rename**, **Move to schema**, **Drop**. Dropping several relations at once
  is one step: they all go, or none of them does.

What a drop would take with it is shown before you confirm.

## Bringing data in and taking it out

- **Load from CSV**, on a schema: upload a CSV file and make a table of it.
- **Bring rows in**, above a table: choose a table in any connection, pair its
  columns with this table's, preview, and copy the rows in.
- **Keep these rows as a new table or file** copies the rows on screen into a
  new table in another connection, or into a CSV file in a folder.
- **Download** asks for **Current page** or **All matching rows**, and whether
  to download the file or **Save to my files**.
- **Copy** tables in the catalog and **Paste** them into a schema of another
  PostgreSQL connection: they are copied with their columns, keys and indexes.
  Whether the foreign keys between them come along is asked.
- Pasting copied tables into a folder of a file or SSH connection saves each as
  a CSV file.

Long copies run in the background. The activity bell shows how they are going
and can stop them.

## The SQL console

**Queries**, on the left rail, lists your saved queries and starts a
**New query** on a connection. **Open as a query** above a table starts one on
that table.

- **Run** runs the selection, or the statement under the cursor. **Run script**
  runs the whole text.
- Results are shown under the editor and can be paged, filtered, sorted,
  downloaded and charted.
- **Explain** shows the plan of a statement without running it.
- Changes are committed at once, unless **Manual** is switched on. Then the
  console holds a transaction open until **Commit** or **Roll back**.
- The connection's **Consoles** setting decides whether
  changes are allowed, asked about each time, or refused.
- Changing the structure (tables, views, indexes, schemas) is always asked
  about. A destructive change is tried inside a transaction first, and you are
  shown what it would do.
- The editor completes schema, table and column names.
- Every run is kept in the query's history.

## Reports

**System** in the catalog holds six reports about the server. They are read
like tables, and can be sorted, filtered, downloaded and charted.

- **Processes**: what is connected and what each connection is doing. Each row
  has **Cancel query** and **Terminate**. The report re-reads itself every five
  seconds.
- **Settings**: the server's configuration.
- **Tablespaces**, **Routines**.
- **Roles**: the server's users. **New role** above the rows makes one. Only the
  connection's owner has it.
- **Extensions**: what can be installed and what is. Each row has **Install**
  or **Remove**.

## Backups

**Backups**, in the catalog's actions menu, lists the backups of this database
kept in your personal storage.

- **Copy this database out** makes a new one. It runs in the background.
- **Restore** puts one back into this database. It replaces the objects the
  backup holds, and asks first.
- **Delete this backup** removes one.

Only the connection's owner can back it up. The button is greyed out when this
installation cannot run the backup program.

## TimescaleDB

When the database has the TimescaleDB extension, hypertables and continuous
aggregates are marked in the catalog, and the actions menu of a hypertable
offers:

- **Change chunk interval**, **Configure compression**;
- **Set retention policy**, **Set compression policy**, **Set refresh policy**,
  and removing each of them;
- **Compress chunks**, **Decompress chunks**;
- **Convert to hypertable**, on an ordinary table.

Work that touches many chunks is planned first and shown for review before it
runs. It then runs in the background, and the activity bell shows how far it
has got and what happened to each chunk.

## Metrics

A PostgreSQL connection can report its own counters to dashboards: sessions by
state, transactions, rows read and written, blocks read from disk and from
memory, conflicts, deadlocks and the size of the database. The owner switches
this on in the **Sources** window of the **Dashboards** space, and chooses how
often. The ready-made layout for it is called **PostgreSQL database**.

## Limits

- A page of rows holds at most 500 rows.
- A pasted block is at most 500 rows and 2000 cells.
- Deleting works on the rows of the page you are on.
- Filters are joined by AND. There is no OR.
