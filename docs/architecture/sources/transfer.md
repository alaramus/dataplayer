# Moving rows in and out of a relation

Copying rows from one source into another, loading a file into a relation,
streaming every matching row out, and pasting files or a table into another
connection. Reading a relation and editing the rows in it are in
[relations.md](relations.md); the grid's own current-page download is in
[../grid.md](../grid.md).

Decisions here: D43, D45, D44, D161, D163, D164, D165, D166, D168, D169.

## D169. A folder is carried whole between connections

`file_copy` and `file_move` take any mix of ticked files and folders. A
folder goes whole: every file and every folder below it, empty ones included,
under the same relative path.

- **Before anything starts** the request walks the folders, stopping as soon
  as a ceiling is crossed: 10,000 files and folders — D74's ceiling within one
  connection — and D168's 10 GB. The job walks again when it begins and carries
  the tree as it is then.
- **Links.** One inside a folder is skipped and listed; one ticked itself is
  refused, "Copy files and folders, not links", since resolved it would carry
  the tree it points at.
- **A taken folder name** offers Keep both, `name (1)`, and never Replace: the
  old folder would go before the new one had arrived. An offer says so by
  `can_replace`, narrowed for the selection.
- **Not into itself.** Where both ends are on this machine (`OnThisDisk`),
  a folder pasted into its own subtree is refused by comparing real paths.
- **A move removes its sources only at the end**, files included: each file
  that arrived and is still the version read, then each folder left empty,
  deepest first, through `Storage.remove_empty`, which refuses a folder that
  holds anything. A Stop or a failure before that leaves the source whole.
- **The payload holds what was ticked**, with files and bytes planned and the
  files arrived, failed, skipped and removed, the path in hand and the first
  hundred files that did not arrive. The row is written at most once a second,
  and at once at a Stop or the end.
- **Processes** shows "reports/2025/q3.csv — 312 of 4,211", then one line per
  ticked item — "reports — 4,208 copied, 3 failed, 1 skipped" — and the files
  that did not arrive, the first ten of each and how many more. A move shows a
  "removing the sources" step.

Known deviations:

- **Two SSH connections to one server are not compared.** A folder pasted into
  its own subtree through them is carried as walked at the start, so it cannot
  recurse, but it is not refused either.
- **A crash leaves a partial copy**, complete file by file.

Spec: [Folders carried between connections](../../decisions/2026-09-25-folder-transfers-design.md)

## D168. A transfer between connections is an owned job

`file_copy`, `file_move` and `relation_csv` run as D81 jobs of kind
`paste.transfer`; the row kinds of D166 stay in the request, held to D45's
16 MB. A kind says which by the protocol it implements, `PastesNow` or
`PastesAsJob`, and `/paste` — in `app/transfers`, above the jobs it starts —
answers `done` with the result or `started` with the job.

- **Planned at once.** `plan` makes every check that answers immediately: the
  ceilings, a taken name, access. D162's window still opens before anything
  starts. At most 1000 files and 10 GB per paste; a CSV stops at 10 GB.
- **Three at a time per person** (`TRANSFER_MAX_ACTIVE`). A fourth is refused
  with 429, "Three transfers are running — wait for one to finish", counted
  under an advisory lock on the owner (`jobs.crud.admit_within`). Eight run at
  once across the server, on worker threads of their own so a long copy takes
  none from the shared pool; one beyond them shows "waiting for a free
  transfer slot" until a slot frees.
- **The payload is the record.** `Transfer` holds both connections, the place,
  the conflict rule, each item with its size and outcome, the bytes moved and
  of how many, and the kind's own words (`doing`, `done`) so the screen names
  no kind. The row is written at most once a second, and at once at a Stop
  or the end (D169); every write is announced.
- **Both ends are checked again** when the job starts, as its owner sees them
  then: a connection gone, switched off or no longer granted enough fails it
  before a byte moves.
- **One file failing is that file's outcome**, in a sentence that names it; a
  connection that cannot be reached, or a destination folder gone, ends the
  rest as not attempted. Anything short of every item done fails the job, which
  then waits in Needs you (D115).
- **Stop is at once.** Every 1 MB piece is a short call on a worker thread that
  a Stop waits for (`in_worker`: a native cancel does not wait for a thread),
  then the file in hand is discarded. The handler says how far it got
  (`ExplainsStop`); a stopped transfer is news in Recent, not a question.
