# Inserting and deleting rows

Date: 2026-08-27
Status: agreed
Round: 11

## Goal

Add two separate commands to the grid: insert one row without losing the
source's defaults, and delete the selected rows as one confirmed operation.
Both commands continue the D25 boundary: the client does not build SQL, does
not parse a row handle and does not guess PostgreSQL's capabilities from the
source type's name.

## Why these are not variants of update

The three operations mean different things. Update changes one known value and
requires the version of one existing row. Insert works with a row that does not
exist yet and must distinguish an absent field, SQL `NULL` and text. Delete
carries no new values, but has to determine the transactional fate of the whole
selection. A combined command would get many mutually exclusive optional fields
and would hide these differences in conditional branches.

## R1. Insertion passes only explicitly given fields

`InsertRowRequest` holds `node_id` and a list of `{column, value}`. A column
not in the list — the source applies its default. A column present with the
value `null` — that is SQL `NULL`. An empty string stays an empty string. A
list rather than a JSON object was chosen because the boundary model checks
duplicates and keeps an explicit order of the statement's parameters.

`FetchColumn` reports `insertable`, `insert_required` and `has_default`.
Generated and identity always columns are not entered; required means
insertable, NOT NULL and without a default. Identity by default can be given
explicitly, but the form omits it by default. PostgreSQL rereads the metadata
before the command, so a stale form cannot insert an unknown or since-generated
column.

In the form, required fields are always on. An optional field has to be
switched on first; after that a nullable field can separately be made SQL
`NULL`. Boolean and enum use a closed choice, other values stay canonical text
and are finally validated by the source. Success returns the whole row through
`RETURNING`, including generated/default values, and a row handle if the table
has a primary key. The page is reread, because the new row may not pass the
current filter or may land on another page of the sort.

## R2. Only a full row of the selection is deleted

An ordinary range of cells must not be mistaken for a list of rows. Delete is
enabled only if every range covers all visible columns; the indexes of
overlapping ranges are deduplicated. Then an opaque handle is required for each
row. Before the request a destructive confirmation with the exact number of
rows is shown.

Hidden columns do not get in the way: completeness here means a row as a grid
gesture, and identity is carried by the server handle anyway. Selection and
deletion are limited to the current page, as copying is; a "delete everything
matching the filter" command would be a different, more dangerous contract
with its own preview.

## R3. Bulk delete is atomic

The request carries from one to 500 handles. PostgreSQL decodes them inside the
adapter and in one statement matches the primary key together with `xmin`.
`DELETE` is allowed only when the number of current rows found equals the
number requested. If even one row has changed or disappeared, zero are deleted
and the API answers 409. Duplicates are forbidden before the statement.

Partial success is rejected. The user confirmed one action on one selection;
after a partial deletion the result of each row would have to be explained
separately and consent asked again for the remainder. All-or-nothing leaves a
single recovery after a conflict: reread the page and select the current rows
again.

## Capabilities and errors

`SupportsInsert` and `SupportsDelete` are independent. PostgreSQL inserts into
ordinary and partitioned tables even without a primary key; it deletes only
when there is a key. The file source stays read-only and reports the reason.
422 means a wrong relation, column, handle or a rejected value; 409 — a version
conflict of a bulk delete; 501 — the type lacks the capability; 502 — a safely
reduced source refusal.

## Checking

Backend tests prove defaults, a generated value, an explicit NULL, required and
unknown fields, deleting several rows and a zero effect with one stale handle.
Unit tests check the completeness of a row selection and the exact payloads of
both commands. Playwright filters `demo_lab.tags` down to an empty result,
inserts a row without `color`, sees the PostgreSQL default, selects the whole
row, confirms deletion and sees the empty result again.
