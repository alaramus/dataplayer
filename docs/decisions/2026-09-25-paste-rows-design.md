# Rows pasted into another connection

Date: 2026-09-25. Decision: D166. Extends D164; reuses D43 and D45.

## The problem

A CSV file in a file or SSH connection can already become a table, or add its
rows to one, but only from the file's own grid ("Create table", D45) or from
the table's grid with a picker for the source ("Bring rows in", D43). Paste
should do the same from where the rows are going: copy the CSV, open the
database, Paste. The same holds for a table of one database pasted into
another.

## D166. Rows are pasted as a new table or into a ticked one

Two kinds join the D164 registry. Both read the clipboard as rows through
`SupportsFetch`, so the source is any node a grid can open: a CSV, Parquet or
worksheet file on local disk or SSH, a PostgreSQL table or view, a Redis key.
One node per paste: "Paste one table at a time".

**`rows_new_relation` — "Create a table".** The destination is the place Paste
was chosen in, of a connection implementing `SupportsCreateRelation`. It
needs `structure` there, as D45 does. The window is D45's "Create table" form
with the connection and schema fixed: the name starts from the copied node's
label without its extension, and each source column can be left out, renamed
and given a type from the destination's vocabulary.

**`rows_into_relation` — "Add rows to a table".** The destination is the one
node ticked at the destination, of a connection implementing `SupportsInsert`
and `SupportsFetch`. It needs `write` there, as D43 does. The window is D43's
"Bring rows in" form with the source fixed: each insertable column of the
ticked table is paired with a source column or left as it is, same names
paired to start with, and the first rows can be previewed.

Both are `converts: true`: nothing runs before its window. Execution goes
through D164's `/paste` with the choices of the window, and runs exactly what
D43 and D45 run: the same bounded read (at most 5000 rows), the same check of
every value against its column before one transaction, the same answers. A new
table refuses a source beyond the ceiling; rows added to a table say that the
rest was cut off.

**Folders are left out.** A connection that holds files is not a destination
for either kind. A folder takes a file as it is (D161) or a table as a CSV file
(D165); making a delimited file out of rows, or appending rows to a ticked CSV,
would put a second answer beside those, for the same Paste.

### What the pair answer gains

- The pair names `target_node_id`: the one node ticked at the destination,
  when exactly one is. Kinds that paste into a place ignore it.
- A kind states the level it needs at the destination (`destination_requires`)
  instead of every kind needing `write`.
- An offer names the window it opens (`workflow`: `run`, `file-name`,
  `new-relation`, `into-relation`), and carries what that window needs and
  only the server knows: the source's columns, and the target's insertable
  columns. The client picks a window by `workflow` and names no kind.
- A run carries `name` and `columns` (source, target and, for a new table, a
  type code). Each kind checks the choices it needs.

### Several offers

A CSV pasted into a schema while one table is ticked has two answers: create
a table in the schema, or add the rows to the ticked one. Paste opens a window
listing the usable offers by title, each with the place or node it acts on;
choosing one opens its own window. With a single usable offer Paste goes
straight to it, as before.

## Out of scope

- Pasting within one connection. A PostgreSQL table copied and pasted in its
  own connection still has no Paste (D164's known deviation).
- Type inference, upsert and key matching, as in D43 and D45.
- More than 5000 rows, progress and cancellation: those wait for owned jobs.

## Acceptance

- A CSV copied in the file connection, pasted in a PostgreSQL schema, opens
  "Create table" with the connection and schema fixed and the columns of the
  file; Create makes a table with its rows.
- With a table ticked, Paste lists both offers; "Add rows to a table" opens
  the pairing form, and the rows arrive in the ticked table.
- A table of one PostgreSQL connection pasted into another works the same.
- Without `structure`, "Create a table" is listed unavailable with the reason;
  a value the target cannot read is named and nothing is written.
- In a folder, a copied table still offers only "Save as CSV", and a copied
  file only "Copy files".

Tests cover both kinds against the database, the routes with the permission
cases, the fixed modes of both forms and the list of offers.
