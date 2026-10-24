# SQLite reports, search, export and catalog actions

Decisions D257 and D258. The fifth slice of the SQLite source: what the file
and its library say about themselves, search over the catalog, downloading
every matching row, and the catalog's action menu.

## Reports (D257)

MySQL's reports describe a server: its processes, its accounts, its counters.
A SQLite file has none of those. What it does have is said by its pragmas, so
the reports are those, in a **System** section after `main` with the id
`\system` — no schema's id here begins with a backslash, the only schema being
`main`:

- **File**: page size and count, the size they make, free pages, encoding,
  journal mode, auto-vacuum, the user version, the application id and the
  schema version.
- **Integrity**: `pragma_quick_check`, which reads every page; opened on
  demand only.
- **Broken foreign keys**: `pragma_foreign_key_check`, the rows another
  program wrote with foreign keys off.
- **Triggers**, from `sqlite_schema`.
- **Functions**, **Modules** (without the pragmas, which are modules of their
  own) and **Collations** this library offers.
- **Compile options** of this server's library.

Each is a statement written in the package and read as a subquery with the
page's filters, sorting and paging, as MySQL's are (D237). SQLite names a
result's columns but gives no type for them, so every column of a report is
`other`, its values written by their class (D250), rather than a declared list
that would be a second copy of the select.

Processes, users and server counters have no counterpart and are not offered.

## Search and export

The catalog is a file on this server's disk, so search reads it whole in one
inspection — every relation, and for a column search every column of each —
and classes names in Python with the shared word rule rather than in SQL. Its
cost is cheap for every field. Nothing typed reaches a statement. A report is
found by its title in the reader's language.

An export prepares the same read as a page and takes its rows from one
connection a batch at a time, so they come from one state of the file.

## Catalog actions (D258)

PostgreSQL's catalog actions, where a file has what they act on:

- **Rename** a table or a view.
- **Drop** one relation or a selection.
- **Load from CSV** into `main`.
- **Create table**, the designer (D256).
- **Model as code** for `main`, a table or a view.

No schema is created, renamed, dropped or moved into: a file has `main` and
nothing else (D248). SQLite's own tables offer only the model, and a report
offers nothing.

### Renaming

A table is SQLite's `ALTER TABLE … RENAME TO`, which rewrites the keys, views
and triggers that refer to it. A view has no rename in SQLite. It is made
again under the new name from its own text, edited where its name stands, and
every view is read afterwards: one that read the old name refuses the rename,
by name, rather than being left broken.

### Dropping is rehearsed

MySQL could not rehearse a drop and read `information_schema` instead (D238).
SQLite's structure changes are transactional, so the preview is the drop
itself, rolled back, as PostgreSQL's is. That matters here more than anywhere:
with foreign keys on, dropping a table first deletes its rows, and the keys
pointing at it act as on any delete — a cascade follows, a refusal refuses. A
rehearsal that SQLite refuses blocks the drop with SQLite's reason.

Alongside it the preview lists what goes or breaks: the table's triggers, the
keys of other tables pointing at it, and the views that read it. SQLite keeps
no list of what a view reads, so a view is a reader when its text names the
table as a name — by tokens, so a string or a comment does not count. A column
of the same name is taken for the table, which names a view that may survive;
the safer mistake.

In a selection, tables that point at others of it are dropped first, so a
parent and its child go together.

### Loading a file

The shared CSV loader (D238) with SQLite's names and one schema: every column
TEXT, the table and its rows in one transaction (D256). Asking for a new schema
is refused.
