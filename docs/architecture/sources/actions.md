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
  [D32](ddl.md)'s `NodeReplacement`.
- Where a relation is moved to is picked rather than typed. The parameter is
  marked `x-ui-purpose: grouping`, the level supplies the groupings this
  connection has, and the form turns the field into a choice of them, leaving
  out the ones the source calls its own. The list cannot travel in the schema:
  it belongs to one connection and the schema is declared by a class. A source
  that offers no groupings still gets a box to type in. Schema drop is previewed by executing the
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

## D79. Making a user of the server is the owner's, and its password is a literal

A role is the server's rather than the database's: one made through this
connection can sign in through every other connection to that server. Nothing
this application hands out is a reason to be able to do that — `structure` is
the most that can be granted, and it was granted for the shape of somebody's
tables.

- `create_role` is the first action to require `own`. The route already asked
  every action for the level it needs, so the level is the whole statement:
  somebody holding a grant is not offered the command and is refused it.
- It is offered on the Roles report and nowhere else, the way the extension
  commands are offered on theirs. `applies_to` speaks about kinds and every
  report is a report, so which report admits which command is a table —
  `REPORT_COMMANDS` — now that two of them do.
- **The password cannot be bound: PostgreSQL takes no parameters in DDL.** It
  travels as `psycopg.sql.Literal`, the driver's own quoting of a value — the
  same code that quotes a bound parameter, run before the statement is sent
  instead of by the server. Quoting written here by hand would be D2c's exact
  prohibition.
- It is sent as the person typed it rather than as a verifier computed here,
  so the server stores it the way its own `password_encryption` says and the
  new role authenticates however every other role on that server does.
