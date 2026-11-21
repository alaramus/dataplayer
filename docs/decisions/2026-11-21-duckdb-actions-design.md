# DuckDB reports, search, export and catalog actions

Decisions D398 and D399. The fifth slice of the DuckDB source (D387–D397):
what the file and DuckDB say about themselves, searching the catalog,
downloading every row, and what the catalog can be asked to do. Facts marked
*checked* were tried on DuckDB 2.0.0 on 2026-11-21.

## Reports, search and export (D398)

A **System** section after the schemas, id `\system`, as ClickHouse's and
MySQL's: D229 writes every backslash of a schema's name as two, so no
schema's id begins with a backslash followed by a letter. Its reports:

- **Database** — DuckDB's version and `pragma_database_size()`: size, block
  size, blocks used and free, the write-ahead log. The memory figures are
  left out: they are the server's, not the file's.
- **Sequences** — `duckdb_sequences()`: start, step, bounds, cycling and the
  statement DuckDB keeps. The designer's identities (D397) are here.
- **Types** — `duckdb_types()` that are not internal: the file's own enums,
  structs and aliases.
- **Macros** — `duckdb_functions()` that are not internal: scalar and table
  macros, their parameters and body.
- **Functions** — DuckDB's built-in functions by name and kind, with how many
  signatures each has.
DuckDB's settings are not a report: `home_directory`, `allowed_directories`
and `extension_directory` are paths of the server (D388), and the rest of the
engine's configuration is fixed (D387). Neither are its extensions:
`duckdb_extensions()` reads the extension directory, which the lock refuses
(*checked*: "Cannot access directory"), and nothing beyond the built-in is
loaded here anyway (D388).

Sequences, types and macros were planned as catalog nodes. They are reports
instead: nothing here acts on them yet but the console, a node kind of their
own would be a frontend for each, and a report already lists, filters, sorts
and exports them.

A report is its statement read as a subquery under the page's filters, sort
and paging, its columns typed by `DESCRIBE` of that statement, every value
cast to text as a relation's are (D390). Nothing is written through a report,
no table is made of one, and a row of one is not a record (D111).

**Search** reads every relation of every schema, and for a column search
every column, in one inspection, and classes names with the shared word rule
in Python, as SQLite's (D257): the file is on this server's disk. It starts at
the top, in a schema, or among the reports, which are found by their titles.
**Export** takes the page's read on one connection a batch at a time, so the
rows are one state of the file.

## Catalog actions (D399)

The catalog offers New schema, Drop schema, Rename, Drop, Load from CSV,
Create table (D397) and Model as code. DuckDB's structure changes are
transactional (D393), so every drop is rehearsed: carried out inside a
transaction, described, and rolled back.

**Rename.** `ALTER TABLE … RENAME TO` and `ALTER VIEW … RENAME TO`. Then
every view of the file is bound again inside the same transaction (D396),
since DuckDB renames without looking at the views that read the old name
(*checked*): one that stops binding refuses the rename by name. DuckDB refuses
a table with an index of its own or one another table's foreign key points at
(*checked*: "entries that depend on it"); the refusal says which.

A table that has a **foreign key of its own is not renamed**. DuckDB renames
it, but the table its key points at keeps the old name as the one depending
on it: from then on that table's rows cannot be deleted ("Table with name …
does not exist") and the table cannot be dropped ("main key table of the
table …"), even after the renamed table is dropped and the file reopened
(*checked*). Refusing is the only way not to break a file.

A schema is not renamed: DuckDB has no `ALTER SCHEMA` (*checked*: "Altering
schemas is not yet supported").

**Drop.** Tables and views together, in one transaction. A table another
table's foreign key points at refuses its drop unless that table goes too, in
which case it is dropped first (*checked*: dropping the referencing table and
then the referenced one in one transaction works). DuckDB does not track
views, so a dropped relation leaves the views that read it broken
(*checked*); the rehearsal binds every view after the drop, and the preview
names each that would stop working. What still refuses — a key from outside
the selection — blocks the drop with the reason.

A sequence only the dropped tables take values from goes with them, and the
preview says so. DuckDB leaves it behind (*checked*), and the designer's
identity is such a sequence (D397): without this, every table designed with
an identity and dropped would leave its counter in the file. Which table takes
values from which sequence is `duckdb_dependencies()`, where the sequence is
the one recorded as depending on the table (*checked*).

**New schema** at the top of the connection, beside the others. **Drop
schema** on a schema other than `main`, which DuckDB keeps (*checked*). A
schema holding anything needs "Also drop everything in it", which is
`CASCADE`; the preview counts its tables, views, sequences, types and macros,
and the rehearsal names every view of another schema that would stop working.
No key from another schema can hold it back: DuckDB keeps a foreign key within
its schema (D389).

A rehearsal binds every view after the work, inside its transaction. A view
that fails to bind aborts that transaction (*checked*), so after each broken
view the work is carried out again to try the views after it: as many runs as
broken views, plus one.

**Load from CSV** is a table of `VARCHAR` columns made with its rows in one
transaction (D397's table made from rows), as SQLite's (D258). **Model as
code** writes the selection's relations, a schema standing for its tables and
views, as SQLite's does. No move between schemas: DuckDB's
`ALTER TABLE … SET SCHEMA` does not parse (*checked*).

Names follow D397: 1 to 128 characters, no spaces at either end. DuckDB's
names are compared without regard to case (*checked*: `"Plain"` collides with
`plain`), and so is a taken name here.
