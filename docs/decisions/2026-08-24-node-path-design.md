# The source itself says where a node lives

Date: 2026-08-24
Status: agreed
Round: 7d

## Goal

Remove the shortcoming recorded in the previous round: "show in catalog"
works only when the node already lies on the level being shown. Go into
another folder, tick another schema or reload the page — and the button on
the table tab opens the catalog but finds nothing in it.

The right move is named there as well: an adapter capability "path to a node".
The source knows how its own ids are built; the client does not and must not.

## The framing that was wrong

The task arrived as "table and connection names coincide, collisions will
start, a single key made of the connector id, the schema and the name is
needed".

There are no collisions. A table's identity in the application is already
composite — the pair `(connectorId, nodeId)`, where `connectorId` is a UUID and
`nodeId` is built by the source itself: postgres writes `public.users`, the
file source writes a path. The pair lives in `rowsPanelId`, in vue-query keys,
in the body of every request. Two `users` from two databases are two different
tabs already today.

The real half of the complaint is the second one: from a `nodeId` alone there
is no way to reach the level the node lies on. That is the subject of this
round. A single string key is not introduced: while the server owns the
parsing, a string form of a reference is pure encoding of the pair, which is
added later as one function and breaks nothing.

## Decisions

### R1. The capability is optional

`SupportsNodePath` next to `SupportsCatalog`, a `runtime_checkable` protocol;
the route checks `isinstance` and answers 501. This is the letter of D2: the
contract requires a minimum, everything else is separate capabilities.

