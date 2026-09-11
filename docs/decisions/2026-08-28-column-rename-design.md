# Column rename

Date: 2026-08-28
Status: agreed
Round: 13

## Goal

Rename one column without recreating it, losing data, or silently removing
dependencies. This is the next DDL slice after add and drop.

## Contract

`RenameColumnRequest` carries `node_id`, the current `name` and `new_name`.
`SupportsRenameColumn` is independent of add and drop: a future source may
allow some of the three and not the others. Whether one particular relation
allows it is still decided by its `column_changes_supported` and the
explanation beside it.

The adapter re-reads the relation model before building a statement. The
current name must exist; the new one must be absent and different. Surrounding
whitespace, and a name longer than 63 UTF-8 bytes, are rejected. Names never
become SQL fragments: PostgreSQL is given nothing but an `Identifier`.

## Dependencies

The statement is `ALTER TABLE <relation> RENAME COLUMN <old> TO <new>`, without
`CASCADE`. This is not add, copy and drop: the column keeps its identity and
its data, and PostgreSQL updates constraints, indexes and catalog dependencies
itself, by its attribute number. The output column names of dependent views are
not rewritten — they belong to the view, not to the source table.

## Interface and caches

Rename sits in the actions of one column's row in Structure. The dialog shows
the old name read-only and accepts a new one. There is no destructive confirm,
because the operation deletes no data, but it is still a separate deliberate
submit.

A success invalidates the relation model and every row query of the connector.
The grid's reconcile drops the old name from the stored layout and takes the
new one from a fresh `FetchResult`. A width or a filter cannot be carried over
automatically, because the client holds no proof of a column's identity.

## Checks

The backend covers the rename itself, dependent metadata, duplicate and unknown
names, the quoted identifier, refusal for a view and for a partition child, and
the absence of the capability. The frontend covers the exact generated-client
payload and the refresh after the mutation.
