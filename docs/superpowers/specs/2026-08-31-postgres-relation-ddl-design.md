# PostgreSQL relation DDL

Date: 2026-08-31. Settles roadmap item 1.5's last implementation slice and D57.

Sources read: `generate_ddl`, `generate_cascade_ddl` and
`postgres_create_table` in the old PostgreSQL adapter; DataPlayer's D22 relation
model, D47 ordered representations, D48 editor boundary, PostgreSQL catalog and
grid panels, and PostgreSQL's `pg_get_*` catalog deparsers.

## Outcome

A PostgreSQL table or view keeps `table` as its preferred representation and
adds source-owned **View DDL** as `sql`. Opening it reads a bounded `SqlContent`
through `SupportsContent` and displays it in a read-only SQL editor surface.
It never calls the editable-content route and has no save command.

The old generator turned its own loosely typed column model back into one
`CREATE TABLE`. That was useful evidence for the workflow but lost view
definitions, quoting, composite constraints and much PostgreSQL syntax. The new
source reads the facts PostgreSQL already knows how to render:

- `format_type` and `pg_get_expr` for columns, defaults and generated values;
- `pg_get_constraintdef` for server-owned constraint syntax;
- `pg_get_indexdef` for indexes not owned by a constraint;
- `pg_get_viewdef` for ordinary and materialized views;
- partition catalogs for `PARTITION BY` and `PARTITION OF`.

All names originate in `pg_catalog` and go through `psycopg.sql.Identifier`.
Owner and relation comment are included. The result is suitable for reading
and as a starting recreation script; it is deliberately not a backup format.

## Why `sql`, not `text`

D47's `kind` is the viewer contract. In the current client, `text`, `json` and
`jsonl` open D48's whole-document editor, whose read returns an opaque version
and whose save replaces the source. A relation's DDL is a derived view of an
object, not its editable source document. Calling it `text` would either send
PostgreSQL to a capability it does not implement or force it to pretend a
derived document can be written back.

`sql` therefore has a distinct discriminated result. The panel reuses the code
surface and SQL language support, but pins it read only and uses `read_content`.
This keeps source capability and screen behaviour aligned.
Successful column, index and constraint mutations invalidate the content query
alongside the relation model and rows, so an open DDL tab re-reads the changed
definition.

## Reaching an alternative representation

Declaring a second representation is not enough when opening a catalog node
always chooses the first. A rows panel opened from the catalog now retains that
source-issued ordered list. The grid shows the first non-table alternative with
the source's exact title and opens it as preferred while retaining the table
alternative, so the SQL panel can return to the grid. Old persisted panels and
tabs opened through a reference have no retained list and show no invented
command.

## Bounds and scope

The response holds at most 256 KB of UTF-8. Each potentially large deparsed
catalog expression is clipped in PostgreSQL, and the assembled document is
clipped again by encoded bytes without cutting through a character. Truncation
keeps the `sql` kind and adds a notice.

This representation includes create syntax, constraints, independent indexes,
owner and relation comment. It excludes grants, triggers, rules, row-security
policies, storage parameters, column comments, identity sequence state and
dependent objects. A child partition is represented by its parent and bounds
plus independent indexes; inherited local overrides are not reconstructed.
Old-style `INHERITS` tables are flattened into the visible standalone shape
rather than retaining their parent relationship. Those omissions are why this
is not the backup/restore feature deferred to Phase 4.

## Tests

Backend tests cover capability declaration, catalog ordering, tables, views,
partitions, exact constraint/index expressions, a missing relation, an
unsupported content kind and a multibyte byte bound. Route coverage reads real
DDL through the public content contract. Frontend tests cover the grid command,
panel registration, bounded read-only display, reload and returning to the
table. The browser scenario opens the connector relation, reads its DDL and
confirms the editor cannot be changed.