Rejected: folding it into `SupportsCatalog` ("if you can show children, you
can say the path"): a source whose id is an opaque handle of someone else's API
with no reverse lookup would be forced either to lie or to have no catalog at
all. Exactly the coercion D2 exists to prevent.

Also rejected: a mandatory method with an honest refusal value: two ways to
say "no" instead of one, and nothing to check that the source actually tried.

### R2. The answer is a chain of full nodes, the target last

```python
async def path_to(self, node_id: str) -> list[CatalogNode]:
```

From the root to the target inclusive. The connection root is not part of the
answer: the root is the connection itself, and the caller already knows what
it is called.

Full `CatalogNode`s, not lightweight `{id, name}` crumbs. Lightweight ones
would be enough for crumbs, but that would be a second node model next to the
existing one, and `name` in a crumb and `name` in a node would diverge in
meaning at the first person who wants an icon in a crumb. The last element of
the chain also answers the question "what is this" — with `kind`, the row
estimate and everything the node knows about itself. The same call, unchanged,
will serve a future "resolve this reference for me".

`NodeNotFound` is a separate exception, not `AdapterError`. `AdapterError` is
declared as a source refusal reduced to safe values; "there is no such node" is
not a refusal but an answer, and the route turns it into 404, not 502.
Returning `None` was rejected: there is already a rule next to it, "an empty
list means an empty node, never a refusal", and a second way to say "no" would
read ambiguously.

### R3. The path on the server and the crumbs on screen are not the same thing

In postgres a schema is a `SchemaNode`, and its role on screen is `group`: a
schema is not a level one enters but a filter chip over the list. The table
`public.users` lies on the root level of the catalog, under the ticked
grouping `public`. For files a folder is a `container`, a real level.

So the server's chain is translated into screen state, and the translation is
done by the node's role — the same `roleOfKind` table that already lets the
catalog never ask which source is in front of it:

- an ancestor with the role `container` is a crumb;
- an ancestor with the role `group` is a ticked grouping;
- the level is the last container among the ancestors, or the root.

Postgres: `[schema public, table users]` → stay on the root, tick `public`.
Files: `[folder a, folder b, file x]` → crumbs `a/b`, the level is id `b`.
A source with the levels "database → schema → table" fits into this without a
single new branch. The translation lives in `features/catalog/location.ts` as
the pure function `locationOf`, like `nodes.ts` and `rows.ts`: it is checked
without mounting.

### R4. Always ask, move only if needed

The path is requested on every "show", not only when the node is not visible.
One road in the code instead of two, and the answer is cached by vue-query, so
the second click is free.

But always rereading the level is wrong: `show()` resets the ticks and the
filter, and a click on the tab icon would wipe the user's checkboxes on a
level where the wanted table is visible anyway. Hence a guard: if the catalog
already stands on that level and the needed groupings are already ticked — we
do not move, we only highlight. The guard compares level ids for equality; the
client still parses nothing.

### R5. The panel resolves the path, not the page

`WorkspaceActions` does not change: `revealInCatalog(connectorId, nodeId)`
still finds the connection, opens the catalog and puts down the target. The
path is requested by `CatalogPanel` — it owns the level and the loader, and the
page must not know about the catalog's internals. The hand-over through state
is already arranged so that the panel may not be mounted yet, and that stays
true.

### R6. Failure according to its nature

- **501** — the source cannot walk back. This is its permanent property, not
  an event: we silently highlight by id, that is, exactly today's "works if the
  node is visible anyway". A message here would be unfixable and change
  nothing.
- **404** — the node existed and disappeared while the tab sat open. This is
  news: a toast, the catalog opens anyway, no highlight. It also closes a hole
  that currently has no answer at all — a tab survives the removal of its table
  and says nothing about it.
- **Anything else** — the network, the source went down: a toast with the
  error text, the catalog opens.

## What is done

**Server.** `SupportsNodePath` and `NodeNotFound` in `adapters/protocol.py`;
`path_to` in `postgres/catalog.py` (parsing `schema[.relation[.column]]` with
the same `partition` as `list_children`, and building the nodes with the same
queries, but for one object) and in `file/catalog.py` (the path goes through
the **existing** session containment rule, so `..`, an absolute path and a
segment with a drive letter are refused by the same code);
`GET /connectors/{id}/catalog/path?node_id=...`, where `node_id` is required —
the root has no path; a line in `capabilities_of`, with the same `issubclass`
as the others.

**Screen.** `locationOf` in `features/catalog/location.ts`; `showLocation` in
`useCatalogLevel` — sets the groupings instead of resetting to the default and
carries the guard from R4; the path loader in `features/catalog/api.ts` with
the key `["nodePath", connectorId, nodeId]`; `CatalogPanel`, having taken the
target, resolves the path, moves where needed and calls the existing
`useFadingMark`.

**Documentation.** D21 in the AGENTS.md table, its home in
`docs/architecture/adapters.md`; the known shortcoming in `workspace.md` — "a
node not on the shown level is not found" — is removed with a reference to D21.

## How it is checked

Server:

- postgres `path_to`: a table gives `[schema, table]` with the right `kind` and
  ids; a column — three links; a nonexistent relation and a nonexistent schema
  — `NodeNotFound`;
- file `path_to`: a nested file gives the folders and the file; `..`, an
  absolute path and a segment with a drive letter are refused; a missing file —
  `NodeNotFound`;
- route: the chain; 404 on a vanished node; 501 for a source without the
  capability;
- `capabilities_of` names the new capability.

Screen:

- `location.spec.ts`: schema as a grouping → root plus a tick; nested folders →
  crumbs and level; a path of one element → root with no groupings; the mixed
  case of a container plus a grouping;
- `useCatalogLevel.spec.ts`: `showLocation` sets crumbs and groupings; on a
  matching level with the groupings already ticked the level is not reread and
  the ticks stay;
- Playwright, and this is the only real proof: open a table from a schema,
  take the catalog to another schema and another folder, click the tab icon —
  the catalog returns to the right level, the right grouping is ticked, the row
  is outlined; the same after a page reload, when the tab is restored from
  storage and nothing is open in the catalog.

## What this round does not include

- a string form of a node reference;
- the agent and anything it would require;
- highlighting in the other direction — from the catalog to an open table tab;
- going to a node from a link in the browser address bar.
