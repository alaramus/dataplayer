# Declared references

A reference a person draws, as opposed to a foreign key the source declares
(D36). The application keeps the line; neither source is changed. A reference
can join columns in different connections and source types when both adapters
support node paths and equality lookup.

Read [relations.md](relations.md) first for what a reference is and how one is
followed. Redis has no declared-table overlay and cannot be an endpoint of a
declared reference; its CSV and clipboard support remains (D195).

Decisions here: D106, D107, D108, D170, D172, D173, D195.

## D195. Redis keeps CSV and clipboard transfers, without table overlays or declared references

The Redis source remains a keyspace grouped by the colons in key names (D91).
The table overlay introduced by D170 and Redis's participation in declared
references introduced by D172 are withdrawn. D173's table editing path is
withdrawn with them.

- **No declared-table API or storage.** Redis folders remain folders; there is
  no table offer, proposal, declaration, special catalog node or table grid.
- **No Redis endpoints for declared references.** The general D106–D108
  feature remains available to adapters that implement row lookup and node
  paths. The structure section is gated by `declared_references`; Redis does
  not implement node paths.
- **Copy, Paste and Redis CSV remain.** Keys, folders and databases keep the
  relation model needed to name their CSV columns, the D44 whole-node export,
  and the existing copy-to-CSV paste flow (D171). This relation model does
  not enable the Relationships graph UI.
- **The Relationships graph has a separate capability.** A source offers it
  only when it supports both relation models and node paths. Redis has no
  node-path capability and cannot be a declared-reference endpoint.

Spec: [Removing Redis table overlays and declared references](../../decisions/2026-09-29-redis-removal-design.md)

## D173. Redis table editing was withdrawn

Redis no longer has declared tables to edit. This decision is retained here as
design history; D195 withdraws its implementation.

Spec: [Editing a table declared over Redis](../../decisions/2026-09-26-redis-table-editing-design.md)

## D172. Redis tables were withdrawn as declared-reference endpoints

Redis no longer has declared tables or participates in declared references.
The general reference contract in D106–D108 remains for supported sources.

Spec: [References to and from a Redis table, by its key](../../decisions/2026-09-26-redis-references-design.md)

## D170. The Redis table overlay was withdrawn

Redis folders are no longer described as tables. D171's CSV support for raw
keys, folders and databases remains in [transfer.md](transfer.md).

Spec: [Tables declared over Redis, and Redis saved as CSV](../../decisions/2026-09-25-redis-tables-design.md)

## D106. The application keeps references no source has

A declared reference is a row of the application's own with two ends. An end is
a connection, a node in it, and one of that node's columns.

- **Both ends are navigable and neither is the key.** Which end a person is
  standing on is decided by the relation they are looking at, and the answer —
  the rows where the far column equals this value — is the same statement from
  either side. A `swap relation` button would choose only which badge gets
  drawn.
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
  arrow, the tooltip and the click are the ones D36 built. A diagram draws it
  too, as a line of its own colour between the two columns (D97). The name is issued by
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
└── declared_routes.py  GET / POST /declared-references, DELETE one

backend/app/adapters/
└── redis/model.py      relation columns used to export raw Redis nodes as CSV

frontend/src/features/declared/
├── api.ts              the list, and what drawing or removing one invalidates
├── model.ts            which end you are standing on, and how it reads
├── DeclareReferenceDialog.vue        one window, both ends
└── DeclaredReferencesSection.vue     the list, beside constraints and indexes

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
