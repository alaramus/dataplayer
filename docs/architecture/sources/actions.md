# Actions a source declares

For adding an action, changing what a form may be applied to, or adding a
report. What an action changes in a relation is [ddl.md](ddl.md).

## D9. An action is one object

The old application dispatched `getattr(connector, action)(**request_body)`
guarded only by `hasattr`, so every public method of a driver was callable by
name from a client; its 765-line table of supported actions took no part in the
guard.

- A name, a title, the kinds of node it applies to, a Pydantic model of its
  parameters and the implementation live in one class. A driver hands out those
  objects and a route calls them. Nothing that is not in the set resolves.
- `POST /connectors/{id}/actions` with a list of node ids answers with everything
  the source can do, with `applicable` saying which of it every one of them
  admits. The same call decides what the client offers and what the server
  allows, and running an action asks `available` again, so being listed permits
  nothing. Applicability depends on state as well as kind: the root of a
  connector is an ordinary directory that may not be renamed or removed.
- `acts_on` says what an action changes — see D56 for its three values. Without
  it the screen would read the difference off the names of actions.
- `Action.bulk` says whether one filled form may be applied to many; `Delete`
  says yes, `Rename` cannot. The flag never leaves the server: when more than
  one node is asked about, the server leaves out what did not declare it.
- `Action.many_files` says whether it may carry several files; `Upload` says yes,
  loading a table from a CSV cannot, because a second file there would be a
  second table. This one does leave the server as `takes_many_files`, because the
  transport is one file per request either way and a client left to guess would
  offer a set for every action that takes a file at all.
- The transport is a protocol, not a flag: an action that carries a file
  satisfies `TakesFile`, and `takes_file` is an `isinstance` check. There are two
  routes because HTTP has two shapes of body, and each refuses an action of the
  other transport with 415.
- `ActionResult.reload_node_ids` names every branch that changed, rather than the
  client inferring one from the action name.
- Personal-file defaults are resolved by the source: a folder submitted unchanged
  becomes `new folder`, then `new folder (1)`. Deleting a directory removes its
  contents after the action's one destructive confirmation. Upload first refuses
  a taken name, then accepts an explicit retry to replace it or to publish the
  first free `name (n).ext` without overwriting a file that appeared meanwhile.

Known deviations:

- **Nothing moves or copies.** An action works inside one node of one connector;
  moving a file to another folder means downloading and uploading it again.
- **Folder creation and rename can still race another writer.** Upload retries
  through no-overwrite publication; the other two use ordinary filesystem
  operations after choosing their target.
- **An upload gives no progress and cannot be resumed.**
- **Nothing records what was done.** No audit trail, no history of deletions.
- **A set is acted on one call at a time.** Deleting five files is five requests
  run in order; a refusal in the middle is collected and reported rather than
  stopping the rest. Nothing is transactional.
- **Applicability costs a call per node.** Bounded by a ceiling of a thousand node
  ids and by the 2000-entry listing refusal.
- **The menu of actions costs two calls.** One about the level being looked at,
  which carries the vocabulary, and one about what is ticked.

Spec: [The action registry](../../superpowers/specs/2026-08-21-action-registry-design.md)

## D56. An action names one of three subjects

A new schema is made in the database level even while one existing schema is
selected to show its relations; a table loaded from a CSV is made inside that
selected schema; renaming the schema acts on the selected grouping itself.
Treating all three as `children` would make the form's displayed target false for
one of them.

- `Action.acts_on` has three closed values. `level` receives the exact catalog
  level being viewed, `children` receives the shown places, and `node` receives
  an explicit selection: ticked rows when there are any, otherwise the groupings
  selected in the grouping control.
- Merely standing in a directory is still not a node selection, so the file root
  and current folder cannot become rename or delete targets by this change.
- The screen asks applicability for all three subjects and remains ignorant of
  action names and adapter types.
- `ActionResult.reload_node_ids` is an ordered list naming every changed branch:
  creation and removal of a schema name the root and the schema id, rename names
  the root plus both old and new ids, and moving a relation names both schemas.
  The client invalidates every exact source-issued id and redraws its current
  level once; it never derives a parent from a node id. This replaced the former
  singular `reload_node_id`, which could not tell the truth about a move.
