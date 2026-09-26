# Declared references and tables

A reference the person drew, as opposed to one the source declares. D36 covers
the second: a foreign key, read from the source, followed within one connection.
This file covers a line somebody draws by hand between two columns that no
source knows are related — including columns in two different connections and
in two different kinds of source — and a table somebody declares over keys a
source keeps without structure (D170).

Neither source is changed. The line is a row in the application's database,
and the table is kept with its connection.

Read [relations.md](relations.md) first for what a reference is and how one is
followed; nothing here replaces that path, it adds a second issuer to it.

Decisions here: D106, D107, D108, D170.

## D170. A folder of Redis hashes can be declared a table

A person can say of a Redis folder: its keys are hashes, and these fields are
the columns. Redis has no word for that, so the application keeps it, and the
driver shows it.

- **Kept with the connection**, in the connector row's `declared_tables`, never
  in Redis: everybody who reads the connection sees it, and it goes with the
  connection. It reaches the driver through `AdapterContext.declared_tables`;
  a driver without `SupportsDeclaredTables` ignores it.
- **Declaring, changing and removing need `structure`**, the level that changes
  a table's structure elsewhere; asking whether the command applies needs
  `read`. One table per folder; a second declaration over the same folder
  replaces the first. Removing forgets the description and touches no key.
- **The driver answers three things** about a node: where a table over it would
  stand (`table_place`: a folder, or the table already over one; anything else
  is refused "Select a folder to describe as a table"), a proposal read off the
  folder, and the declaration it would keep, refusing a column called `key`.
- **The proposal** is the fields of the first hundred hashes directly in the
  folder, by name, each read with one bounded `HSCAN`; a type is guessed from
  every sampled value — number, boolean, date and time, else text. A declared
  table proposes its own columns first, ticked, and what else the sample holds
  unticked.
- **In the catalog** a `TableNode` with id `t<db>:<prefix>` stands right after
  its folder, named as declared, saying `over user:` where a table's row count
  would be. The folder stays as it was.
- **Opened, it is a grid** of one row per hash directly in the folder, in key
  order: `key` — the name within the folder — then the declared fields, a
  missing one empty. A key of another type is not a row, and
  `FetchResult.notice` says how many were left out. At most 100,000 keys under
  the folder are read, the first by name of those scanned, and the notice says
  when there were more. Nothing is editable, sortable or filterable.
- **Every Redis node reads as a relation** (`SupportsRelationModel`): a key its
  type's columns (kind `key`), a folder or a database the listing's four
  (`key_listing`), a declared table `key` and its fields (`declared_table`).
  The columns of each are said once, in `redis/shapes.py`, for the grid, the
  model and the export alike. **Every node has a path** (`SupportsNodePath`):
  database, folders, then the node, a folder derived from its name rather than
  scanned for.

Known deviations:

- **Each page scans the folder again**, up to its ceiling, and asks every key's
  type: the rows are paged over hashes the scan found, and nothing keeps the
  list between pages but the read cache.
- **A hash's field named `key` cannot be a column**: the first column has that
  name.

Spec: [Tables declared over Redis, and Redis saved as CSV](../../decisions/2026-09-25-redis-tables-design.md)

## D106. The application keeps references no source has

A declared reference is a row of the application's own with two ends. An end is
a connection, a node in it, and one of that node's columns.

- **Both ends are navigable and neither is the key.** Which end a person is
  standing on is decided by the relation they are looking at, and the answer —
  the rows where the far column equals this value — is the same statement from
  either side. The old application had a `swap relation` button, and all it
  chose was which badge got drawn.
- **It belongs to the person who drew it**, and it is visible only while that
  person can still read both ends. A revoked grant ([D33](../backend.md)), a
  disabled connection or a deleted one takes the arrow off the screen rather
  than leaving one that answers 403.
- **One column at each end.** A real composite key is read from the source and
  is D36's business; a composite declared one needs a column-pairing screen and
  has nothing asking for it.
- **The same pair drawn twice is the same row.** The two ends are ordered
  canonically before a fingerprint is taken, so drawing A→B and B→A once each
  leaves one reference, held by a unique constraint rather than by the lookup
  before the insert.
