# Loading a CSV as a new table

## Problem

D43 moves rows from one source into a relation of another, and its first
sentence says what it does not do: the target has to exist already. The case it
was built for — a CSV — usually has no table waiting for it, so the reader has
to create one by hand, column by column, guessing at the names in the file,
before the move it actually wanted.

The reader is not holding the file in personal storage either. They have it on
their machine, they are looking at the catalog of a database, and what they
want is one button there.

## It is an action, and that is the whole design

The catalog column already has a menu of what the source can do. What is in it,
what each line's form holds, whether a line carries a file, which nodes admit
it and what access it needs are all read off the source's own declaration
(D9, D13). So this feature is one class in the PostgreSQL adapter, and the
screen needed **no change at all** to grow a "Load from CSV" button that opens
a window with a file picker and a name field.

That is worth stating plainly, because it is the return on two earlier
decisions. A route of its own would have meant a dialog of its own, a button
placed by hand, and a screen that knows one source type by name.

## Creating a relation is a capability, not the action's own SQL

`SupportsCreateRelation`:

- `new_relation_options(parent_node_id)` — what this container will accept a
  new relation with: `supported`, a `reason` when not, and the
  `ColumnTypeOption` list D27 publishes for a column added to a relation that
  exists.
- `create_relation(request)` — a name, an opaque container id, a list of
  `(name, type_code)`, and the rows.

One capability with two methods because either alone is useless. Asked of a
*container* rather than of a relation because there is no relation yet, and
that is also what lets `pg_catalog` refuse in its own words rather than be
quietly missing from a list. The action reads the same answer to decide whether
to offer itself on a schema, so the gate is written once.

## The relation and its rows are one request

`create_relation` carries the rows. That is the decision worth arguing about,
since it makes one method do two things.

The alternative is two requests: create, then insert through `SupportsInsert`.
It fails on the case this exists for. A file written by somebody else regularly
holds a value the column cannot take, and with two requests that leaves an
empty table nobody asked for, in a platform that deliberately has no way to
drop one.

Only the source can put the DDL and the rows in one transaction. PostgreSQL
rolls DDL back like anything else, so `CREATE TABLE` and the inserts commit
together or not at all. `Transaction` gained a `schema_change` for this:
`change` fetches, and a statement that returns no rows would fail inside the
cursor rather than at the source.

The values are checked before either statement runs, by the same
`pg_input_is_valid` pass D41 and D43 make, and `ValuesRejected` is reused
rather than restated.

## Every column is text

A delimited file states no types. The file source already says so, in the
comment above the reader that refuses to guess one: a type read off the first
page depends on where the reading stopped. The same holds here with more
force — a guess that is wrong on row 4001 turns into a failed load, while text
always arrives and D38 changes a column's type afterwards, counting the rows in
the way before it locks anything.

So the form has one field: the name of the table, defaulting to the file's own
name without its extension.

## The reading is shared

`adapters/delimited` holds what both sources need: the delimiter rule, the
naming of a header written by hand — empty and repeated names are the normal
case — and the fitting of a short row to the header. The file source pages a
file through it; this action takes a whole one. Neither adapter imports the
other, which is the point.

## Both ceilings refuse rather than truncate

At most 5000 rows, and at most 16 MB read before the file is refused. D43
truncates and says so, because it samples a source that goes on existing; here
the reader handed over a whole file and a part of one arriving would go
unnoticed. Anything larger is the durable job of Phase 4, and a bigger number
would only move where the request times out.

The file is held whole while it is parsed, which is what the byte ceiling is
for. Staging it on disk would buy a larger ceiling and no new capability.

## Where the table goes

An action that makes something *inside* — a new folder, an upload, a loaded
table — is offered for the places whose contents are on screen. For a personal
directory that is the level being looked at, as before. For a database it is
the schemas ticked in the filter above the list, because a schema is a grouping
rather than a folder one walks into (D12) and the level itself holds nothing.

`toMenu` therefore takes places rather than one level. The change cannot
regress the file source, which has no groupings, and for a database it turns
"no such action offered anywhere" into "offered in the schema you are reading".

With two schemas ticked the line greys out, exactly as renaming two folders to
one name does: one file is one table, and `bulk` is what says so.

## Follow-up: the destination may be a folder

The grid gained the other half of this — rows already on screen kept as a new
relation — and it went first to a database, because that is where a relation
is made. Asked for later: those rows kept as a file, which is what the reader
wants when they were reading files to begin with.

It changed no contract. `SupportsCreateRelation` is implemented by the file
source, whose container is a folder and whose relation is a delimited file, so
the route, the request, the ceilings and the result are the ones above. What
had to be thought about was smaller and all on the screen:

- **One type, so no type control.** A delimited file states no types and every
  value read out of one is text, which the capability already says in
  `column_type_options`. The form draws the column's type only when there is
  more than one, because a list of one is a control that does nothing.
- **The words follow the destination, not the source.** A schema takes a table
  and a folder takes a file. The catalog says which of the two a node is, so
  the heading, the labels and the button read off the picked node — and the
  window's heading changes while the window is open, which is a thing the
  floating windows could not do before.
- **The list holds only what could take one.** `create_relation` became a
  capability code, so a connection that would answer 501 to the first question
  the form asks is not offered as a destination at all.
- **What is a folder is not "what has children".** A workbook and an archive
  are walked into like a folder (D51, D53 in the source contract) and
  neither can be written a file into, so the form offers directories.
- **Atomicity by the means at hand.** The database half is one transaction; the
  file half writes beside the destination and links into place, which refuses a
  taken name at the same moment it publishes and leaves nothing behind when it
  fails.

## Deliberate boundary

- **Nothing but a name.** No types in the form, no NOT NULL, no default, no key
  and no index. Each of those already has a command against an existing
  relation, and each answers with what stands in its way.
- **A taken name is refused, never replaced**, and nothing is dropped here.
  Removing a relation is D46, which asks first.
- **No transformation**, as in D43: a value crosses as the text the file held.