- **A file for an SSH server is written there as it arrives**
  (`Storage.incoming`), into a temporary name beside its target, and is never
  staged whole on this machine. A local folder keeps its staged file beside the
  target.
- **The screen follows it.** The footer says "Copying to SSH server · 45 MB of
  120 MB"; Processes names both connections, the item in hand and afterwards
  each item's outcome, the first ten and how many more. A table has no known
  total, so it shows the bytes written and no bar. The catalogs it writes into
  re-read as files arrive, at most every two seconds and once at the end, and
  the tab that started it says how it ended.

Known deviations:

- **A crash can leave a staged file.** A process that dies mid-file leaves its
  `.dataplayer-…` beside the target, locally or on the SSH server. It is never
  published under the real name; the startup sweep does not reach a
  connection's disk.
- **No folders, pause or resume.** An interrupted transfer is not continued;
  pasting again decides the files already there by the conflict rule chosen.

Spec: [Transfers as owned jobs](../../decisions/2026-09-25-transfer-jobs-design.md)

## D164. One paste answer for a pair of connections

A clipboard from another connection is pasted through three routes, whatever
it holds. `POST /connectors/{destination}/paste/offers` lists what it can
become here; `POST /connectors/{destination}/paste` runs one offer, at
once or as a transfer job (D168);
`POST /connectors/{source}/clipboard/offer` says whether a selection can be
held at all. Each kind of paste is an entry in the `connectors/paste`
registry. It names the capabilities it needs from each end and the clipboard
mode it serves, and is matched with `isinstance`, never by adapter type. There
are five: `file_copy` (D161), `file_move` (D163), `relation_csv` (D165),
`rows_new_relation` and `rows_into_relation` (D166).

- The pair names the place Paste was chosen in and, when exactly one node is
  ticked there, that node as `target_node_id`.
- Asking needs `read` on both ends. A kind states what it needs beyond that
  on each end — `write` or `structure` on the destination, `write` on the
  source of a move — and is listed unavailable with that reason; running it
  answers 403. A kind neither end matches is not listed, and an empty list
  reads "Nothing here can take what was copied".
- An offer names the window it opens (`workflow`), whether it converts,
  whether Replace is allowed and whether it changes the source, with what its
  window needs: a suggested file name, the source's columns, the target's
  insertable columns. The client picks a window by `workflow` and names no
  kind.
- The catalog has one Paste. Several usable offers open a list first; a
  conversion opens its window; a plain copy runs at once and opens D162's
  conflict window on a taken name. The source catalog is refreshed when the
  offer changes the source, after success or a partial failure alike.
- Copy and Cut are drawn for a source with its own Paste (D74) as before, and
  otherwise from the clipboard answer: a mode no kind serves for this source is
  not drawn, and a selection a kind refuses is drawn disabled with the reason.
  A PostgreSQL table has Copy and no Cut.
- A request carries up to 1000 ids; a kind states its own smaller ceiling as a
  reason.

Known deviations:

- **Same-connection Paste stays source-owned.** A clipboard from the same
  connection still goes through the source's own action (D74); a PostgreSQL
  table copied within its own connection has no Paste at all.

Spec: [Paste offers, and a table pasted into a folder as CSV](../../decisions/2026-09-25-paste-offers-and-table-csv-design.md)

## D166. Rows are pasted as a new table or into a ticked one

Two kinds read the clipboard as rows through `SupportsFetch`, one node at a
time: a CSV, Parquet or worksheet file on local disk or SSH, a PostgreSQL
table or view, a Redis key. Both are copies, both convert, and both run what
D43 and D45 run, from `connectors/imports`: the same bounded read, the same
check of every value, the same single transaction. The routes of D43 and D45
call the same two functions.

- `rows_new_relation`, "Create a table": into the place Paste was chosen in,
  of a source implementing `SupportsCreateRelation`, with `structure` there.
  Its window is D45's form with the connection and schema fixed. A source
  beyond 5000 rows is refused.
- `rows_into_relation`, "Add rows to a table": into the one ticked node, of a
  source implementing `SupportsInsert` and `SupportsFetch`, with `write`
  there. Its window is D43's form with the source fixed, same names paired to
  start with. Beyond 5000 rows the rest is cut off and the answer says so.