- It reaches the grid as an ordinary `FetchResult.references` entry, so the
  arrow, the tooltip and the click are the ones D36 built. The name is issued by
  the application and names both the reference and the end being stood on, so a
  node referenced to itself still offers two distinct ways out.
- The node's own label is copied in when the reference is made, the way a share
  copies one ([D58](../sharing.md)), because naming a node means asking its
  source. The connection's name is read live, because the viewer holds `read` on
  it by the rule above.

Known deviations:

- **Private to its author.** Sharing one asks who owns a line between two
  connections, and nothing needs the answer yet.
- **A page costs one more query.** The references of a node are looked up on
  every fetch, after the read cache rather than inside it: what a source
  produced is the same page for everyone, and which lines this person has drawn
  over it is not.

Spec: [A reference the person draws](../../decisions/2026-09-05-declared-references-design.md)

## D107. A declared reference is checked against both sources, when it is made and when it is followed

The application composes no SQL and takes no identifier from the client except
the reference's own name.

- **When it is made**: the caller must hold `read` on both connections, each
  node must exist and be readable as rows, each named column must be among the
  columns that node states now, and each must admit equality lookup. A source
  that cannot look a value up in a column cannot be an end of a reference, and
  refusing at that moment beats drawing an arrow that fails on every click.
- **When it is followed**: the far end is read again — the grant may have gone,
  the connection may have been switched off, the file may have been rewritten
  with different headers. The predicate is built from that reading and is an
  equality filter in the closed vocabulary of [D2c](contract.md), which the
  target's own fetch then validates a second time.
- The two answers are D36's. `NoReferencedRows` with a reason for a row whose
  cell is empty and for a column that has stopped admitting equality;
  `ReferencedRows` otherwise. Neither is a failure of the request
  ([D2d](contract.md)).
- The follow route answers the names it issued itself and never hands one to an
  adapter. The name carries the reference's id under a reserved prefix, so this
  is a lookup and not a guess.

Known deviations:

- **The far end is read with a one-row fetch.** It is the only capability every
  source states its filterable columns through. The read cache absorbs the
  repetition, and nothing measures it yet.

Spec: [A reference the person draws](../../decisions/2026-09-05-declared-references-design.md)

## D108. A followed reference names the connection it lands in

`ReferencedRows` said where to go but not whose it was, because the answer used
to be always the connection that was asked.

- It now carries the connection — id, name and adapter type — and the workspace
  opens the target's tab there instead of in the tab the click came from.
- It is filled in by the route, not by the adapter: an adapter knows itself and
  not its own identity, and the route is the one place that knows which
  connection it just asked. For a key inside one source it is that same
  connection.

Spec: [A reference the person draws](../../decisions/2026-09-05-declared-references-design.md)

## Where the code is

```
backend/app/connectors/
├── declared.py         the row, its two ends, the names this module issues,
│                       reading an end against its source, the references of
│                       one node, and following one
├── declared_routes.py  GET / POST /declared-references, DELETE one
├── tables.py           the declared tables a connector row keeps (D170)
└── table_routes.py     /connectors/{id}/tables: offer, proposal, PUT, DELETE

backend/app/adapters/
├── declared_tables.py  a declaration, a proposal, `SupportsDeclaredTables`'s
│                       answers
└── redis/tables.py     where one stands, the sample, the rows of a table;
                        `model.py` and `export.py` beside it read every node

frontend/src/features/declared/
├── api.ts              the list, and what drawing or removing one invalidates
├── model.ts            which end you are standing on, and how it reads
├── DeclareReferenceDialog.vue        one window, both ends
└── DeclaredReferencesSection.vue     the list, beside constraints and indexes

frontend/src/features/catalog/
├── declaredTable.ts         the window's decisions: draft, added field, why not
└── DeclareTableWindow.vue   "Describe as table", from the catalog's menu
```

The catalog walk both this and D43 need is `frontend/src/features/catalog/NodePicker.vue`.

## Something to try it on

The development stack draws two of them itself, in `app/seed_references.py`,
between whatever connections the developer already has: `demo_lab.organizations`
to `accounts.csv` in personal storage, and `accounts.csv` to `renewals.csv`
beside it. Both are keyed by a slug neither source says anything about. The
seeder makes no connection of its own — what a machine is connected to is not
a fixture — so a stack whose file source was registered a moment ago gets its
examples on the next start.
