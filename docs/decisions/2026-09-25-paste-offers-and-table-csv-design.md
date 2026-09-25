# Paste offers, and a table pasted into a folder as CSV

Date: 2026-09-25. Decisions: D164 (one paste answer for a pair) and
D165 (a table pasted into a folder becomes a CSV file). Builds on D161, D162
and D163; step 1 and part of step 4 of
[Interactions between connections](2026-09-25-cross-connector-interactions-design.md).

## The problem

Cross-connection Paste has one pair of routes per kind of transfer:
`file-copy/offer` and `file-copy` for Copy, `file-move/offer` and `file-move`
for Cut. The catalog chooses between them by the clipboard mode. A third kind
would add a third pair of routes and a third branch in the client. The
interactions spec requires the opposite: the server answers what can be done
with a pair, and the client does not keep a table of kinds.

The first kind that is not a file copy is also the most useful one: save a
database table as a CSV file in a folder of any explorer connection — the
local files or an SSH server — without a download to the browser and an
upload back. Its parts already exist. D44 streams every row of a relation as
CSV in bounded batches; D161's destination storage stages a file and
publishes it only once complete. What is missing is the way to ask for it:
a PostgreSQL catalog has no Copy at all, because Copy and Cut are shown only
where the source has its own clipboard action (D74).

## D164. One paste answer for a pair

### Offers

`POST /connectors/{destination_id}/paste/offers` takes the pair:

- `source_connector_id`, `source_node_ids` — what the clipboard holds;
- `mode` — `copy` or `move`, the clipboard's verb;
- `destination_node_id` — the folder or container Paste was chosen in.

It answers a list of offers. Each offer has:

- `kind` — a closed `Literal`: `file_copy`, `file_move`, `relation_csv`;
- `title` — what the command does, for a window or a later chooser;
- `available` and `reason` — the reason is set whenever it is unavailable;
- `name_conflict` — the default name is taken at the destination;
- `converts` — the result is a different kind of object than the source;
- `can_replace` — whether the conflict window may offer Replace;
- `changes_source` — running it changes the source connection too;
- `suggested_name` — for a kind that asks for a name, its starting value.

The kinds live in a registry in the `connectors` layer, beside D43's row
import. Each kind declares the capability it needs from the source, the one
it needs from the destination, and the clipboard modes it serves. A kind is
matched by `isinstance` against those protocols, never by adapter type. A kind
that does not match is not listed. A kind that matches but is refused by the
current state — a folder rather than a file, a read-only destination, a name
the destination rejects — is listed as unavailable with its reason.

The route checks `read` on the source, and `write` on the destination. A kind
that removes the source (`file_move`) also needs `write` on the source, as in
D163. Rights and nodes are checked again at execution: an offer is
information, never authorization.

### Execution

`POST /connectors/{destination_id}/paste` takes the same pair plus:

- `kind` — the offer being run;
- `conflict` — `refuse`, `rename` or `replace`, as in D162;
- `name` — for a kind that asks for one, the name typed in its window.

It answers `kind`, a `message`, the number of objects written, `rows` when
rows were written, the final `name` when there is one, and `reload_node_ids`
for the destination. The client refreshes the source connection when the
offer's `changes_source` is true, instead of inferring it from the clipboard
mode. The offer rather than the result carries it, because a move that fails
partway has no result and may still have removed earlier files.

The four routes of D161 and D163 are removed. Their behaviour does not
change: limits, staging, the check that a moved source is unchanged, and
Replace withheld for a cross-connection move all carry over as the
`file_copy` and `file_move` kinds.

### The catalog

- **Paste** stays one command (D162). When the clipboard belongs to another
  connection, it is enabled when the answer has an available offer, or an
  offer whose only problem is a taken name. When no offer is listed, its hint
  is "Nothing here can take what was copied".
- With exactly one usable offer, Paste runs it. An offer with `converts` or
  a name to ask for opens its window first; a plain copy runs directly and
  opens the conflict window of D162 only on a taken name. With several usable
  offers Paste opens a window that lists them. No pair has more than one kind
  in this step, so that window is specified and not built.
