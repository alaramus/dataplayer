# Adding and removing columns

Date: 2026-08-27
Status: agreed
Round: 12

## Goal

Add the first changes to a relation's structure: create one column and drop
one column. The commands must stay part of the adapter contract, must not turn
the frontend into an SQL builder, and after success must update Structure and
Rows in step.

## The main boundary

A column type cannot be passed as an arbitrary SQL string. Unlike a value, a
type occupies a place in the syntax and cannot be a `%s` parameter; plain
substitution would bring back exactly the SQL injection channel that D2c
closes. So the relation model carries a list of `ColumnTypeOption`: a person
sees the title and the SQL spelling, and the client returns only an opaque
`code`. The adapter maps the code to a prebuilt `psycopg.sql.SQL` fragment. An
unknown code is rejected before the statement.

The first PostgreSQL vocabulary holds common scalar types: text, integer,
bigint, numeric, boolean, date, timestamp with time zone, jsonb and uuid. This
is not an attempt to describe all of PostgreSQL. Length, precision, arrays,
domains, enums and composite types will require typed option parameters, not a
text "SQL" field.

## R1. The capability belongs to a specific relation

`SupportsAddColumn` and `SupportsDropColumn` are independent of reading the
structure. `RelationModel` reports `column_changes_supported`, a reason and
type options. PostgreSQL allows the commands for an ordinary table and a
partitioned parent. A view is not a table. A child partition gets a separate
explanation, "change the parent": its columns are inherited, and a local
gesture would create a false expectation.

The type's capability stays in the capability catalog, and a specific relation
may forbid it. The file adapter implements no DDL Protocol and answers 501 on
the route instead of a stub.

## R2. ADD COLUMN receives only structured fields

The command holds `node_id`, name, type code and nullable. The name is checked
again against fresh metadata, limited by PostgreSQL's ceiling of 63 bytes and
passed only through `Identifier`. The type code goes through a closed registry.
Nullability is a boolean that adds a fixed `NOT NULL` token.

A default expression is not part of this round. It has two different meanings:
a literal value and a source expression (`now()`, sequence, function). One text
field would again mix data and syntax. The consequence is stated plainly:
nullable is on by default, and a NOT NULL column on a non-empty table without a
default will be rejected by the source.

## R3. DROP COLUMN gets no CASCADE

Removal addresses an existing column by its exact name and shows a destructive
confirmation. By the table's own rules PostgreSQL will remove the indexes and
constraints that belong to the column; this loss is named in the dialog. But
the statement does not contain `CASCADE`: external dependencies must stop the
action, not vanish as a side effect of one click.

Rename and alter type are not disguised as a combination of add/drop. Rename
preserves identity and dependencies, alter type requires conversion/USING
semantics; these are separate future contracts.

## R4. After DDL two projections go stale

The structure query is reread to show the new model of constraints and
indexes. Row queries of the same connector are invalidated too: the columns
array and every row shape changed at once. Inserting or cutting out one column
locally is not possible — generated metadata and the server-side order are the
source's answer, not a client computation.

## Errors and checking

404 means a vanished relation, 422 — an unsupported relation, a duplicate or
unknown column/type and a safely reduced DDL refusal, 501 — a missing
capability, 502 — a source failure. Backend tests check metadata, add/drop, a
quoted identifier, an unknown type, views, partitions and NOT NULL rejection.
Unit tests check the exact generated-client payload and the confirmation.
Playwright on the real `demo_lab.tags` adds a unique nullable text column, sees
it in Structure, removes it and sees the updated model.
