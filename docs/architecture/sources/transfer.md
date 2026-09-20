# Moving rows in and out of a relation

Copying rows from one source into another, loading a file into a relation, and
streaming every matching row out. Reading a relation and editing the rows in it
are in [relations.md](relations.md); the grid's own current-page download is in
[../grid.md](../grid.md).

Decisions here: D43, D45, D44.

## D43. Rows move between sources through the platform

The first command naming two connectors. It lives in the `connectors` module
rather than in an adapter, because an adapter knows itself and nothing else, and
asking one to read another would be the first crack in that.

- Two connectors mean two permissions, checked separately against the grants of
  D33 — writing rows into the target, reading the node in the source. Neither
  implies the other.
- It is not an import of a file: the file source is one readable source among
  several and the relation one writable target among several.
- The read has a ceiling of 5000 rows and pages the source at its own limit to
  reach it. More is not refused — that would make the command useless — but the
  answer says the rows were cut off.
- Columns are paired explicitly, source column to target column, and both sides
  are validated against what each says it has before anything is read. Matching
  by position or by equal names would turn a wrong import into one that looks
  right.
- The target checks every value against its column's type before writing, the
  same pass D41 makes, and answers with the cells that cannot be read: row,
  column and the value itself, cut short. Then one transaction; a partial import
  is impossible, which is why there is no downloadable error report.
- `preview` reads the first rows through the same mapping and hands them back.
  It answers "have I paired these columns correctly" and deliberately does not
  validate against the target.
- The same bounded read can prepare a relation that does not exist yet: the
  route asks the target container's `SupportsCreateRelation` for its type
  vocabulary, then passes an explicit mapping to `create_relation`. Creation
  refuses a source beyond the ceiling, because a new table made from only the
  first part of one would carry a false identity.

Known deviations:

- **No transformation.** A value crosses as the text the source gave or it does
  not cross. Trimming, date formats and decimal separators need a vocabulary.
- **No upsert and no key matching.** Existing targets receive inserts; a new
  target receives plain columns and rows, with constraints left to
  [D40](ddl.md).

Spec: [Bringing rows from one source into another](../../decisions/2026-08-30-row-import-design.md)

## D45. A file becomes a table in one transaction

D43 moves rows into a relation that already exists; this is the half a reader
rarely has. It is a catalog action ([D9](actions.md)) rather than a route of its
own, so nothing on the screen learned anything about PostgreSQL.

- `SupportsCreateRelation` has two methods and is one capability because either
  alone is useless: `new_relation_options` says what a container will accept a
  new relation with — `supported`, a `reason` when not, and D27's
  `ColumnTypeOption` list — and `create_relation` makes it. Asking a *container*
  is what lets a schema the server owns say why it admits nothing.
- The rows travel with the request. With a separate create and insert, a value
  the column could not take would leave behind an empty relation nobody asked
  for, and this platform has no way to drop one. PostgreSQL rolls DDL back like
  anything else, so either the table arrives with its rows or nothing is made.
  `Transaction` gained `schema_change` for this: `change` fetches, and a
  statement returning no rows would fail inside the cursor.
- Every value is checked first by the same `pg_input_is_valid` pass D41 and D43
  make, and rejected cells come back in `ValuesRejected`.
- Every column is text. A delimited file states no types, and one read off its
  rows would depend on how many were looked at. A column takes another type
  afterwards through [D38](ddl.md), which counts the rows in the way first.
- `adapters/delimited` holds the delimiter rule, the naming of a header written
  by hand and the fitting of a short row. The file source pages a file through
  it and this action takes a whole one; neither adapter imports the other.
- Both ceilings refuse rather than truncate: at most 5000 rows and 16 MB. D43
  truncates because it samples a live source; here the reader handed over a whole
  file, and a part of one arriving would go unnoticed.
- The schema being looked at is the initial destination, not a hidden constraint;
  the workflow can request a new one, and PostgreSQL may refuse for privilege.
  The table name starts as the filename without its extension, and columns may
  be omitted or renamed before the file is sent.
- **A source that keeps files takes one too, and it is a delimited file.** A
  folder has no CREATE TABLE and needs none: rows under named columns are a
  CSV. The same capability, the same route and the same form — only the
  container is a folder, the type vocabulary has the single entry a delimited
  file can honestly offer, and the extension is added when the name carries
  none, because `orders` alone opens as a document.
- **Atomic by the means the source has.** The file is built beside its
  destination and linked into place, so a failure leaves nothing half-written
  and a name already taken is refused by the link rather than by a check that
  something could slip past. It is what the transaction is for the database
  half, stated in the only terms a filesystem has.
- **The form is worded by the destination, never by the type of the source.**
  A schema takes a table and a folder takes a file, and the catalog already
  says which of the two a node is; the heading, the labels and the button read
  off that. Which connections are offered at all is read off the capability's
  code, so a source that would answer 501 is not in the list. Where a source
  publishes one column type, the column's type control is not drawn: a list of
  one is a control that does nothing.

Known deviations:

- **No inferred structure beyond names.** No inferred type, NOT NULL, default,
  key or index; each has a command of its own against an existing relation.
- **A taken name is refused, never replaced.** Removing a relation is
  [D46](actions.md).
- **Only the top level of a destination is offered.** Its groupings, or its
  folders and itself — a folder two levels down cannot be chosen yet, and
  walking a destination catalog inside this form is a later slice.
- **A file destination is written at 0600**, as everything this source creates
  through a temporary file is.
- **The file is held whole in memory** while it is parsed, which is what the
  16 MB ceiling is for.

Spec: [Loading a CSV as a new table](../../decisions/2026-08-30-relation-create-design.md)

## D44. An export is a source-owned row stream

The current-page download of D28 repeats one bounded `FetchRequest`; an export of
every matching row does not. Paging `SupportsFetch` until it stops would make a
changing source several snapshots and put offset cost in the platform rather
than in the driver.

- `SupportsExport` takes the node, committed filters, ordered sort and visible
  columns, and yields `ExportBatch` objects of at most 500 rows. There is no
  limit or offset in that request.
- A source either has a real streaming read or does not implement the capability.
- PostgreSQL keeps one validated query open through a server-side cursor; each
  batch crosses as D23's lossless text cells, the sort keeps its source-owned
  tiebreaker, and only requested visible columns are selected.
- The file source deliberately does not opt in: [D49](actions.md)'s node
  download and exporting a tabular interpretation are different operations.
- CSV stays outside the adapter. The connector layer encodes one batch at a time
  with D28's null and quoting rules and writes a `.part` under the caller's
  personal `downloads/<connector-id>` directory; a clean end renames it
  atomically, failure or cancellation removes it. The request returns a row
  count, filename and one-minute signed ticket for that exact stored path, so
  neither side of the HTTP boundary assembles a whole Blob.

Known deviations:

- **It is a long request, not a job.** No durable progress, resume or background
  completion; an upstream timeout or full disk refuses the export rather than
  returning a truncated success.
- **A ticket is reusable until it expires.** It is a bearer capability for one
  already-created file. One-time redemption would require shared state across
  backend processes.

Spec: [Exporting every matching row](../../decisions/2026-08-30-streaming-export-design.md)
