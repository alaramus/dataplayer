# Actions a source declares

For adding an action or changing what a form may be applied to. What an action
changes in a relation is [ddl.md](ddl.md); downloads and reports are in
[downloads.md](downloads.md).

Decisions here: D9, D56, D118, D79, D46, D68, D74, D162, D209, D210.

## D209. Rows picked in a report open a reviewed action on the node they belong to

A row command ([D70](relations.md)) runs at once. Something reviewed first —
dropping chunks is a job with a plan (D123) — is an action of a catalog node,
and a database-wide report's rows belong to many nodes whose ids the client
cannot compose.

- A relation declares `PickedRowsAction`s on its fetch result beside its row
  commands: the action's name, the columns that name a row, a title and an
  icon. They are filtered by the action's own level.
- The grid offers them while rows are picked. Pressing one sends the picked
  rows' keys to `POST …/rows/picked`, and the source answers with the node, the
  parameters naming exactly those rows, and the fields they stand in for — or
  refuses: rows of two nodes, a row that is gone.
- The client opens the action's own window on that node, with those values set
  and those fields left out. Preview, review, fingerprint and job are the
  action's own, so the plan reads every picked row again.

The Chunks report offers drop, move, reorder, detach and both merges this way;
the actions take `chunks` by name as well as a window.

Spec: [Reviewed actions from rows picked in a report](../../decisions/2026-10-10-actions-from-picked-rows-design.md)

## D210. A tablespace is the server's, changed from the Tablespaces report

New tablespace… sits above the report's rows like New role (D79); Rename… and
Change owner… are offered over one picked row (D209), through `offered_in =
"picked"`, which keeps them out of the catalog menu and the row above the grid;
Remove is in a row's corner (D70). All need `own`. `pg_default` and
`pg_global` are offered none of them, and a `pg_` name is refused first.

`CREATE` and `DROP TABLESPACE` refuse a transaction block and are sent with
none (`schema_change(alone=True)`, as D206). The directory is the server's:
DataPlayer neither lists nor makes one, the form says what the path needs, and
each refusal is a sentence chosen by SQLSTATE. A drop the server refuses
because something is stored there loses nothing.

Spec: [Tablespaces](../../decisions/2026-10-10-tablespaces-design.md)

## D162. Paste asks about a taken name in a window

The catalog offers one Paste command for either a same-connection or a
cross-connection clipboard. A taken destination name opens a window with
Cancel, Keep both and, where safe, Replace. D163 withholds Replace for a
cross-connection Cut. An offer may know about the conflict before
the command runs; a concurrent change may reveal it only when execution is
attempted. Both paths open the same choice, rather than adding Paste variants
to the action menu. The source-owned and application-owned transports retain
their own execution paths and recheck availability when a choice is made.

Spec: [Paste conflict window](../../decisions/2026-09-25-paste-conflict-window-design.md)

## D9. An action is one object

Rejected: dispatching `getattr(connector, action)(**request_body)` guarded
only by `hasattr`, which makes every public method of a driver callable by name
from a client; a separate table of supported actions takes no part in such a
guard.

- A name, a title, the kinds of node it applies to, a Pydantic model of its
  parameters and the implementation live in one class. A driver hands out those
  objects and a route calls them. Nothing that is not in the set resolves.
- `POST /connectors/{id}/actions` with a list of node ids answers with everything
  the source can do, with `applicable` saying which of it every one of them
  admits, or whether a destination candidate is available (D118). The same
  source offers decide what the client presents and what the server
  allows, and running an action asks `available` again, so being listed permits
  nothing. Applicability depends on state as well as kind: the root of a
  connector is an ordinary directory that may not be renamed or removed.
- `acts_on` says what an action changes — see D56 and D118. Without
  it the screen would read the difference off the names of actions.
- `Action.bulk` says whether one filled form may be applied to many; `Delete`
  says yes, `Rename` cannot. The flag never leaves the server: when more than
  one execution target is asked about, the server disables what did not declare
  it. Destination candidates are choices, not an execution set (D118).
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
- The generic action screen uses the shared form and chooses geometry from the
  form's capabilities. Ordinary questions fit their content. A preview keeps a
  stable compact form, and a staged file list keeps a stable medium form, so
  changing content scrolls without moving the title or footer actions.
