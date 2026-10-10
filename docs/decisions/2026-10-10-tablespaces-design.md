# Tablespaces: making, renaming, handing over and removing one

Date: 2026-10-10. Settles D210.

## Problem

The hypertable designer left two things to a spec of their own (D207,
"Deliberately outside"): creating and removing tablespaces, and installing and
removing extensions. Both are PostgreSQL administration rather than Timescale.

What existed: a read-only Tablespaces report (System), and an Extensions
report whose rows already offer Install and Remove (D70). Hypertable settings
attach existing tablespaces (D207) and Move chunks moves chunks into one
(D208), but a tablespace could not be made from DataPlayer.

## Scope

Tablespaces only, decided by the user on 2026-10-10. Updating an extension,
installing one into a chosen schema or version, and removing one with what is
built on it were proposed and left out until somebody needs them.

## Decision

D210. **A tablespace is made, renamed, handed over and removed from the
Tablespaces report, by the owner of the connection.**

- **New tablespace…** above the report's rows, like New role over Roles (D79):
  a name, a location and an optional owner from the server's roles. Level
  `own`: a tablespace is the server's, not one database's.
- **Rename…** and **Change owner…** are about one tablespace, so they are
  offered over one picked row (D209), with the tablespace set and not shown.
  A new place an action can be offered, `picked`, keeps them out of the
  catalog menu and the row above the grid.
- **Remove** in a row's corner (D70), at once, with a question. PostgreSQL
  refuses to drop a tablespace anything is still stored in, from any database,
  so nothing is lost; the refusal says so.
- None of them is offered on `pg_default` or `pg_global`, and a name beginning
  with `pg_` is refused before a statement is sent.
- `CREATE TABLESPACE` and `DROP TABLESPACE` refuse a transaction block, so they
  are sent with none, the way maintenance statements are (D206).
- **The directory is the server's.** DataPlayer cannot list, create or give a
  directory to the operating-system user PostgreSQL runs as. The form says
  what the server needs of the path, and each refusal — no such directory, not
  empty, not absolute, not allowed — is a sentence of DataPlayer's, chosen by
  SQLSTATE rather than the driver's text.

No reviewed plans: each is one statement the server checks itself, and nothing
it refuses leaves a half-done state.

## Rejected

- **Creating the directory through `COPY … TO PROGRAM`.** It needs a
  superuser, runs a shell command on the server, and is what a security review
  should find. Tests use it to prepare a directory; the product does not.
- **Editing a tablespace's options** (`seq_page_cost`, `random_page_cost`,
  `effective_io_concurrency`). Rarely touched; left for when somebody asks.