- A value the target cannot read is named — the first one, its row, and how
  many more — and nothing is written; the window stays open with it.
- A source that holds files is not a destination for either. A folder takes a
  file as it is (D161) or a table as CSV (D165); a delimited file made of rows,
  or rows appended to a ticked CSV, would be a second answer for one Paste.

Known deviations:

- **The forms live in the grid.** D45's and D43's dialogs are imported by the
  catalog from `features/grid`, where they were first written, with a mode for
  a destination or source that is already decided.

Spec: [Rows pasted into another connection](../../decisions/2026-09-25-paste-rows-design.md)

## D165. A table pasted into a folder becomes a CSV file

Kind `relation_csv`: from a source implementing `SupportsExport` and
`SupportsRelationModel` — a PostgreSQL table or view today — into a folder of
an explorer connection. Copy only; nothing offers a Cut of it.

- One relation per paste. Columns come from the relation model in order, rows
  from one D44 export stream with no filter and the source's own ordering. The
  encoder is D44's (`downloads.write_csv`), so the bytes equal the grid's
  whole-relation download.
- Paste opens "Save as CSV" with `<table>.csv`. The name must be plain, and
  `.csv` is appended unless it already ends so. Not D45's rule, which keeps any
  delimited extension: a `.tsv` holding commas reads back as one column.
- A taken name opens D162's window with Keep both and Replace. Replace is
  allowed because the source is not a file.
- The stream is written where it is going as it comes (D168) and published
  after the last batch. At most 10 GB of CSV; crossing it fails the paste. A
  source failure, a refused name, the ceiling or a Stop discards the file, and
  the source's stream is closed at once rather than when collected.
- The destination's read cache is invalidated. The source is untouched and the
  clipboard keeps the table.

Known deviations:

- **Whole relation only.** Copying from the grid with its filters, sort and
  visible columns is not offered.

Spec: [Paste offers, and a table pasted into a folder as CSV](../../decisions/2026-09-25-paste-offers-and-table-csv-design.md)

## D163. A file can be moved between explorer connections

Cross-connection Cut uses the same clipboard and Paste as Copy, but the
application asks for `write` on both connections. It publishes every complete
file at the destination first; only then does it remove each source file that
is still the version read (D169). A failed deletion leaves both copies and
reports that state. The server invalidates both connections' read caches; the client
refreshes both open catalogs. The clipboard is cleared when the move starts
(D168).

A name conflict offers Keep both in the same window as Copy. Replace is not
offered for cross-connection Cut because two connectors may name the same
backing file. Replacing it and then deleting the source could remove the new
destination. The existing same-connection Cut remains source-owned.

Known deviations:

- **A batch is not atomic.** A file that fails stays at the source while the
  rest move. A file whose destination was published but whose source could
  not be removed remains in both places; its outcome says so.
- **No directory moves.**

Spec: [Moving a file between connections](../../decisions/2026-09-25-cross-connector-cut-design.md)

## D161. A file can be copied between explorer connections

The first cross-connection interaction is a file copy between two sources that
expose the explorer's `Storage`, including local files and SSH. The application
resolves both connections, checks `read` on the source and `write` on the
destination, and asks each storage about its own opaque node ids. It is
D164's `file_copy` kind: the pair answer says whether the selected files can
be copied to the current folder, and execution checks again. The
same-connection Paste of D74 continues through the source's own action.

- Copy leaves the source in place. A folder is carried whole (D169); a
  ticked link is refused. A paste holds at most 1000 files and 10 GB (D168). Bytes are read in
  1 MB pieces and written where they are going; the destination publishes
  only after the whole file has arrived.
- Existing names are refused by default. The catalog has one Paste command;
  choosing it opens a conflict window with Keep both and Replace when the
  offer reports a taken name or execution discovers one. A batch checks its
  names before starting, but a source or
  destination can change during execution: a file that then fails is that
  file's outcome, and the files around it still arrive (D168). The destination
  catalog is invalidated even on failure.
- The offer is advisory. Both rights and connector states are resolved again
  at execution, and every node is checked by the source storage when read.

Spec: [Interactions between connections](../../decisions/2026-09-25-cross-connector-interactions-design.md)

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