- `PreparesConnector` is an action capability that returns a `ConnectorDraft`
  with a name, adapter type and source-resolved options. Its
  `POST /connectors/{id}/actions/{name}/connector-draft` route rechecks the action,
  node and access like execution does, but saves nothing and invalidates no
  source cache. `ActionInfo.prepares_connector` is derived from the protocol;
  the menu opens the ordinary connector form directly, and its normal Save or
  Apply creates the connection. The client never constructs a path from node ids.
- File sources offer **Connect folder** for one selected child directory, to
  the owner only. The source resolves the folder against its current root, then
  expresses it relative to the owner's personal home, including when the
  source itself starts in a nested folder. Internal symlinks use the resolved
  target path; an escape, the current connector root, files and multiple
  selections are refused. A path that the connection options would trim is
  refused instead of quietly pointing the new connection at another folder.
- Personal-file defaults are resolved by the source: a folder submitted unchanged
  becomes `new folder`, then `new folder (1)`. Deleting a directory removes its
  contents after the action's one destructive confirmation. **New file** asks
  for a name defaulted to `new file` and nothing else, then makes an empty file
  in the folder being looked at; a taken name is refused rather than numbered,
  because whoever named it — a person or the agent (D133) — refers to it by that
  name next. Upload first refuses
  a taken name, then accepts an explicit retry to replace it or to publish the
  first free `name (n).ext` without overwriting a file that appeared meanwhile.

Known deviations:

- **Source-owned Paste stays within one connector.** D74 defines copying and
  moving within a file source; D161's first cross-connector file copy belongs
  to the application layer.
- **Folder creation and rename can still race another writer.** Upload retries
  through no-overwrite publication; the other two use ordinary filesystem
  operations after choosing their target.
- **Uploads cannot resume partway through a file.** D95 shows transport progress
  and allows pausing or stopping a batch before its next request.
- **There is no durable action audit trail.** D95 retains local process results
  for the page session only.
- **A set is acted on one call at a time.** Deleting five files is five requests
  run in order; a refusal in the middle is collected and reported rather than
  stopping the rest. Nothing is transactional.
- **Applicability costs a call per node.** Bounded by a ceiling of a thousand node
  ids and by the 2000-entry listing refusal.
- **The menu asks about distinct subjects.** Level, places, selected nodes,
  selected groupings and destination candidates use cached queries; identical
  target lists share an answer.

Spec: [The action registry](../../decisions/2026-08-21-action-registry-design.md)

## D56. Level, places and node selection are separate subjects

A new schema is made in the database level even while one existing schema is
selected to show its relations; a table loaded from a CSV is made inside that
selected schema; renaming the schema acts on the selected grouping itself.
Treating all three as `children` would make the form's displayed target false for
one of them.

- The original three `Action.acts_on` values remain: `level` receives the exact catalog
  level being viewed, `children` receives the shown places, and `node` receives
  an explicit selection: ticked rows when there are any, otherwise the groupings
  selected in the grouping control.
- Merely standing in a directory is still not a node selection, so the file root
  and current folder cannot become rename or delete targets by this change.
- D118 adds independent grouping and destination subjects. The screen asks
  applicability per subject and remains ignorant of
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

Spec: [PostgreSQL schema actions](../../decisions/2026-08-31-postgres-schema-actions-design.md)

## D118. Selection scope and destination choice are separate

`group` acts on explicitly selected groupings, unaffected by checked rows.
Schema rename and drop use it and require one schema. `destination` opens a
workflow that chooses one destination; CSV import and table creation use it.
Their candidates are all groupings offered by the level, so displaying several
schemas or none does not prevent opening the form when a valid destination exists.

The source returns `available_node_ids` and `unavailable_reason` with
`applicable`. Ordinary subjects require every target to qualify and `bulk` for
multiple targets; a destination workflow requires at least one eligible
candidate. The client gives that workflow one eligible initial destination,
preferring a displayed place, and the form exposes the final choice. Candidate
lists never become execution batches. Node actions never silently omit an
ineligible selected node. Move to schema permits repeated independent moves;
rename and schema drop retain their single-target constraint.