- Schema create, rename and move refuse a taken name before DDL and compose every
  identifier with `psycopg.sql.Identifier`. A move accepts only the exact name of
  an existing non-system schema returned by `pg_namespace` and returns
  [D32](ddl.md)'s `NodeReplacement`. Schema drop is previewed by executing the
  exact `DROP SCHEMA` with or without `CASCADE` and rolling it back, as D46
  requires.

Known deviations:

- **Open descendants do not follow a schema rename.** The grouping follows its
  exact replacement, but every relation id below it changes too. Returning an
  unbounded replacement for every relation would make an action result scale with
  the whole schema, and the client may not construct the new ids. Tabs below a
  renamed schema become stale until a bounded branch-replacement contract exists.
- **A schema name can race another creator.** The fresh existence check gives the
  useful conflict answer, but another session can take the name before the DDL.
  PostgreSQL then refuses the statement safely; there is no overwrite.

Spec: [PostgreSQL schema actions](../../superpowers/specs/2026-08-31-postgres-schema-actions-design.md)

## D46. An action answers what it would do

What makes a destructive action safe is not a confirmation box but knowing what
goes with it.

- `Previews` is a `runtime_checkable` Protocol with one method, and `ActionInfo`
  derives `previews` from an `isinstance` rather than from a declared flag, so
  what the API says cannot drift from what the action does. Most actions have
  nothing worth previewing and answer 501.
- The answer is an `ActionPreview`: one summary, a list of lines, and `blocked`.
  Every part of it is the source's own words; the dialog renders a sentence and a
  list and knows nothing about what is being previewed, which is what lets one
  generic form show the consequences of a cascade.
- It is asked again whenever the form changes, since the point is that ticking a
  box changes the answer, and it needs the level the action itself needs: reading
  what a drop would destroy is not a lesser thing than the drop for anyone
  deciding whether it is safe.
- The preview is the drop, rolled back. What a cascade reaches is written in
  `pg_depend`, and restating those rules here would be a second implementation of
  them — wrong the first time an extension adds a kind of dependency, and wrong
  in the worst place. `PostgresSession.rehearse` runs the statement inside a
  transaction psycopg is told to roll back whatever happens.
- Two kinds of answer are kept. A successful rehearsal raises notices —
  `drop cascades to view …` — which are the server describing what it did. A
  refused one carries the list in the DETAIL field of `2BP01`, and only that
  field is passed on: the text of an exception is what carries the connection
  string. Neither is read for meaning; both are shown.
- A rehearsal takes the locks the real statement would, so it is held to a
  two-second `lock_timeout`. A question about what would happen must not become
  an outage, and a rehearsal that cannot get the lock says so.
- `blocked` turns the dialog's button off. The kind of relation comes from the
  catalog's own description of the node, because `DROP TABLE` does not drop a
  view and PostgreSQL's complaint about that names neither.

Known deviations:

- **One relation at a time.** `bulk` is false, unlike deleting files: one list of
  consequences cannot be told apart into five relations' worth by whoever reads
  it.
- **The preview is a moment, not a promise.** Something can come to depend on the
  relation between the question and the answer; the drop is what decides.
- **A preview is asked for one node.** A form applied to several would come back
  as several answers, and nothing on the client knows what to call each of them.
- **An open tab outlives what it shows.** A dropped relation leaves its data tab
  in place, to fail on its next read; the workspace can follow a renamed node
  ([D32](ddl.md)) and has no word yet for one that is not there at all.

Spec: [Dropping a relation, and seeing what goes with it](../../superpowers/specs/2026-08-30-relation-drop-design.md)

## D49. Download is a source-declared action

Download is not a property of a file node or its viewer, so every adapter uses
the same Actions menu without an adapter-name or action-name branch.

- A source declares an ordinary action named `download`, and the callable action
  implements `ProducesDownload`. The listing derives `downloads` from that
  protocol, as it derives file upload and preview transports.
- The action receives the whole non-empty selection once. The file source returns
  one selected file unchanged; more than one node, or any selected directory,
  becomes one recursive ZIP — `<directory>.zip` for one folder and
  `download.zip` for a set — with empty directories retained.
- ZIP staging runs in a worker thread and a temporary file, with ceilings of
  10,000 entries and 2 GiB of uncompressed source bytes; symbolic links and
  ambiguous duplicate top-level names are refused. The archive is removed after
  the stream closes.
- The authenticated request issues a signed one-minute ticket containing the
  user, connector, action and opaque node ids. Following it with a normal browser
  navigation re-checks the user, access, enabled connector, action and every
  target before asking the source for `ActionDownload`. A server path never
  enters the ticket or the client.
