# Universal search: live first, indexed later

Date: 2026-10-02. Decisions: D197 through D205. Their architecture home is
[search.md](../architecture/search.md), written by S1. They amend D76, D91 and
D134 where they say so.

Status: agreed on 2026-10-02, when the user asked for it to be built as
written; that answers the open questions below with the defaults this spec
states. Built slice by slice; what each slice ran is under
[Validation](#validation). The user's notes of the same day are the input: one search over
everything the application holds and reaches, live first, indexing added later
as a way to make it faster and wider where live is not enough. Where this spec
reorders those notes it says so in [What changed from the first notes](#what-changed-from-the-first-notes).
Revised the same day after a review of the first draft against the code: the
hit became a light pointer, outcomes are per cell, the answer is a stream,
Redis gets no node paths, and the slices were reordered.

## Outcome

The contract of an answer is the same at the end of every phase. A phase adds a
way to answer, not a second search.

**Phase 1, live.** A search button in the workspace header, and Ctrl+K (⌘K on
a Mac), open the search over whatever is on screen. Typing `auth` shows, within
a fraction of a second, a few rows in fixed groups: Connections; one group per
connection the person is working with, holding relations, keys, folders and
files found there by name; Favorites; Pipelines; Dashboards; Conversations;
Services; SSH keys; Guide; Source types. The best name matches stand above the
groups. Enter opens a Search tab holding everything found everywhere, filled in
as each place answers, and saying for every place what happened: searched,
stopped at a ceiling, did not answer in time, not searched and why. Looking
inside files is asked for, runs as a job in the footer, and lists files with the
line that matched. A found thing opens the way it opens from its own list; a
node can be shown in its catalog.

**Phase 2, names kept.** A connection's owner may let it keep a list of its
names. A large tree, a remote server or a large key space is then found by name
as fast as a local list, the row says how old the list is, and whatever the list
does not cover is still searched live.

**Phase 3, contents kept.** An owner may name a folder or a connection whose
contents are kept as text. Words inside those files are then found at once,
with the passage that matched.

**Phase 4, meaning.** Optionally, kept contents also get vectors from a local
model. A search then finds a paraphrase and the other language, merged with the
other hits by rank.

## What changed from the first notes

The notes put the line between the phases at "without an index" and "with an
index". The line that holds up is a different one: **the contract first, the
ways of answering second.** Live and kept are two ways to answer the same
question about the same place (D203), so the first phase is the contract plus
the live way, and every later phase is one more way behind the same contract.
Concretely:

- **Some things placed in the second pass belong in the first.** Metadata,
  timestamps, permissions, where a result came from and how old it is, partial
  results, timeouts, cost limits, deduplication, and "did not look" versus
  "found nothing" are not index features. They are the contract, and an answer
  without them is wrong the first time a slow server is asked (D198–D201).
- **Some things placed in the first pass do not belong in any.** Routing a
  query by guessing its intent with a model (seconds per keystroke, a cost per
  keystroke, the words sent to a third party) and a query syntax typed into the
  field. Deterministic rules and controls with a closed meaning do the same job
  and can be tested (D202, D205).
- **"Search the data in connections" is three different promises.** Names —
  relations, keys, folders, files — are cheap to ask live and are phase 1.
  Contents of files are minutes of reading, so live they are an explicit job
  (phase 1) and kept as text later (phase 3). Values in the rows of a database
  are neither: asked live they are a scan of somebody's production server per
  keystroke, and kept they need a person to say which columns mean something.
  They are out of this plan, and finding a value stays the grid's filter or SQL.
- **"Indexing" is two layers, not one.** A kept list of names (phase 2) is cheap,
  copies no contents, works for every source that has a catalog, and is the
  thing that tells a later contents pass what changed. A kept copy of contents
  (phase 3) is expensive and is a plaintext copy of somebody's documents. The
  first is needed earlier and for more sources than the second. Embeddings
  (phase 4) are the last layer, not part of the first index.
- **The application's own objects need no index at all.** Connections,
  pipelines, dashboards, keys, guide pages and saved-query titles are rows in
  the application's database or pages in memory; asking them is already the
  cheap path. What is encrypted there is searched by bounded decryption, never
  kept (D204).
- **Files are not the first thing kept.** The first kept layer is names, for
  every source; contents follow, and contents happen to exist mostly in
  document-like sources. The withdrawn design started its index with the
  explorer's file contents.
- **One ranked list across sources is not achievable and is not attempted.**
  Groups in a fixed order, one rule for how well a name matched, and no numeric
  score compared across places (D202).

## Evidence

### What exists

- **Search inside one connection (D76).** `SupportsNodeSearch` and
  `SearchesContents` in `backend/app/adapters/protocol.py`, models in
  `backend/app/adapters/search.py` (`NodeSearchRequest`, `NodeMatch`,
  `NodeSearchResult`: CatalogNodes from the listing's builder, `parent_id`,
  `location`, a 200-character `excerpt`, `complete` and `notice`). The text is
  matched as one case-folded substring, from one character. Routes
  `GET /connectors/{id}/catalog/search` and `/catalog/search-contents`, both at
  `read` through the one access funnel, not cached. Only the explorer implements
  them, so the file source **and SSH** search; PostgreSQL and Redis answer 501.
  The catalog's known deviation "Only the file source searches" is stale on SSH.
- **Bounds of that search.** 100 matches by default and 500 at most, 100,000
  entries looked at, 24 levels; contents read up to 8 MB a file and 256 MB a
  search locally, 1 MB and 32 MB over SSH (D152). Breadth first; links listed,
  never walked; not paged; nothing bounds it in time.
- **Which sources can search** is read off capability codes, a closed set of
  nine (`search`, `content_search`, …) derived by `issubclass` in
  `capabilities_of`. D13's sentence "today there is one" is stale.
- **`SupportsNodePath` is a gate.** `capabilities_of` grants
  `declared_references` to a source with rows and node paths, and
  `relationship_graph` to one with a relation model and node paths. Redis has
  rows and a relation model and no node paths, which is the whole of D195's
  withdrawal of both from Redis. D91 adds that a tree "is not filtered and not
  searched".
- **Searches over application data** are three, all substring, none indexed:
  the query library (title, and body by decrypting the newest 500), query
  history (executed text, the newest 500 of up to 1,000 retained), and the
  superuser's server log. Connections, dashboards, conversations and the type
  catalog — which also matches startable service templates, so `TimescaleDB`
  finds PostgreSQL — are filtered in the browser over lists already loaded;
  pipelines are not filtered at all.
- **The browser's lists are first pages.** Connections are loaded with the
  route's default of 100, and both ways of opening a node from elsewhere —
  `openIntent` behind the agent and `revealInCatalog` — look the connection up
  in that list, so a hit in the 101st connection would not open. The
  conversation list is 100 as well.
- **What is plaintext and what is not.** Connection names and non-secret
  options, pipeline names, dashboard and widget names, saved-query titles and
  SSH key names are plaintext. A managed service has no name of its own: it
  shows its connection's name as it was when the service was asked for. Query
  bodies and executed text are sealed under `QUERY_CONTENT_KEY` (D63);
  conversation, quick-chat and project titles and every message under
  `AI_CONTENT_KEY` (D141, which also says "no transcript search").
- **Who sees what.** Connections: owner or a grant, one predicate
  (`_visible_to` in `backend/app/connectors/crud.py`), no standing answered as
  if the thing did not exist (D33), no superuser bypass (D34), switched-off
  connections readable as rows and never asked (D20). A grantee's read runs
  under the owner's credentials. Dashboards: owner plus their own grants
  (D129). Pipelines, saved queries, conversations, services, keys, jobs: owner
  only.
- **Opening a thing from elsewhere.** The agent's `OpenIntent` (connector, node,
  view) is the only server-validated "open this" contract; its model is in
  `app.ai.models`, and its client half, `openIntent`, is a private function of
  `WorkspacePage.vue`. The dashboard intent is read once when its space is set
  up, so it is ignored once that space has been shown; the conversation intent
  is watched without `immediate`, so it is ignored the first time the AI space
  mounts; pipelines have no intent. Reveal in a catalog is state a panel takes
  (`revealInCatalog`), and moving a catalog to another level clears its filter,
  ticks and search results. Opening a panel while another space is shown brings
  Data forward, except what the agent opens, which floats.
- **The header** is the kit's `AppLayout`: a `header-start` slot (on the
  workspace: the first-panel toggle and a waiting pair, D167), space, the
  fullscreen toggle and the user menu; 42 px tall, tested at 768 px wide, and
  drawn under floating windows (layer 3000 over Quasar's 2000), which may cover
  it. There is no global keyboard shortcut anywhere, no debounce helper, and no
  editable combobox in the kit (`AppSelect` is select-only); `AppPopup` passes
  only its anchor and side to the `q-menu`, which takes focus when it opens.
  Terminals in the foot card own every key once ready (D148).
- **Long work** is an owned job (D81): owner required, a closed set of kinds,
  named steps, its input in `parameters` (plaintext, returned to the client),
  shown in the footer (D95), interrupted on restart, never pruned except
  pipeline runs.
- **Load.** A connector's pool holds 5 connections and the process 20 pools;
  past that the least recently used pool is closed under one lock. Catalog
  queries run without a statement timeout and inspection queries with 5 s. The
  read cache awaits its loads through `asyncio.shield`, so cancelling a cached
  read does not cancel the query. Worker-thread work shares AnyIO's default
  limiter with every route; only transfers have one of their own. The health
  monitor (D19) knows, per person while somebody watches, which connections
  are down.
- **Infrastructure.** The application database is the official `postgres:18`
  image; `pg_trgm` ships with it and is created by nothing; `pgvector` is not in
  it. There is no embedding model or call anywhere. The backend is one process
  (D124); the metrics collector is the precedent for a second one, building
  adapters with the owner's credentials and no pool (D127).

### What is broken and would be multiplied

A search across everything calls these many times at once, so they are fixed
first (S0).

- **Search words reach the log.** Uvicorn's access line carries the query
  string, D184 routes it into the rotated file, and nothing masks `search=` or
  `query=`. The library, history and catalog searches already write every word
  into a file a superuser reads, against D63's "neither stored nor logged".
- **The contents search's byte budget counts bytes it never read.** The size of
  every file it passes is added, including files skipped as too large or binary
  (`backend/app/adapters/explorer/search.py`), so one large file stops a search
  early with a notice that says it was read.
- **A failure in the middle of a walk loses the walk.** An `AdapterError` from
  SSH (a dropped connection, a key whose passphrase is not held) is not an
  `OSError`, so it ends the search with 502, discards what was found, and loses
  D147's `locked` kind, which is what lets a screen offer the passphrase.
- **The library and history decrypt on the event loop.** Up to 500 bodies of up
  to 1 MiB each, per keystroke, in async handlers.

A walk that cannot be stopped is the fifth such defect; it needs a change to
the capability's contract and is S4's.

### The withdrawn design

`dd1c64d` (2026-09-29) proposed D188–D194; `cb6cd86` (2026-10-01) reverted it.
Those numbers stay unused. It said the field never asks a connection's server,
that nothing is found inside a connection unless its owner made an index scope,
and its order of work started the index with the explorer's file contents,
then embeddings, with PostgreSQL names last.

This spec reverses its centre: phase 1 is exactly asking connections live, and
the first kept layer is names for every source. It keeps what was sound there
and says so where it does: providers handed in at assembly, groups rather than
one ranking, a result as a pointer, an owner naming what is kept, change known
from stored versions, deletion only by a complete enumeration, a row key that
leaves room for rows, a local model in a container of its own.

The legacy application's indexing, as that design recorded it from the code: a
folder was marked, a watcher ran every 60 seconds and took a file as changed if
its modification time fell in the last minute (so a missed pass lost a change),
chunk ids were `uuid5(user_id:path:chunk_index)` (so a rename re-indexed a file
and an edit near the top shifted every chunk), and the vector store lived inside
the file adapter, which is why it could only ever index files. Kept from it:
marking a place to keep, a model in its own container, chunking by structure.

## Terms

| Term | Meaning |
| --- | --- |
| Source type | A driver class and its options, registered in code (D1). |
| Connection | A configured source: address, credentials, grants, switched on or off, its owner's policies. |
| Node | A thing inside a connection, identified by `(connector_id, node_id)` (D21). |
| Application object | A thing the application itself keeps: a connection row, a pipeline, a dashboard, a saved query, a conversation, a service, an SSH key, a guide page, a source type. |
| Capability | What a source type can answer, as an optional protocol (D2). Catalog search is two of them (D76). |
| Provider | What the search asks: one kind of application object, or one connection. Not a source type, not a capability. |
| Place | Where a cell looks: an application object type, a connection, or a node of one. |
| Field | What a cell matches there, a closed set: `names`, `contents`; `columns` from S8. |
| Cell | A place and a field. The unit the plan chooses a way for and reports an outcome for. |
| Way | How a cell is answered: `live`, or `kept` (phase 2 on), or not at all. |
| Hit | One found thing: a pointer to it and why it was found. |
| Outcome | What happened to one cell in one answer. |

"Catalog search" means D76, the search inside one connection's catalog. "The
search" means this one. `app.adapters.search` is the capability and keeps its
name; the engine is `app.search`.

## D197. The search is one engine asking providers, and a source is not a provider

**A provider answers words with hits for its cells.** Two families:

- **Application providers**, one per kind of application object. A provider
  lives with its feature — queries, pipelines, dashboards, conversations,
  services — and is handed to the engine when the application is assembled in
  `app/main.py`, the way the job runner is handed its handlers (D81). The engine
  imports no feature. Providers for what sits below the engine — connection
  rows, SSH keys, the guide, the source types — live in the engine package; the
  service templates a source type is also found by are handed in by
  `app.services`.
- **Connection providers**, one per connection the person can read, built by
  the engine from the connection's `SupportsNodeSearch`. Nothing in the engine
  is written per source type: a type that gains the capability is searched, and
  one without it is reported with a reason (D201).

**The engine plans, asks, bounds and merges.** It is `app/search/`, placed in
the import layers between `app.transfers` and `app.jobs`: the features above
hand it their providers, and the jobs, connections, adapters and guide below
are what it builds on. It is added to every SDK-containment contract and to
`redis-cache-is-not-coordination` in `backend/.importlinter`, which list
modules by name and would otherwise let it import a driver or the shared cache
unnoticed. The node half of `OpenIntent` — the views a node opens in — moves
below it, into `app.adapters`, and the agent imports it from there.

**One route:** `POST /api/v1/search`. The words travel in the body (D200), and
the answer is a stream of lines (D201).

**Catalog search is not replaced.** The catalog's own button keeps its route,
and both it and the engine ask the same capability under the same matching rule
(D202), so there is one walk and one result shape.

Rejected:

- **A `DataSource` abstraction beside connections.** A second registry of what
  D1 and D2 already describe, and D2a's families again.
- **The browser calling one route per provider.** Simpler, and it would put the
  plan, the budget and the access rule in the browser; the same computation
  would then exist on both sides.

## D198. A hit is a light pointer with its evidence, never the thing

**A hit carries:**

- **target**, a union discriminated by kind:
  - `connection` — a connector id;
  - `node` — a connector id, the node id, `parent_id`, `location` in the
    source's words, name and kind; an optional `sub_key`, always empty in this
    plan, so a row could one day be a target without changing what a node
    target means; optional `ancestors`, the path from the root as the source
    states it (D202 below says why); and an optional `node`, the `CatalogNode`
    from the listing's own builder, which live always fills;
  - `object` — an application object type from a closed set, and its id.

  A chunk of a document is never a target: what matched inside a document is
  evidence about the document (D203).
- **title** and **detail**, written by the provider: the second line names the
  connection a node is in, the type of a connection, the owner of a dashboard
  shared with the person. A connection the person can no longer see is never
  named, the rule the library already follows for a document's connection.
- **facts**, structured where the place has them, for the Search tab to filter
  and sort by: the kind, when the thing itself last changed (a file's
  modification time, a pipeline's update), and its owner when it is not the
  person.
- **match**: the field that matched (`name`; `details`, such as a connection's
  host; `body`, such as a guide page's text; `contents`, a file's), its class
  (D202), an optional anchor (a line, a page or a range, which the live
  contents search already knows), and an excerpt.
- **The excerpt is text cut into segments**, each marked as a hit or not, at
  most 200 characters. No HTML crosses the API (D50) and no offsets either: a
  Python offset counts code points and a JavaScript one UTF-16 units, so offsets
  would mark the wrong letters after an emoji. Segments render with
  interpolation, the hit in `--dp-find`.
- **access**: the person's level where the thing has levels (a connection, a
  node, a dashboard), for what the row offers. It decides nothing (D199).
- **open**: an intent from a closed set the workspace already understands —
  for a node the views a node opens in (catalog, preferred, rows, structure,
  summary), for each application object type one intent of its own.

**Why a light pointer.** A node found live has its `CatalogNode` and opens like
a listed one, with its icon, viewers and actions, D76's argument. A node found
in what is kept (phase 2) may have only its id, name and place, and must still
be the same hit: the open registry works from the pointer and asks the node's
path (D21) when `node` is absent. Contents are never copied into an answer;
opening reads the source, and a node gone since says so (D21's 404) instead of
opening a stale copy.

**One hit per target.** A thing found twice in one answer — by name and by
contents, live and kept — is one hit: the better class wins (D202), and its
evidence and provenance come with it.

## D199. What may be found is decided before anything is asked

- **Connections are filtered by the one visibility predicate** inside the query
  that lists them: owner or grant. A connection the person has no standing on
  is never asked, never counted and never named. A search is not a way to
  discover connections; a share link is the only one (D61).
- **Ids from the browser are intersected with that set in the same query.** A
  connection named in the context hint (D200) or as a scope (D205) without
  standing is dropped with no outcome and no count; a scope naming one answers
  404 exactly as an unknown id does. Switched-off state is reported for visible
  connections only, so it cannot become an oracle the way D20's 409 before D33's
  404 would.
- **`read` is the level a search needs.** The engine resolves every visible
  connection in one query before it asks any, and builds each adapter from that
  row at `read` — the funnel's rule without its per-connection round trip.
- **A grantee's search runs under the owner's credentials**, as every grantee's
  read does (D33): the owner's server sees it as the owner's own load.
- **A switched-off connection is found by its name and never asked** (D20).
- **An application provider applies its feature's own rule inside its query**:
  owner only for pipelines, saved queries, conversations, services and keys;
  owner plus dashboard grants for dashboards (D129). The engine passes the
  person; it does not filter afterwards, which would lose results and leak
  counts.
- **No superuser mode** (D34). The server log stays the superuser's own tool
  and is not a provider.
- **Names kept as they were are not searched.** A share's labels, a pipeline
  card's labels and a declared reference's labels are copies taken when they
  were made; a hit on an old name is a wrong answer. A service is found by its
  connection's name as it is now, and by the kept name only while it has no
  connection.
- **The agent asks nothing by default** (S10): a provider is offered to it only
  by a decision of its own. Connections and their nodes, under D135, the guide
  and the source types are offered; the query library, history and
  conversations never (D133); objects somebody else owns, such as a dashboard
  shared with the person, never.
- **Encrypted content** follows D204.

## D200. A cell states its cost, and a mode spends only what it may

**Cost classes**, a closed set:

| Class | What it is | Examples |
| --- | --- | --- |
| `instant` | A bounded query of the application database, or a list in memory | connection rows, pipelines, dashboards, services, keys, guide pages, source types, saved-query and conversation titles |
| `cheap` | One bounded request to a connection's metadata | PostgreSQL's catalog by name; a small Redis database; a local tree walked by name within a time budget |
| `costly` | Many round trips, or a large bounded read | a tree over SSH; a large Redis database; PostgreSQL columns; saved-query bodies (D204) |
| `job` | Minutes | the contents of files |

**The class belongs to the cell and is stated without asking anybody.** One
provider has cells of different cost: saved-query titles are `instant` and
bodies `costly`; a PostgreSQL connection's names are `cheap` and its columns
`costly`. An application provider states its cells' classes. A source type
states its own through an optional protocol of its own, `StatesSearchCost`,
from the field and what the engine remembers of the connection's last search
(how much it looked at); a type without it is `costly`. Redis is `cheap` up to
a key count and `costly` above it or before its first search; the explorer is
`cheap` on local storage and `costly` over SSH. Nothing is asked of a server to
plan, so a dead server cannot hold the plan.

**Three modes:**

- **Typing**, after 150 ms without a key and at least two characters:
  `instant` cells everywhere, and `cheap` cells of the connections in the
  person's context only — the connections whose panels are open in the
  workspace, sent by the browser as a hint, current one first, at most eight.
  One deadline of 400 ms; what is late is dropped and counted in one quiet line.
- **Search**, on Enter or in the Search tab: `instant` and `cheap` everywhere,
  then `costly`, in one streamed answer. Cheap cells have 2 seconds, costly
  cells 10 seconds each and 20 seconds in all. At most 20 connections are
  asked, in a stated order — in context, recently opened (S6), then by name —
  and the rest are `skipped: not asked` with a gesture that asks them too.
- **Contents**: a job (S7), never on a keystroke and never implied by Enter.

**Bounds**, each a setting with a default and a ceiling:

- **One answer in flight per person.** A newer one cancels the older, in the
  browser (an abort) and on the server (its tasks). Identical cells asked by the
  same person in flight share one task; nothing is shared between people.
- **At most 4 connections asked at once, and one search at a time per
  connection**, so a person typing holds at most one of a connector's five
  pooled connections.
- **A connection that is not pooled is searched through a short-lived
  connection of its own**, the metrics collector's way (D127), so a fan-out
  never closes the pools other people's grids are using.
- **A PostgreSQL search runs under a statement timeout set to the time left**,
  not the inspection's 5 seconds; a query whose answer nobody waits for is
  cancelled on the server.
- **Worker-thread work for the search runs under one limiter of its own**
  (4 by default), so searches cannot take the threads every other route uses.
  The capability takes a deadline and a cancellation check as an argument of
  its own, not a field of the request model, and a walk checks both between
  entries and stops with `complete: false` and a notice.
- **Dead servers are not asked again and again.** A connection the person's
  health monitor (D19) last saw down is `skipped: unreachable`, with the time
  and "Search anyway". A connection that did not answer, or failed, is not
  asked by the same person again for a backoff that doubles like D19's, held in
  memory.
- **Application providers share one database session and run one after
  another**: they are `instant`, and a session is not shared between tasks.
- **Rows**: 5 a group while typing, 50 a cell in the Search tab, D76's ceilings
  below both. Words: at least 2 characters, at most 200 (D76's ceiling), at most
  8 words.

**Nothing is cached in this phase.** Catalog search is not cached today; a
typed query rarely repeats; and a cache would have to refuse answers cut by
time and keep its loads cancellable, which D31's does not. Coalescing in the
engine is enough.

**The server neither stores nor logs the words.** They travel in a POST body,
the engine never writes them, and a test types a marker word and asserts it
appears in no log line, no job row and no message on a socket (S0 makes the
same true of the existing searches). What the browser keeps is D205's.

## D201. An answer is a stream of cells, and says what happened to each

**The answer is a stream of lines** (newline-delimited JSON over the POST), one
line per cell as it finishes — its outcome and its hits — then one line for the
best matches (D202), then a closing line. Groups are drawn as their cells
arrive, and nothing already drawn is moved. A later phase that answers a cell
from what is kept sends the same line sooner. The browser reads it with a
hand-written reader, its line types tied to the server's models by a test, as
socket frames are (D18).

**An outcome per cell:**

- the cell — its place (an object type, a connection, or a node of one) and its
  field;
- `way` — `live` in phase 1, `kept` from phase 2, `none`;
- `as_of` — when what answered was read; absent means now;
- `status`, a closed set:
  - `complete` — it looked everywhere it was asked to;
  - `stopped` — it hit a ceiling, with the source's own notice (D76);
  - `late` — the deadline passed;
  - `failed` — a kind and a safe sentence; driver text never (D2c). `locked`
    (D147) stays its own kind, so the owner is offered the passphrase;
  - `skipped`, with a reason from a closed set: switched off, cannot search,
    unreachable, too costly for this mode, not in context while typing, not
    asked;
- `more` — whether asking this cell alone would find more.

**One cell's failure never fails the answer.** A 501, a `NodeNotFound`, an
`AdapterError` and a timeout each become that cell's outcome.

**"Nothing found" is said over cells**, and only when every cell asked was
`complete`. Otherwise the answer says where it did not look, as D76 separates
"nothing else matched" from "I stopped looking". A kept cell that found nothing
says how old its list is.

**What a person reads.** Outcomes are words, never codes:

| Status or reason | Sentence |
| --- | --- |
| late | Didn't answer in 2 s · Try again |
| unreachable | Can't be reached since 14:02 · Search anyway |
| not in context while typing | Not searched while typing · Press Enter |
| stopped | Stopped after 100 matches · Search only this connection |
| switched off | Switched off |
| cannot search | Can't be searched by name |
| not asked | Not searched · Search these too |
| locked, to the owner | Locked · Unlock the SSH key |
| locked, to a grantee | Locked by its owner |
| nothing found | Nothing found in all 12 places |

**Not paged.** The first N of each cell and its `more`. "More in this
connection" asks that cell alone with its full limit; there is no cursor across
cells, because there is no order across them to page through.

## D202. Groups in a fixed order, and one rule for how well a name matched

**Groups, in this order:** Connections; one group per connection, those in
context first; Favorites (saved queries); Pipelines; Dashboards; Conversations;
Services; SSH keys; Guide; Source types. From S9, Open tabs first. A group with
nothing in it is not drawn. A thing found in a connection, live or kept, by
name or by contents, is in that connection's group.

**One rule for words, in every place.** Words are split on white space; every
word must occur in the name, case-folded, in any order. Nothing is compiled: a
`*` is a character (D2c, D76). The rule is one pure function in
`app.adapters.search`, below both the engine and the sources, and catalog search
moves to it: **this amends D76**, whose text is today one substring. Typing
`2024 orders` then finds `orders_2024.csv` in the catalog and in the field
alike.

**Classes, best first:**

1. `exact` — the name is the words;
2. `prefix` — the name begins with them;
3. `word` — every word begins a word of the name, where `_`, `-`, `.`, `/`,
   `:` and white space separate words;
4. `substring` — every word occurs somewhere;
5. `text` — found in a body or in contents, not in the name;
6. `meaning` — reserved for phase 4: found by a model, not by the words.

**A source orders by class before it stops.** A walk that stops at its ceiling,
or a query with a `LIMIT`, must not drop the exact match for twenty substring
ones: the explorer keeps the best classes it has seen within its ceiling, and
PostgreSQL orders exact and prefix names first in the query. The engine then
classes every hit with the same function. A kept store, later, orders the same
way. One table of cases (words, name, class) is read by the tests of every
implementation, so none can drift.

**Inside a group:** class, then the provider's own `rank` where it has one (a
tree's nearness, a kept store's score), then the name.

**Best matches:** up to three `exact` or `prefix` hits from the `instant` and
`cheap` cells, above the groups, by class, then by how recently the person
opened them (S6), then by group order. They are sent once and never reordered
by what arrives later, and are not repeated below.

**No score is compared across places.** A connection matched by name and a
paragraph near by cosine distance are not on one scale, and a list merged from
them would be ordered by accident.

Rejected:

- **One list merged by a numeric relevance.**
- **A language model reading the intent of each query.** Seconds of delay, a
  cost per keystroke, and the words sent to a third party (D135).

## D203. Live and kept answer the same cell, and what is kept is never a provider

**A plan is a set of cells**: Connections × names; the `orders` connection ×
names; a folder of personal storage × contents. Each cell gets a way: live,
kept, or none with a reason.

**Phase 1: every cell is live or none.** The plan and the outcome already carry
the way, so the contract does not change later.

**From phase 2, what is kept claims a cell** when it covers that place and
field and is within its freshness window. Otherwise the cell stays live where
live is possible: keeping something never makes a thing unfindable that live
would have found. The matching rule is the same for both ways (D202 for names;
one rule for contents, phase 3). A hit from what is kept says `via: kept` and
its `as_of`, and the row wears D105's mark that it may be stale.

**What is kept is one store asked once** for every cell it claims. It is not a
group and not a provider among providers: a file found by name both live and in
the kept list would otherwise appear twice, and the plan would ask live what the
store had already answered. Its hits fold into their place's group.

**A chunk is evidence, never a target.** Hits from chunks fold into their node;
the best chunk becomes the excerpt and the anchor a viewer may open at.

**The request, the hit and the outcome do not change when a cell changes
way.** This is the property every later phase is held to.

## D204. Encrypted application content is searched by bounded decryption, never kept

- **Saved-query titles are plaintext** and matched in SQL, `instant`.
- **Saved-query bodies are matched only in Search mode**, through the
  library's own bounded decryption — the newest 500, D63's rule — in a worker
  thread under the search's limiter, checking for cancellation between
  documents, as a `costly` cell. Never while typing: a keystroke would decrypt
  up to 500 MiB.
- **Query history is not a provider.** A run is a record of what was executed,
  found in its own place (D63); in this field it would repeat the same SQL a
  hundred times.
- **Conversation, quick-chat and project titles are matched by decrypting the
  newest 500 of each** in a worker thread, `instant`: they are short. Their
  messages are not searched; D141 stands.
- **Nothing encrypted is kept by any phase.** A searchable copy of ciphertext is
  a plaintext copy (D63).

## D205. One search, opened from the header or by Ctrl+K, and hits open through the workspace's own intents

**Where.** `AppLayout` gains a `header-center` slot; the kit imports no
feature. The workspace page puts a compact search button there, drawn as a
field with its shortcut, which collapses to an icon by the room actually left —
measured, not by a breakpoint — so a waiting pair (D167), whose title is now
cut with an ellipsis, never overlaps it. Preferences and Admin have no search:
there is nowhere there to open a hit into.

**The search itself opens over everything**, at the popup layer, at the top of
the window: a floating window may cover the header, and a field under it would
take what is typed blind. The button and the shortcut open the same thing.

**Mod+K opens it**: Ctrl+K on Windows and Linux, ⌘K on a Mac — on a Mac, Ctrl+K
is the system's kill-line and stays so. It is the application's first global
shortcut and comes with the registry `WorkspaceScene` reserves a list for. It
is not taken while focus is in a terminal, whose keys are the shell's (D148;
Ctrl+K is readline's kill-line), nor while a dialog is open. The browser's own
Mod+K is prevented where it is taken.

**The popup** is a new kit component, a combobox over a grouped list, reusing
`AppSelect`'s option rendering (group headings, a second line, icons) and built
on `AppPopup`, which gains `no-focus`, `no-refocus` and `no-parent-event` so
focus never leaves the input. The active row is `aria-activedescendant`; no row
is active until an arrow is pressed; Enter opens the active row, or the Search
tab when none is, and the last row says "Show all results". The status line —
what is still being asked, what did not answer — is a polite live region. The
first Escape closes the popup and keeps the words; the second returns focus
where it was. Shown on `/ui-kit`.

**A scope.** Opened while a catalog panel has focus, the popup's first option is
"Search in ‹connection›", taken with Enter or the right arrow, removed with
Backspace. With it the plan asks that connection only, from the level the
catalog stands on — what the catalog's own button asks. In a tree (D91) the
scope is the grouping the tree is rooted in.

**Enter opens the Search tab**, a workspace panel with the role `navigate`, so
hits opened from it open beside it in the work column and it stays visible, as
a catalog does. It holds the whole answer, filters by group, connection, kind
and when changed, every outcome with its gesture, and "Search inside files",
which starts S7's job behind D76's confirmation and the same remembered answer.
Enter while Dashboards, AI or Pipelines is shown opens the tab in a window over
that space.

**Opening.** A hit's `open` intent goes to one client registry that maps each
intent to an action that exists. For that, S2 lifts `openIntent` out of
`WorkspacePage.vue` into `WorkspaceActions`, so the agent and the search turn
`(connector, node, view)` into a panel in one place; it takes whether to float
over the space being shown or bring Data forward, and hits opened while another
space is shown float, as the agent's do; it asks the server for a connection
that is not in the browser's first page, and says so when it is gone. S5 makes
the dashboard intent work once its space has been shown, makes the conversation
intent work on the AI space's first mount, and gives pipelines an intent. A
guide page opens the guide window; a source type opens New connection on it; a
service opens its tool at the foot of the screen; an SSH key opens Preferences
on it.

**Show in catalog** is `revealInCatalog`, D112's gesture, with two cases added.
A catalog holding search results, a filter or ticks is not wiped: another
catalog of that connection opens at the node's level instead
(`duplicateCatalog`). A catalog already on that level, showing search results,
leaves them before it marks the row. A node whose source has no node path —
a Redis key — is revealed from the hit's `ancestors`.

**What the browser keeps**: the last ten submitted searches, in session storage
for this tab, as D63 keeps drafts — never in local storage, never for words that
found a saved query's body, and cleared on sign-out. The Search tab keeps no
words in the saved layout or in a tab group (D94); restored, it is empty. An
empty search shows the recent searches and, from S6, what was last opened from
the search.

## What is kept, by phase: direction, not yet decisions

Each of these becomes a decision when its slice is designed in detail. They are
written now so that phase 1 builds nothing in their way.

### Phase 2 — names, kept

- **An owner's choice per connection**, off by default: "Keep a list of names
  for search", in the connection window, changed only by the owner, the way the
  transfer flag is (D135). A grantee sees the state.
- **Any source with a catalog.** A pass enumerates through a source's own
  enumerator — one catalog query for PostgreSQL, a `SCAN` for Redis, the
  storage's walk for the explorer — not `list_children`, which refuses a folder
  of more than 2,000 entries and would leave it never fully seen.
- **A row per node**: connector, node id, parent, name, kind, location, the
  `CatalogNode` itself with when it was read, so a kept hit is the same pointer
  as a live one (D198), a version token where the source has one (modification
  time and size for a file; PostgreSQL and Redis have none and are compared as
  sets of names), and the pass that last saw it.
- **Coverage per subtree, deletion per subtree.** A pass records which folders
  it saw completely; a row is deleted only under a folder enumerated completely
  and only when that pass did not see it. One dropped SSH connection never
  empties the list.
- **Matched by D202's rule**, backed by trigrams (`pg_trgm`, created by a
  migration; a concurrent index build runs neither inside Alembic's transaction
  nor in the application's process, the trap LangGraph's `setup()` already
  taught). Words shorter than three characters, which trigrams cannot serve,
  are answered live where live is possible.
- **The access filter is inside the query**, before ranking: the connection is
  readable by the person now and switched on. A revoked grant or a switched-off
  connection yields nothing from the list. A list switched off longer than its
  window is deleted.
- **Every pass runs in one worker process**, from phase 2 on, built like the
  metrics collector (D127): enumerating an SSH tree of 100,000 entries does not
  belong in the backend's one process (D124), and phase 3 must not move it
  there later. The backend reads pass state from rows, since the worker cannot
  announce on the socket; it gets a log name of its own; and it carries D127's
  trap of not starting with `docker compose up -d db backend`. Passes are not
  jobs — a periodic idempotent pass as a job would fill every footer and the
  job table — whereas a scheduled pipeline run is one (D179) because a person
  asked for that run. "Refresh now" is a request row the worker takes, and the
  connection window shows the pass.
- **A freshness window per connection**, chosen by the owner like D105's;
  beyond it the cell goes back to live.
- **What changes names in DataPlayer marks the list stale at once**: a DDL
  change, a rename, an upload, a delete, a transfer, an action that names a
  created or replaced node. Not a row edit, which would keep a busy database's
  list stale forever. The hook is handed in at assembly; writers import nothing
  of the list. Changes made elsewhere are seen at the next pass.
- **A plaintext copy of names, and it says so.** D101 encrypts every cache value
  that leaves the process because catalog names can be sensitive; a list the
  database must search cannot be encrypted, so this is the first plaintext copy
  of names at rest. It is the copy the owner agreed to; switching it off or
  deleting the connection deletes it in the same transaction.
- **Built with the owner's credentials**, as a grantee's live read already is.
  A key whose passphrase is held only in the backend's memory (D147) is never
  used by the worker; such a connection keeps its old list and says why.

### Phase 3 — contents, kept

- **An owner names a scope**: a connection and a node, with what it covers
  (formats, the largest file). The legacy "mark this folder", for any source
  that has contents.
- **Fed by phase 2's passes**: only what changed is read. Three layers against
  repeated work: an unchanged version is not read, an unchanged content hash is
  not extracted, a chunk whose text is already known is not recomputed.
- **Text is extracted by format, once.** The same extractor serves the live
  contents search and the kept one, or the two would disagree about one file.
  Extractors live in the explorer by the import contract; PDF and Office are new
  ones, added when asked.
- **One contents rule for both ways.** Live contents search matches a
  substring of a line, so `auth` finds `oauth2`; kept contents keep that rule,
  with trigrams over the chunks' text, and words shorter than three characters
  are answered live. A word-stem index would find less than live did for the
  same cell.
- **Chunks follow structure** with a locator — a page, a range of lines — which
  becomes the hit's anchor.
- **The access filter is inside the query**, as in phase 2.

### Phase 4 — meaning

- **A local embedding model in a container of its own**, behind an embedder
  protocol (model, dimensions, token ceiling, the query and passage forms,
  whether it sends data out). Vectors keyed by a chunk's text hash and the
  model; a new model is built beside the old one and switched to when complete.
- **Where vectors live is decided in that slice, by measurement**: `pgvector` in
  the application database means changing its image in `compose.yml` and both
  CI files; a store of its own follows the metrics store (D126).
- **Hits by meaning are class `meaning`**, fused with the words' hits of the
  same cell by rank, in their place's group. Live places are never searched by
  meaning.
- **The words a person types are embedded by the local model only.** An
  external embedding provider, if ever allowed, embeds passages of connections
  whose owner allows transfer (D135), during a pass, with the owner's key
  (D140); never the words of a search. Not built until asked.

### Rows of database tables

Not planned. A table is found by its name and its columns (S8); a value in its
rows is found with the grid's filter or with SQL. Keeping rows would need a
person to name a key, the text columns and a change column for each table; it is
designed when somebody asks for it, and the hit's `sub_key` is where it would
go.

## Rejected

- **The field never asking a connection's server**, the withdrawn D188. Names in
  a connection are cheap to ask, and modes, deadlines, the context limit and
  backoff bound what a keystroke costs. Waiting for an owner to build an index
  before a table can be found by name is the system built around the index that
  the user's notes argue against.
- **Indexing every connection by default.** A stale second copy of everything,
  a wider leak, hours of work nobody asked for.
- **Contents searched as one types.** D76 made it a gesture with a stated price.
- **A typed prefix language** (`in:`, `type:`). The scope option and the tab's
  filters say the same with closed controls. A prefix may come later and must
  parse into the same closed filter.
- **History, transcripts and the server log as providers** — D204, D199.
- **Node paths for Redis**, to show a found key in its tree. It would hand
  Redis the declared references and the relationships graph D195 withdrew;
  the hit carries its ancestors instead.
- **A cache of search answers in this phase** — D200.

## Slices

Each slice is built with its tests and verified with the checks ENGINEERING.md
names for the sides it touches. Each is useful on its own and its acceptance
depends only on slices before it. Phase 1 is S0–S10; phases 2–4 are listed to
fix the order and are designed in their own specs.

### S0 — corrections the search would multiply

- Access lines lose their query string, as the request context already does
  (D184).
- The contents search counts the bytes it read, not the sizes it passed.
- An `AdapterError` in the middle of a walk ends it with what was found,
  `complete: false`, the reduced sentence, and its error kind — `locked`
  included, so the catalog offers the owner the passphrase.
- The library's and history's decryption move to a worker thread.
- Stale documentation: SSH searches (D76's deviation), nine capability codes
  (D13), the history search window is the newest 500 of up to 1,000 runs (D63).

Acceptance: a marker word sent to each existing search route appears in no log
line; a search over a tree holding one 40 MB file and a matching small file
finds the small file over SSH; a walk whose storage fails halfway returns the
earlier matches; a walk that meets a locked key offers the owner the
passphrase; neither the library's nor the history's search decrypts on the
loop.

### S1 — the engine and the instant providers

`app/search/` with D197–D203's models, the planner over cells, modes, costs,
deadlines, cancellation, the limiter, per-person coalescing, the streamed
answer and its outcomes, the word rule and its table of cases;
`POST /api/v1/search`. Providers, all `instant`: connection rows (name, the
source type's title, host and database from the non-secret options), guide
pages (title, headings, body, in memory), source types with the service
templates `app.services` hands in. The type catalog window asks this provider
rather than keeping its own copy of the rule. A test provider that never
answers, so `late`, cancellation and the deadline are proven before anything
slow exists.

Acceptance: a connection is found by part of its name, its type and its host;
somebody else's connection is found by nobody; a superuser finds nothing more;
a switched-off connection is found and says it is off; a context hint and a
scope naming another person's connection, switched on or off, answer exactly as
an unknown id does; `TimescaleDB` finds PostgreSQL; a guide page is found by a
word in its body; a provider that never answers is `late` and the stream ends
on time; a newer request cancels the older; the marker word is in no log line.

### S2 — the search on screen

The header slot and button, the overlay, Mod+K and its registry, the popup kit
component and `AppPopup`'s new properties, debounce and abort, the stream
reader, recent searches in session storage, the open registry with `openIntent`
lifted into `WorkspaceActions` (float or bring forward; a connection outside the
first page fetched), and the intents for a connection, a guide page and a
source type.

Acceptance: Mod+K opens the search from inside the SQL editor and from a
maximized window, above it; Ctrl+K in a terminal reaches the shell; on a Mac,
Ctrl+K in the SQL editor deletes to the end of the line; Escape twice returns
focus; arrows, Enter and the live region work with a screen reader's
semantics; a connection found from the Dashboards space opens floating over it;
a connection outside the browser's first 100 opens; with a pair waiting on a
60-character name at 900 and 1024 px nothing overlaps; the header passes at
1280 and 768 px in every theme.

### S3 — the Search tab

The tab (role `navigate`), groups drawn as cells arrive, filters by group,
connection, kind and when changed, outcome sentences with their gestures, "more
in this connection", the scope option, the tab in a window over a covered
space.

Acceptance: a slow cell's hits appear after the others without moving them;
every cell not searched is listed with its sentence; "Nothing found" never
appears while a cell is late or stopped; opening a hit leaves the tab visible.

### S4 — names inside connections, live

Connection providers built from `SupportsNodeSearch`. **Amends D76**: the word
rule and class order (D202), a deadline and cancellation check as an argument,
a fourth bound — time — said in the notice, `ancestors` on a match, the error
kind on a result; the catalog's own button uses all of it. `StatesSearchCost`.
The context hint, the order and ceiling of connections asked, unpooled
connections for those not pooled, one search per connection, the statement
timeout, backoff and the health monitor's state, Show in catalog with its two
added cases.

- **PostgreSQL gains `SupportsNodeSearch`**: schemas and relations whose names
  hold every word, in one bounded query of `pg_class` and `pg_namespace` with
  `strpos` on bound values (so `%` and `_` are characters), exact and prefix
  names first, `LIMIT n + 1` for `complete`, nodes built by the listing's builder
  with one relation context per schema. `cheap`.
- **Redis gains `SupportsNodeSearch` and no node path**: a `SCAN` bounded by
  keys looked at and by time, not by matches (today's ceiling counts matches,
  so a rare word walks the whole database); names case-folded and matched in
  the process, since `MATCH` is case-sensitive and building `[aA]` classes from
  typed text would be compiling it; empty databases skipped by `INFO`; each
  match carries its ancestors, worked out from its name in `keyspace.py`.
  `cheap` up to a key count, `costly` above it. **Amends D91**: a key space is
  searched from the field; the tree itself still offers no search of its own.
- **The explorer** states `cheap` for local storage and `costly` over SSH, and
  keeps the best classes it has seen within its ceilings.

Measured on the way: the time each source takes for a name search on the
development data, recorded under Validation and used to set the deadlines, the
connection ceiling and the Redis threshold.

Acceptance: `class` typed with a PostgreSQL connection open finds `pg_class`
(a test against a catalog that always holds hundreds of rows, not an empty
schema); `100%` finds nothing rather than everything; `2024 orders` finds
`orders_2024.csv` in the field and in the catalog's own search; an exact name
is not lost behind a hundred substring matches; a key found in a Redis database
of a thousand keys is shown in its tree; the Redis capability codes are
unchanged; a Redis database above the threshold is searched on Enter and not
while typing; a server that does not answer is `late`, the other groups are
drawn, and it is not asked again within its backoff however often Enter is
pressed; a newer keystroke cancels the older walk and the older PostgreSQL
query; a search over 25 connections closes no pool another person is using;
Show in catalog keeps a catalog's contents search on screen.

### S5 — every application object

Pipelines, dashboards (owned and granted), favorites (titles while typing,
bodies in Search mode, D204), conversations, quick chats and projects by title
(D204), services by their connection's name, SSH keys. The dashboard,
conversation and pipeline intents.

Acceptance: each type is found and opens where it lives; somebody else's
pipeline, conversation or key is found by nobody; a dashboard shared with the
person is found and names its owner; a saved query is found by a word in its
body only after Enter, and ten rapid Enters leave at most one decryption
running; a conversation is found by its title and never by its messages, and
opens from the field before the AI space has ever been shown; a dashboard opens
from the field with the Dashboards space already shown once; a service is found
by its connection's new name after a rename.

### S6 — what was opened recently

The browser keeps what was last opened from the search — the target only, a
kind and ids, at most 50, per person and server in local storage (D99), where
the workspace layout already keeps node ids — and sends it as a hint. The
server answers it through the same visibility filter, so nothing from a
connection the person can no longer read is named. An empty search lists them;
recency orders the best matches. Nothing is stored on the server.

Acceptance: what was opened comes back first; after a grant is revoked or a
connection switched off, the empty search shows nothing from it; a hint naming
another person's connection changes nothing in the answer.

### S7 — inside files, as a job

A job kind `search.contents` over the connections chosen in the tab that have
`content_search`; D76's confirmation and remembered answer; D76's and D152's
bounds per connection and one total; one at a time per person; Stop. The job's
handler lives in `app.search`, above `app.jobs`. **The words, the chosen places
and the matches are held in the backend's memory, keyed by job id, for 30
minutes**, and never written to the job's row: `parameters` carries counts, the
step and message never quote the words, and a failure is recorded as private.
The matches are read through a route that answers 404 unless the caller owns
the job and drops matches from a connection the caller can no longer read. Once
they have expired the job's entry in Recent says so and offers to search again.
Finished jobs of this kind are pruned to the newest 20 per person. The memory
they live in is one more line in D124's table of what is process-local.

Acceptance: a word inside a local file and inside a file over SSH is found,
with its line; the job is in Working and then Recent; Stop ends it with what was
found; the marker word is absent from the job row, `GET /jobs` and the log;
after a restart the job is interrupted and its matches are gone.

### S8 — names inside relations

The field `columns` for PostgreSQL: column names and comments, and relation
comments, matched in Search mode (`costly`); a hit is its relation, with the
column or comment as the excerpt. No column node kind.

Acceptance: `email` finds the tables that have such a column and says which;
a table comment is found by a word in it.

### S9 — places the browser holds

Open tabs, windows and tab groups (D94), which only the browser knows: their
titles go to the server in the request, bounded, and are classed there by the
same rule; nothing of them is stored. They open by activating the tab or
restoring the group.

Acceptance: an open tab is found and activated; a tab group is found and
restored after D94's warning.

### S10 — the agent

**Amends D134**: the agent gains a `search` tool over the providers offered to
it (D199), bounded like the other tools, with D135 checked per connection; it
asks live only the connections attached to the conversation, or in context.
"Ask the agent" as the popup's last row puts the words into a new
conversation's composer, unsent.

Acceptance: the agent finds a table by name across the connections it may use;
a connection that does not allow transfer is named in a refusal and nothing of
it reaches the model; no saved query, conversation, pipeline or shared
dashboard is ever in its results.

### Later phases

- **S11 — names kept** (phase 2), its own spec.
- **S12 — contents kept** (phase 3), its own spec.
- **S13 — meaning** (phase 4), its own spec.

## Testing

- **Pure:** the word rule and its classes (one table of cases, read by every
  implementation's tests); the planner (cells, modes, costs, context, skips,
  the connection ceiling); outcomes and their sentences; excerpt segments,
  emoji included.
- **Backend:** each provider with an owner, a grantee, a person with no
  standing and a superuser; browser-supplied ids without standing; a
  switched-off connection never contacted; a source without the capability
  reported with its reason; deadlines, cancellation and the thread limiter with
  a source that never answers; the marker word absent from every log line, job
  row and socket message; PostgreSQL against the system catalog; Redis and SSH
  behind the service registry, skipped without their servers.
- **Browser:** debounce and abort, the stream reader, the intent registry,
  segments rendered as text; Playwright for Mod+K (and not in a terminal),
  typing, Enter, a hit opened from each space, Show in catalog, and the header
  at its widths.

## Open questions for the user

1. While typing, the search asks only the connections open in the workspace,
   and everything else on Enter. Or should typing ask no connection at all?
2. Conversations are found by title and never by their messages. Enough?
3. Saved queries are found by a word in their SQL only after Enter, among the
   newest 500. Enough?
4. Should a list of names be kept by default for personal storage, where
   nothing leaves the server, while every other connection waits for its
   owner?
5. Values in database rows stay out of this plan. Agreed?
6. What made the withdrawn design wrong? This spec assumes its centre — no live
   search, the index first — and keeps its parts; anything else there that must
   not come back?

## Validation

Each slice records here the checks it ran and their results, and S4 records its
timings.

- **S0.** `pytest` over the log, file-search, catalog-search, library and
  history routes and a marker test across every search route: green. The SSH
  test of a 40 MB file beside a small match was red on the old byte count and
  green on the new one. `ruff`, `mypy`, `lint-imports`, `check-docs`;
  `vitest` for the catalog level, `type-check`, `lint`: clean.
- **S1.** `pytest tests/search` (57: the word table, excerpts, the planner, the
  route's acceptance cases, a provider that never answers, a newer request
  ending the older) and the connector, agent and guide tests the refactors
  touched: green. `ruff`, `mypy`, `lint-imports`, `check-docs`; `vitest` for the
  stream reader and the type catalog, `type-check`, `lint`: clean. The type
  catalog's E2E runs with S2's, against a rebuilt backend.
- **S4, S8.** Search, adapter, route and health tests: 307 passed, 1 skipped;
  the full backend suite 3,763 passed, 11 skipped. Each review fix was red
  before it. Timings on the development data (median of 5): PostgreSQL names
  17–47 ms on a connection of its own, 3–6 ms through an open pool; columns
  3–8 ms; local files 3 ms for 32 entries, 20–23 ms for 1,020, 420–500 ms for
  20,200; SSH 57 ms for 19 entries signing in, 385–511 ms for 2,040; Redis
  19–28 ms for 1,000 keys, 160 ms for 20,000, 660–760 ms for 100,000. They
  keep the 0.4 s typing deadline for PostgreSQL and small local trees, make SSH
  costly, and set `SEARCH_CHEAP_KEYS` at 20,000.
- **S5, S6, S9 (backend).** `pytest tests/search tests/pipelines tests/metrics
  tests/queries tests/services tests/ai`: 742 passed; each review fix red
  before it.
- **After merging S4–S9.** `pytest tests/search` and every provider, adapter
  and route search test: 350 passed, 1 skipped. Coalescing was reconciled: an
  answer joins a task in flight within 0.25 s of its deadline.
- **S2, S3 and the open intents.** `vitest` 2,362 passed, `type-check`,
  `lint`: clean. The full E2E suite, run by the user: 362 passed, 4 failed
  (Markdown's diagram, a PDF twice, the 3D graph). All four passed on a rerun:
  the dev server had found Mermaid, pdf.js and three.js only when a lazily
  loaded panel first imported them and reloaded the page mid-test. They are now
  pre-bundled at start (`optimizeDeps.include` in `vite.config.ts`), and the
  four pass against the restarted server.
- **Not built:** S7 (contents as a job), S10 (the agent), and the browser's
  halves of S6 and S9 — the field sends neither what was opened nor open tabs.