The menu, form caption, current-name default, preview and execution use the same
resolved targets, captured when the form opens. Existing permission, root,
system-node and transport guards still run on execution. Actions drawn over a
node's rows and client-owned commands keep their existing capability rules.

Spec: [Action targets and availability](../../decisions/2026-09-07-action-targets-design.md)

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
- **And it is asked for from above those rows, not from the catalog menu.**
  Reaching it meant walking to the report in the catalog, ticking it and
  opening a menu, while the list of users it adds to was already on screen —
  the same distance installing an extension was moved out of
  ([D70](relations.md)). `Action.offered_in` is `catalog` or `rows`, declared
  by the action and read by the client, which knows no action's name: what
  says `rows` is drawn in the row of commands over the node it acts on and is
  left out of the menu, so one command is never in two places. It names the
  picture it is drawn as, `person_add` here, for the reason a row command
  names one ([D70](relations.md)). Only this action says any of it; a second
  one is when the statement earns a decision of its own.
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
  catalog changed. The grid re-reads its own page instead: an action run from
  above the rows changed the rows, and nothing else on screen would say so.

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
- **A name can race another creator.** The check is fresh, and the server
  refuses a duplicate safely; nothing is overwritten.

Spec: [A database user](../../decisions/2026-09-02-database-user-design.md)

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

The form is asked the same way. A field that names a thing of the node — a
column, an index, a tablespace — is a string in the static schema, and a bound
of a chunk window is an instant on one hypertable and a number on another. An
action whose form depends on the node implements `OffersFieldHints`:
`ActionInfo` derives `offers_hints` from an `isinstance`, and the dialog asks
`POST …/actions/{name}/hints` once it opens for one node. A field the answer
names values for becomes a list; one it leaves out, or names nothing for, stays
typed. A field it names as an integer loses its calendar and says what number
it takes. The hints are a convenience the plan checks again, never what decides.
Until every required field is filled the dialog does not ask for a preview: it
says what is missing instead of relaying the server's sentence about an empty
value.

Spec: [Dropping a relation, and seeing what goes with it](../../decisions/2026-08-30-relation-drop-design.md)

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

Spec: [Dropping several relations at once](../../decisions/2026-09-02-action-node-set-design.md)

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
- **Paste opens no window.** A form whose every field is hidden, that is not
  destructive, takes no file and previews nothing has nothing to ask, and the
  window it opened was an empty confirmation of a gesture already made twice —
  pick up, walk, put down. Such an action runs the moment its line is chosen;
  the window comes up only when the source refuses, because the refusal is
  read there. The rule is about the form and not about paste: any action that
  asks nothing behaves the same way.
- **Every id is judged on arrival**, by the containment rule of D8, exactly as
  a path typed into a form is.
- **A move names both ends** in `reload_node_ids`, and the clipboard is
  forgotten once its contents land: offering to paste a file that has just been
  moved away is offering a refusal.
- **The ceilings are the archive's** — ten thousand entries and two gigabytes,
  counted before anything is written ([D71](content.md)).
- **What was acted on is unticked.** Copy and Cut let the ticks go and say what
  was taken: left on, the tick was the only sign anything had been, and Paste
  aimed at the copied file rather than at the folder. The same holds for every
  action that was carried out — from the menu, a form, a download or a pair's
  bar — except that what it failed on stays ticked for another try
  (`ticksAfter` in `actions.ts`). What only shows something, and a form closed
  with Cancel, leave the ticks alone.

Known deviations:

- **A tree's pick is not let go.** In a catalog drawn as a tree, the one node
  acted on is where the tree stands rather than a tick, and stays picked.
- **The source-owned action still takes ids from its own connection.** D161
  lets the application copy files between two connections while keeping each
  node id paired with the connection that issued it.
- **A large copy has no internal progress or cancel.** D95 shows its request as
  an indeterminate process; the request still has no filesystem checkpoints.
- **There is no undo.** A move is a move.
- **The clipboard does not survive a reload**, and says so by being empty.

Spec: [Copying and moving files](../../decisions/2026-09-02-file-clipboard-design.md)