- `image` is the first binary `NodeRepresentation`. The catalog classifies PNG
  and JPEG by name, because listing must not open every file, while the content
  read verifies the bytes with Pillow and returns the verified MIME type, width,
  height and byte length. Its dedicated preview ticket returns the verified bytes
  inline with `nosniff`; it is not the download action's ticket or transport.
- Preview has two independent ceilings: 20 MB of encoded bytes and 40 million
  decoded pixels. The verified bytes are the bounded bytes returned, so a file
  cannot change between checking and rendering. A single-file action stream is
  yielded in 256 KB chunks and never assembled in Python or JavaScript.
- The first viewer accepts only PNG and JPEG. GIF and WebP need animation and
  frame bounds, SVG an active-content decision, TIFF and icons their own format
  behaviour. All can still be selected for Download.

Known deviations:

- **Tickets may be replayed until they expire.** Every redemption re-checks
  current access, the action and its targets, but the signed token is not
  consumed.
- **Archive staging has no per-user or process-wide quota.** Each result has hard
  entry and source-byte bounds, but concurrent staging is not pooled.
- **Preview returns the bounded original image, not a thumbnail.** A later
  source-owned thumbnail can reduce transfer without changing the representation.
- **The JSON and JSONL bounded viewers remain API-only.** A large-document
  fallback still needs a screen that does not imply a partial document is
  editable.

Spec: [Download actions and bounded image content](../../superpowers/specs/2026-08-31-original-file-and-image-content-design.md)

## D55. A source may publish reports of its own

Three of the old application's "System's objects" screens have no relation to
open and never will — tablespaces need `pg_tablespace` joined to `pg_roles` and
`pg_class` with `pg_tablespace_size` and a count of objects, and a reader cannot
be asked to write the join.

- A report is a named, read-only, tabular answer a source gives about itself. It
  is a catalog node of kind `report`, walked to and opened like anything else,
  and the section holding them is a report with children, the way a folder inside
  an archive is an entry with children ([D53](content.md)).
- The registry in `postgres/system_reports.py` holds one `sql.SQL` per report,
  written in this repository and never composed from anything a request carries.
  A node id selects one entry from a closed tuple; an id naming no entry is
  `NodeNotFound`, not a query.
- Filters, sorting and paging arrive as the ordinary `FetchRequest` and are
  validated against the report's own columns exactly as against a relation's,
  because the report becomes the `FROM` of the same builder —
  `SELECT … FROM (statement) AS report`. So [D2c](contract.md) holds unchanged.
- The columns are described, not declared. Listing them beside each statement
  would drift the first time a statement changed, so the statement is executed
  with `LIMIT 0`, psycopg's cursor description gives each column's name and type
  OID, and one lookup in `pg_type` turns those into the same `ColumnType` a
  relation's columns are built from. A report therefore sorts, filters, charts
  and downloads with no code that knows it is a report.
- Nothing is written through a report, and this needs no rule: `update`, `insert`
  and `delete` are refused for it as for a view, and no row handle is issued.
- The section's node id is `pg_dataplayer`. PostgreSQL refuses to create a schema
  whose name begins with `pg_`, so the id cannot collide with a schema a user
  could make — the server's own guarantee rather than a convention this project
  hopes holds.
- The six reports PostgreSQL publishes are processes, settings, tablespaces,
  roles, routines and extensions. Extensions is one report where the old
  application had two, because `pg_available_extensions` already states the
  installed version.
- A report is not a relation and answers no relation model: `describable` is
  false, and a subquery has no constraints, indexes or owner.
- Another adapter gets this for nothing: a queue's consumer lag and a container
  runtime's process list are the same shape, and the kind is not named after
  PostgreSQL.

Known deviations:

- **A report has no row count and no estimate.** `pg_class.reltuples` is about a
  relation; running the statement to count would cost what reading it costs.
- **Following a foreign key out of a report is not offered.** The columns of a
  join carry no constraint, and inventing a reference from a column name is the
  guessing [D36](relations.md) exists to avoid.
- **Ordering falls back to the statement's own.** A report has neither a key nor a
  `ctid`, which is why every registered statement ends in an `ORDER BY` of its
  own.

Spec: [What the old PostgreSQL adapter does beyond the table rounds](../../superpowers/specs/2026-08-31-postgres-system-operations-design.md)