- **Nothing rehearses it.** A preview is the statement run and rolled back, and
  it is worth having because the server's own words come back with it
  ([D46](#d46-an-action-answers-what-it-would-do)); those words are not worth
  having about a statement that carries a secret. Every refusal is this
  module's own sentence chosen by SQLSTATE, which is what `schema_change` and
  `transaction` already guarantee for anything they run.
- A reserved `pg_` prefix and a name that is taken are answered before any
  statement, so the two refusals a person actually meets happen with nothing
  sent.
- The role may sign in and, at most, connect to the database this connection is
  on — asked of the server as `current_database()`, never named by a client.
  CREATEDB, CREATEROLE, SUPERUSER, membership and object privileges are not
  offered: each is a way of handing out more than the person filling in the
  form holds.
- The result names no branch to re-read, because a role is not a catalog node.
  Naming one to make a grid refresh would be a claim that something in the
  catalog changed.

Known deviations:

- **Nothing removes a role.** A role that owns objects cannot be dropped
  without deciding what becomes of them, and that decision is its own slice.
  One made here is taken away with SQL.
- **The password reaches the server's log where the server logs DDL.**
  `log_statement = 'ddl'` writes the statement out, password included. Closing
  that means sending a SCRAM verifier computed here, which also decides on the
  server's behalf which authentication method the new role can ever use.
- **What the new role may read is not answered here.** It can connect and see
  nothing; grants are written as SQL by somebody who has left read-only on
  purpose ([D66](../querying.md)).
- **The report does not re-read itself when a role is made**, exactly as the
  list of extensions does not when one is installed.
- **A name can race another creator.** The check is fresh, and the server
  refuses a duplicate safely; nothing is overwritten.

Spec: [A database user](../../superpowers/specs/2026-09-02-database-user-design.md)

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

- **The preview is a moment, not a promise.** Something can come to depend on the
  relation between the question and the answer; the drop is what decides.
- **A preview of several nodes is only offered where the source takes them
  together** ([D68](#d68-a-set-of-nodes-is-a-subject-an-action-may-have)).
  Several answers stitched together on the client would be a claim the client
  has no right to make.
- **An open tab outlives what it shows.** A dropped relation leaves its data tab
  in place, to fail on its next read; the workspace can follow a renamed node
  ([D32](ddl.md)) and has no word yet for one that is not there at all.

Spec: [Dropping a relation, and seeing what goes with it](../../superpowers/specs/2026-08-30-relation-drop-design.md)

## D68. A set of nodes is a subject an action may have

`bulk` said a filled form may be applied to a set, and the transport behind it
was the same request repeated per node. That is right while the nodes are
independent — five files deleted from a folder are five facts, and a refusal of
one says nothing about the other four. It is wrong when the set is the
question: ticking a table and the view over it and sending two requests refuses
the table, because the view is still there when the first request runs.

So `bulk` keeps its meaning — a set is allowed — and how the set is carried out
is a separate statement:

- `TakesNodeSet` is a `runtime_checkable` Protocol with `perform_on_set`, and
  `PreviewsSet` is its counterpart with `preview_on_set`. Two rather than one,
  for the reason `Previews` is separate from `TakesParams`: an action may take
  a set and have nothing worth previewing about it, and a capability nobody
  implements must not become a stub.
- `ActionInfo` derives `takes_set` and `previews_set` with `isinstance`, as it
  already derives `takes_file`, `previews` and `downloads`. A flag and an
  implementation can disagree; an isinstance check cannot.
- `POST …/actions/{name}/set` and `POST …/actions/{name}/set/preview` carry
  `{node_ids, params}`. A separate body rather than a second optional field on
  `ActionRequest`: two shapes in one body have to be argued about at every call
  site. An action without the capability answers 415 rather than quietly acting
  on the first node of the list.
- Applicability is unchanged. The set routes resolve the action through the
  same check the download route uses, so every node is judged exactly as it is
  for a single request, and a node named twice is refused.
- The client obeys rather than decides: `nodeSetOf` in
  `features/catalog/actions.ts` is the one rule about what a set is, and both
  the preview and the run read it, so what a person is shown and what is then
  sent cannot disagree.

PostgreSQL's drop is the first action to take one. It issues one statement per
kind of relation, each naming every target of that kind, in one transaction and
in the order views, materialized views, tables. Grouping is what makes it work:
everything named in one `DROP` is already gone when the server checks what
depends on the rest. One transaction is what makes it honest: a selection that
cannot go whole leaves every relation in it standing, because half a drop is a
schema nobody asked for. `rehearse` takes the same several statements, so the
preview is still the drop rolled back.

Known deviations:

- **The order across kinds is a heuristic, not a topological sort.** Views
  before materialized views before tables covers a view over a table, which is
  the case people meet. A materialized view read by a view, all three ticked,
  can still need a cascade — and the preview says so before anything happens.
- **One refusal refuses the whole set.** That is the point where relations are
  concerned, and it is the wrong answer for an action whose members really are
  independent. Such an action keeps the repeated transport.
- **Nothing names which relations went.** The message counts them, and the
  catalog is re-read; a person who ticked five boxes and looked away has the
  count and the list, not a receipt.
- **Only the drop takes a set today.** Moving several relations into one schema
  would be the next one, and keeps the repeated transport until somebody asks.

Spec: [Dropping several relations at once](../../superpowers/specs/2026-09-02-action-node-set-design.md)

## D74. Copy and Cut are the client's, and Paste is the source's

Every way of naming a destination in a form is bad: typing a path somebody is
looking at, a select the source would walk its whole tree to fill, or a tree
picker that is a second catalog inside the first. The shape people already know
avoids all three — pick things up here, walk to where they go, put them down —
and its destination is the place being looked at, which an action already knows
how to be told (`acts_on: "children"`).

So Copy and Cut change nothing and belong to the client: they remember a
selection and a verb in `features/catalog/clipboard.ts`, nothing is sent, and
somebody who changes their mind has changed nothing. `paste` is an ordinary
declared action of the source, and what was picked up travels in the request —
a selection held for ten minutes in a browser is not state the source should be
keeping.

Consequences:

- **The form fills itself by purpose, never by name.** The action declares two
  hidden fields, `clipboard-nodes` and `clipboard-mode`, and the dialog fills
  them from what is held. The client learns that a field wants the selection,
  not that the action is called paste — the arrangement `node-name`,
  `grouping` and `file-conflict` already use.
- **Copy and Cut are drawn only where a source has somewhere to put things**,
  which is where its vocabulary holds a command with a `clipboard-nodes` field.
  A database offers neither.
- **They are lines of the same menu the source's actions are in**, together
  with Details ([D75](contract.md)), rather than icons beside it: what can be
  done with a ticked row is asked in one place, and a row of icons grows with
  every verb the client gains. A client line carries a `client:` prefix, which
  a source's identifier-named action cannot collide with.
- **A command needing the clipboard is disabled while it is empty** and says
  what it would paste while it is not.
- **Every id is judged on arrival**, by the containment rule of D8, exactly as
  a path typed into a form is.
- **A move names both ends** in `reload_node_ids`, and the clipboard is
  forgotten once its contents land: offering to paste a file that has just been
  moved away is offering a refusal.
- **The ceilings are the archive's** — ten thousand entries and two gigabytes,
  counted before anything is written ([D71](content.md)).

Known deviations:

- **Nothing crosses connections.** A held selection belongs to the connection
  it came from, because an opaque node id means nothing to another source.
- **A large copy has no progress and no cancel.** It is one request, bounded by
  the ceilings and by nothing else.
- **There is no undo.** A move is a move.
- **The clipboard does not survive a reload**, and says so by being empty.

Spec: [Copying and moving files](../../superpowers/specs/2026-09-02-file-clipboard-design.md)

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

## D73. A download may ask something first, and the model is written as code

`ProducesDownload` took the selection and nothing else, which is right while a
download is only a copy of what was picked. It is not enough when a download is
also a choice: the same relations written as a SQLAlchemy model, a Django model
or a DBML document are three different files.

So the capability takes the filled form too — `download(node_ids, raw)` — and
validates it with the action's own model, exactly as `perform` does. The signed
ticket a browser redeems carries the parameters, because the ticket is the
authority for one invocation and what was chosen is part of what was
authorised; a parameter in the URL is one a person can edit on the way.

Its first user is `describe_model`, offered on a schema and on a relation. The
renderers are pure functions over `RelationModel` in `adapters/model_code.py`:
a source that can describe a relation already publishes its columns, types,
keys and comments (D22), so this is a transformation of an answer that already
exists rather than a second description of a relation. The old application had
two of these inside each driver, reading a driver-shaped dictionary.

Consequences:

- **A schema stands for its contents**, which is what makes a diagram of a
  database one selection rather than forty.
- **A key is written by the published name of what it points at**, looked up
  among the relations in the document; a node id is opaque and reading one
  apart is what D21 forbids. A key pointing outside the document is left out of
  DBML entirely, because dbdiagram refuses a file that names a table it was not
  given.
- **Nothing generated claims to be a migration**, and every file says so in its
  first line. No singularisation — a singular is a guess about English, and a
  guess in generated code is a bug somebody has to find. Django models are
  `managed = False`, because the tables exist and Django did not make them.
- **A composite key is named as what it is.** Django has none, so the columns
  stay ordinary fields and `unique_together` says the rest, under the names the
  file actually gave them.
- **A written model is read before it is taken anywhere.** The action declares
  `x-ui-workflow: model-as-code`, and the client opens a screen of its own
  instead of the generic form: the three dialects as three names on one line,
  the document itself in the editor everything else reads code in, and Copy,
  Save and — for the one dialect a website draws — a door to that website.
  Saving is the bytes already on the screen, so nothing is asked twice.
- **A download runs straight from the menu only when it has nothing to ask and
  nothing to show.** One with a form goes through the form; one with a screen
  of its own goes through that. Downloading a file somebody has not seen is
  asking them to open it in something else to find out what it says.
- **What a workflow screen chooses between is read off the schema**, never
  written out again: `x-ui-choices` carries the source's own words for each
  value — `dbml` is a value, "DBML (dbdiagram.io)" is what a person
  recognises — and the schema's default is what the screen opens on. A screen
  may name the field it is about, the way the file-to-relation screen names
  the ones it fills; it may not invent the values or the words.

Known deviations:

- **The dialects are three, and the obvious fourth is missing.** Alembic,
  Liquibase, Prisma and plain DDL are not written.
- **The document is fetched again for every dialect.** Pressing one of the
  three names is a round trip, and a dialect looked at twice is asked for
  twice.
- **A type is mapped by name, and a name this has never seen becomes text.**
  Every mapping is a best effort at a portable type, and a dialect-specific one
  would tie the file to one database.
- **There is a ceiling of two hundred relations** in one document, and a schema
  above it is refused rather than partly written.

Spec: [The model a source published, written as code](../../superpowers/specs/2026-09-02-model-as-code-design.md)

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