- **Copy and Cut** are shown for a selection when the source has its own
  clipboard action (as now), or when
  `POST /connectors/{source_id}/clipboard/offer` with `node_ids` says so. That
  route answers `copy` and `cut`, each with `available` and `reason`, from the
  source half of the same registry: a selection can be copied when some kind
  accepts it as a source in `copy` mode. A PostgreSQL table therefore gains
  Copy, and not Cut.

## D165. A table pasted into a folder becomes a CSV file

Kind `relation_csv`, `converts: true`, title "Save as CSV", mode `copy` only.

**Source.** One node of a connection implementing both `SupportsExport` and
`SupportsRelationModel`, where the node is `describable`. Today that is a
PostgreSQL table or view. A selection of more than one node is unavailable:
"Copy one table at a time". The file source is not a source for this kind: it
does not implement `SupportsExport` (D44), and a CSV file pastes as a file.

**Destination.** A folder of an explorer connection (`TransfersFiles`, D161).

**What is written.** Every row and every column, in the order the relation
model gives the columns, with no filter and the source's own ordering. The
rows come from one D44 export stream, which is one snapshot of the relation.
The bytes are the same as D44's download: UTF-8 with a byte order mark, a
header row, and D28's rules for nulls and quoting. The encoder is shared with
D44's writer, not copied.

**The window.** Paste opens a window "Save as CSV". It names the table and the
destination folder, and has one field, the file name, starting as
`<table name>.csv`. `.csv` is added unless the name already ends in `.csv`.
D45's rule keeps any delimited extension, and a `.tsv` holding commas would
read back as one column.
The destination storage validates the name as a plain name. Save and Cancel.

**A taken name.** Save sends `conflict: refuse`. When the name is taken, the
D162 conflict window opens with Cancel, Keep both and Replace. Replace is
allowed here: the source is not a file, so the replaced file cannot be the
source itself, which is the reason D163 withholds it.

**Writing.** The stream is written into `destination.staged(target)` and
published only after the last batch. A source error, a refused name or the
ceiling discards the staged file; the folder never shows a partial CSV.

**Limits.** At most 200 MB of CSV, D161's byte ceiling. Crossing it refuses
with `too_large` and publishes nothing. There is no row ceiling: the stream
holds one batch in memory. The work runs inside the request, like D161: no
progress, no cancellation.

**Afterwards.** The destination folder reloads through the ordinary reload
path, and the destination's read cache is invalidated. The source is not
changed, and the clipboard keeps the table, so it can be pasted again
elsewhere. The toast names the file and the number of rows.

**Errors.** A source failure is reduced to its kind and a safe message, as in
D44's route; the driver's text never reaches the caller. A storage failure is
"The file could not be saved".

**Relation to what exists.** D44's `downloads/export/keep` already writes the
same CSV into a fixed folder of personal storage. This kind writes it into any
folder the person chooses, in any explorer connection. Both remain.

## Out of scope

- CSV → table through Paste: a file pasted into a schema or onto a table. That
  is the next step, and it needs D43's and D45's forms and limits.
- Copy from the grid with its filters, sort and visible columns.
- Several tables in one Paste, and formats other than CSV.
- Owned jobs with progress and cancellation (D81, D95), and higher ceilings.
- The paired catalog view.
- Same-connection Paste through the offers route. It stays the source's own
  action (D74) and is recorded as a known deviation of D164.

## Acceptance

- A copied local file and a cut SSH file still paste as today: both kinds,
  conflict windows, both catalogs refreshed after a move.
- A ticked PostgreSQL table shows Copy and not Cut; a ticked schema shows Copy
  disabled with its reason.
- Pasting the table in a writable SSH folder and in a local folder opens
  "Save as CSV"; Save writes a file with the same bytes as D44's download of
  that table, and the folder shows it.
- A taken name opens the conflict window; Keep both writes `name (1).csv`,
  Replace replaces the file.
- A read-only destination or a missing read grant on the source makes the
  offer unavailable with a reason; a grant revoked after the offer is refused
  at execution.
- An export over 200 MB, and a source failure halfway, leave no file.
- A Redis selection shows no Copy.

Tests cover the registry and each kind against local storages, both routes
with the permission cases, and the catalog: offer shapes, the window, the
conflict path and the source refresh driven by `source_changed`. Validation
commands are run with the user's approval, per AGENTS.md.
