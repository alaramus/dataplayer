# Universal search: live first, indexed later

Date: 2026-10-02. Decisions: D197 through D205, proposed. Their architecture
home will be a new `docs/architecture/search.md`, written by the first slice
that builds them; until then they live here only and are not in the AGENTS.md
table.

Status: proposed on 2026-10-02 in discussion with the user. Not agreed, nothing
built. The user's notes of the same day are the input: one search over
everything the application holds and reaches, live first, indexing added later
as a way to make it faster and wider where live is not enough. Where this spec
reorders those notes it says so in [What changed from the first notes](#what-changed-from-the-first-notes).

## Outcome

The contract of an answer is the same at the end of every phase. A phase adds a
way to answer, not a second search.

**Phase 1, live.** A field in the workspace header, focused by Ctrl+K (⌘K on a
Mac). Typing `auth` shows, within a fraction of a second, a few rows in fixed
groups: Connections; In connections — relations, keys, folders and files found
by name in the connections the person is working with; Saved queries;
Pipelines; Dashboards; Conversations; Services and keys; Guide; Source types.
The best name matches stand above the groups. Enter opens a Search tab holding
everything found everywhere, filled in as each place answers, and saying for
every place what happened: searched, stopped at a ceiling, too slow, not
searched and why. Looking inside files is asked for, runs as a job in the
footer, and lists files with the line that matched. A found thing opens the way
it opens from its own list; a node can be shown in its catalog.

**Phase 2, names kept.** A connection's owner may let it keep a list of its
names. A large tree, a remote server or a large key space is then found by name
as fast as a local list, the row says how old the list is, and whatever the list
does not cover is still searched live.

**Phase 3, contents kept as words.** An owner may name a folder or a connection
whose contents are kept as words. Words inside those files are found at once,
ranked, with the passage that matched.

**Phase 4, meaning.** Optionally, kept contents also get vectors from a local
model. A search then finds a paraphrase and the other language, merged with the
word hits by rank.

## What changed from the first notes

The notes put the line between the phases at "without an index" and "with an
index". The line that holds up is a different one: **the contract first, the
ways of answering second.** Live and indexed are two ways to answer the same
question about the same place (D203), so the first phase is the contract plus
the live way, and every later phase is one more way behind the same contract.
Concretely:

- **Some things placed in the second pass belong in the first.** Metadata,
  timestamps, permissions, where a result came from and how old it is, partial
  results, timeouts, cost limits and "did not look" versus "found nothing" are
  not index features. They are the contract, and an answer without them is wrong
  the first time a slow server is asked (D198, D199, D200, D201).
- **Some things placed in the first pass do not belong in any.** Routing a query
  by guessing its intent with a model (seconds per keystroke, a cost per
  keystroke, the words sent to a third party) and structured query syntax typed
  into the field. Deterministic rules and controls with a closed meaning do the
  same job and can be tested (D202, D205).
- **"Search the data in connections" is three different promises.** Names —
  relations, keys, folders, files — are cheap to ask live and are phase 1.
  Contents of files are minutes of reading, so live they are an explicit job
  (phase 1) and kept as words later (phase 3). Values in the rows of a database
  are neither: asked live they are a scan of somebody's production server per
  keystroke, and kept they need a person to say which columns mean something.
  They are out of this plan, and finding a value stays the grid's filter or SQL.
- **"Indexing" is two layers, not one.** A kept list of names (phase 2) is cheap,
  copies no contents, works for every source that has a catalog, and is the
  thing that tells a later content pass what changed. A kept copy of contents
  (phase 3) is expensive and is a plaintext copy of somebody's documents. The
  first is needed earlier and for more sources than the second. Embeddings
  (phase 4) are the last layer, not part of the first index.
- **The application's own objects need no index at all.** Connections,
  pipelines, dashboards, keys, guide pages and saved-query titles are rows in
  the application's database or pages in memory; asking them is already the
  cheap path. What is encrypted there is searched by bounded decryption, never
  indexed (D204).
- **Files are not the first thing indexed.** The first kept layer is names, for
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
  `location`, a 200-character `excerpt`, `complete` and `notice`). Routes
  `GET /connectors/{id}/catalog/search` and `/catalog/search-contents`, both at
  `read` through the one access funnel. Only the explorer implements them, so
  the file source **and SSH** search; PostgreSQL and Redis answer 501. The
  catalog's known deviation "Only the file source searches" is stale on SSH.
- **Bounds of that search.** 100 matches by default and 500 at most, 100,000
  entries looked at, 24 levels; contents read up to 8 MB a file and 256 MB a
  search locally, 1 MB and 32 MB over SSH (D152). Breadth first; links listed,
  never walked; not paged.
- **Which sources can search** is read off capability codes, a closed set of
  nine (`search`, `content_search`, …) derived by `issubclass` in
  `capabilities_of`. D13's sentence "today there is one" is stale.
- **Searches over application data** are three, all substring, none indexed:
  the query library (title, and body by decrypting the newest 500), query
  history (executed text, newest 500 of up to 1,000 retained), and the
  superuser's server log. Connections, dashboards, conversations and the type
  catalog are filtered in the browser over lists already loaded; pipelines are
  not filtered at all. The conversation filter sees the first 100 conversations
  only.
- **What is plaintext and what is not.** Connection names and non-secret
  options, pipeline names, dashboard and widget names, saved-query titles,
  service and SSH key names are plaintext. Query bodies and executed text are
  sealed under `QUERY_CONTENT_KEY` (D63); conversation, quick-chat and project
  titles and every message under `AI_CONTENT_KEY` (D141, which also says "no
  transcript search").
- **Who sees what.** Connections: owner or a grant, one predicate
  (`_visible_to` in `backend/app/connectors/crud.py`), no standing answered as
  if the thing did not exist (D33), no superuser bypass (D34), switched-off
  connections readable as rows and never asked (D20). Dashboards: owner plus
  their own grants (D129). Pipelines, saved queries, conversations, services,
  keys, jobs: owner only.
- **Opening a thing from elsewhere.** The agent's `OpenIntent` (connector, node,
  view) is the only server-validated "open this" contract; its client half,
  `openIntent`, is a private function of `WorkspacePage.vue`. Dashboards and AI
  conversations have one-shot module intents; pipelines have none. Reveal in a
  catalog is state a panel takes (`revealInCatalog`).
- **The header** is the kit's `AppLayout`: a `header-start` slot (on the
  workspace: the first-panel toggle and a waiting pair, D167), space, the
  fullscreen toggle and the user menu; 42 px tall, tested at 768 px wide.
  There is no global keyboard shortcut anywhere, no debounce helper, and no
  combobox or grouped list in the kit.
- **Long work** is an owned job (D81): owner required, a closed set of kinds,
  named steps, shown in the footer (D95), interrupted on restart.
- **Infrastructure.** The application database is the official `postgres:18`
  image; `pg_trgm` ships with it and is created by nothing; `pgvector` is not in
  it. There is no embedding model or call anywhere. The backend is one process
  (D124); the metrics collector is the precedent for a second one (D127).
- **The read cache** (D31, D105) is opted into by PostgreSQL only, keyed by
  person and connector, with a closed set of areas (`catalog`, `fetch`,
  `metadata`) and connector-wide invalidation from about thirty call sites.

### What is broken and would be multiplied

A search across everything calls these many times at once, so they are fixed
first (S0).

- **Search words reach the log.** Uvicorn's access line carries the query
  string, D184 routes it into the rotated file, and nothing masks `search=` or
  `query=`. The library, history and catalog searches already write every word
  into a file a superuser reads, against D63's "neither stored nor logged".
- **The content search's byte budget counts bytes it never read.** The size of
  every file it passes is added, including files skipped as too large or
  binary (`backend/app/adapters/explorer/search.py`), so one large file stops a
  search early with a notice that says it was read.
- **A failure in the middle of a walk loses the walk.** An `AdapterError` from
  SSH (a dropped connection, a key whose passphrase is not held) is not an
  `OSError`, so it ends the search with 502 and discards what was found.
- **The library decrypts on the event loop.** Up to 500 bodies of up to 1 MiB,
  per keystroke, in an async handler.
- **A walk in a worker thread cannot be stopped.** Nothing bounds it in time,
  and a caller that stops waiting leaves it running in the shared pool.

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
from stored versions, deletion only by a complete enumeration, words before
meaning, a local model in a container of its own.

The legacy application's indexing, as that design recorded it from the code: a
folder was marked, a watcher ran every 60 seconds and took a file as changed if
its modification time fell in the last minute (so a missed pass lost a change),
chunk ids were `uuid5(user_id:path:chunk_index)` (so a rename re-indexed a file
and an edit near the top shifted every chunk), and the vector store lived inside
the file adapter, which is why it could only ever index files. Kept from it:
marking a place to index, a model in its own container, chunking by structure.

## Terms

| Term | Meaning |
| --- | --- |
| Source type | A driver class and its options, registered in code (D1). |
| Connection | A configured source: address, credentials, grants, switched on or off, its owner's policies. |
| Node | A thing inside a connection, identified by `(connector_id, node_id)` (D21). |
| Application object | A thing the application itself keeps: a connection row, a pipeline, a dashboard, a saved query, a conversation, a service, an SSH key, a guide page, a source type. |
| Capability | What a source type can answer, as an optional protocol (D2). Catalog search is two of them (D76). |
| Provider | What the search asks: one kind of application object, or one connection. Not a source type, not a capability. |
| Place | What a provider covers: an application object type, or a connection. |
| Field (of a place) | What is matched there: names, or contents. |
| Cell | A place and a field. The unit the plan chooses a way for. |
| Way | How a cell is answered: live, or from what is kept (phase 2 on). |
| Hit | One found thing: a pointer to it and why it was found. |
| Outcome | What one provider did with one request. |
| Tier | A set of cost classes asked together in one request. |

"Catalog search" means D76, the search inside one connection's catalog. "The
search" means this one. `app.adapters.search` is the capability and keeps its
name; the engine is `app.search`.

## D197. The search is one engine asking providers, and a source is not a provider

**A provider answers words with hits about one place.** Two families:

- **Application providers**, one per kind of application object. A provider
  lives with its feature — queries, pipelines, dashboards, conversations,
  services — and is handed to the engine when the application is assembled in
  `app/main.py`, the way the job runner is handed its handlers (D81). The engine
  imports no feature. Providers for what sits below the engine — connection
  rows, SSH keys, the guide, the source types — live in the engine package.
- **Connection providers**, one per connection the person can read, built by
  the engine from the connection's `SupportsNodeSearch`. Nothing in the engine
  is written per source type: a type that gains the capability is searched, and
  one without it is skipped with a reason (D201).

**The engine plans, asks, bounds and merges.** It is `app/search/`, placed in
the import layers between `app.terminals` and `app.connectors`: the features
above implement its protocol, and the connections, adapters and guide below are
what it builds providers from. It is added to every SDK-containment contract in
`backend/.importlinter`, which list modules by name and would otherwise let it
import a driver unnoticed.

**One route, one request body:** `POST /api/v1/search`. The words travel in the
body (D200).

**Catalog search is not replaced.** The catalog's own button keeps its route,
and the engine calls the same capability with the same request, so there is one
walk and one result shape. The field scoped to a connection (D205) asks exactly
what the catalog's button asks.

Rejected:

- **A `DataSource` abstraction beside connections.** A second registry of what
  D1 and D2 already describe, and D2a's families again.
- **The browser calling one route per provider.** Simpler, and it would put the
  plan, the budget and the access rule in the browser; the same computation
  would then exist on both sides.

## D198. A hit is a pointer with its evidence, never the thing

**A hit carries:**

- **target**, a union discriminated by kind:
  - `connection` — a connector id;
  - `node` — a connector id and D76's match: the `CatalogNode` from the
    listing's own builder, `parent_id`, `location` in the source's words;
  - `object` — an application object type from a closed set, and its id.

  A row of a table is not a target in this plan. A chunk of a document is never
  one: what matched inside a document is evidence about the document (D203).
- **title** and **detail**, written by the provider: the second line names the
  connection a node is in, the type of a connection, the owner of a dashboard
  shared with the person. A connection the person can no longer see is never
  named, the rule the library already follows for a document's connection.
- **match**: the field that matched (`name`; `details`, such as a connection's
  host; `body`, such as a guide page's text; `contents`, a file's), its class
  (D202), and an excerpt.
- **The excerpt is text cut into segments**, each marked as a hit or not, at
  most 200 characters. No HTML crosses the API (D50) and no offsets either: a
  Python offset counts code points and a JavaScript one UTF-16 units, so offsets
  would mark the wrong letters after an emoji. Segments render with
  interpolation, the hit in `--dp-find`.
- **provenance**: `via` — `live`, the only value in phase 1 — and `as_of`, when
  what answered was read; absent means now.
- **access**: the person's level where the thing has levels (a connection, a
  node, a dashboard), for what the row offers. It decides nothing (D199).
- **open**: an intent from a closed set the workspace already understands —
  for a node the views of `OpenIntent` (catalog, preferred, rows, structure,
  summary), for each application object type one intent of its own.

**Why a pointer and not the thing.** D76's argument at a larger scale: a found
node is a node, so it has its icon, its viewers, its actions and its details
with no second row type. Contents are not copied into an answer; opening reads
the source, and a node gone since says so (D21's 404) instead of opening a
stale copy.

## D199. What may be found is decided before anything is asked

- **Connections are filtered by the one visibility predicate** inside the query
  that lists them: owner or grant. A connection the person has no standing on
  is never asked, never counted and never named. A search is not a way to
  discover connections; a share link is the only one (D61).
- **`read` is the level a search needs.** A connection provider reaches its
  source through the same funnel as every route, with `requires="read"`.
- **A switched-off connection is found by its name and never asked** (D20). Its
  outcome says so.
- **An application provider applies its feature's own rule inside its query**:
  owner only for pipelines, saved queries, conversations, services and keys;
  owner plus dashboard grants for dashboards (D129). The engine passes the
  person; it does not filter afterwards, which would lose results and leak
  counts.
- **No superuser mode** (D34). The server log stays the superuser's own tool
  and is not a provider.
- **Names kept as they were are not searched.** A share's labels, a pipeline
  card's labels and a declared reference's labels are copies taken when they
  were made; a hit on an old name is a wrong answer. They are found through
  what they point at.
- **Each provider says whether the agent may ask it** (S9): the query library
  and history are never offered to the agent (D133), and neither are
  conversations.
- **Encrypted content** follows D204.

## D200. A provider states its cost, and each tier is asked on its own

**Cost classes**, a closed set:

| Class | What it is | Examples |
| --- | --- | --- |
| `instant` | A bounded query of the application database, or a list in memory | connection rows, pipelines, dashboards, services, keys, guide pages, source types, saved-query and conversation titles |
| `cheap` | One bounded request to a connection's metadata | PostgreSQL's catalog; a small Redis database; a local tree walked by name within a time budget |
| `costly` | Many round trips, or a large bounded read | a tree over SSH; a large Redis database; saved-query bodies (D204) |
| `job` | Minutes | the contents of files |

**The class belongs to the provider for this connection, now.** Redis answers
from the key count one `INFO` already gives; the explorer from its storage,
local or remote. `SupportsNodeSearch` gains a method that states it, so the
engine never branches on a source type.

**Three modes:**

- **Typing**, after 150 ms without a key and at least two characters: `instant`
  providers, and `cheap` connection providers for the connections in the
  person's context only — the connections whose panels are open in the
  workspace, which the browser sends as a hint, current one first, at most
  eight. One deadline of 400 ms for the whole answer; what is late is dropped
  from the popup and counted in one quiet line.
- **Search**, on Enter or in the Search tab: two requests. The first asks
  `instant` and `cheap` everywhere the person can read, with a deadline of 2
  seconds. The second asks `costly`, each provider with its own 10 seconds.
  The first's groups are drawn as they arrive; the second fills its own groups
  and never reorders what is already on screen.
- **Contents**: a job (S6), never on a keystroke and never implied by Enter.

**Bounds**, each a setting with a default and a ceiling:

- at most 4 connection providers asked at once per request, and one search in
  flight per person and connection; a newer request cancels the older one,
  in the browser (an abort) and on the server (the task);
- a time budget travels into the capability: `NodeSearchRequest` gains one, and
  a walk checks it between entries and stops with `complete: false` and a
  notice, rather than being left running in a worker thread nobody waits for;
- 5 rows a group while typing, 50 a provider in the Search tab, D76's ceilings
  below both;
- identical requests in flight share one task; an answer is kept for the
  source's catalog window in a new cache area `search` (D31, D105), which a
  connection's owner may shorten like the others and which is invalidated with
  the connector. Only a source that opted into caching is cached;
- at least 2 and at most 200 characters (D76's ceiling), at most 8 words.

**The words are neither stored nor logged.** They travel in a POST body, the
engine never writes them, and a test types a marker word and asserts it appears
in no log line (S0 makes the same true of the existing searches).

## D201. An answer says what every provider did

**An outcome per provider**, a closed set:

- `complete` — it looked everywhere it was asked to;
- `stopped` — it hit a ceiling, with the source's own notice (D76);
- `late` — the deadline passed;
- `failed` — a kind and a safe sentence; driver text never (D2c);
- `skipped`, with a reason from a closed set: switched off, cannot search,
  too costly for this mode (with the gesture that would search it), not in
  context while typing, a key whose passphrase is not held (D147);
- `pending` — belongs to the second request and is not answered yet.

**One provider's failure never fails the answer.** A 501, a `NodeNotFound`, an
`AdapterError` and a timeout each become that provider's outcome.

**"Nothing found" is said only when every provider asked was complete.**
Otherwise the answer says where it did not look, as D76 separates "nothing
else matched" from "I stopped looking".

**Not paged.** The first N of each provider and a notice. "More in this
connection" asks that provider again with its full limit; there is no cursor
across providers, because there is no order across them to page through.

## D202. Groups in a fixed order, and one rule for how well a name matched

**Groups, in this order:** Connections; In connections, one subgroup per
connection with the connections in context first; Saved queries; Pipelines;
Dashboards; Conversations; Services and keys; Guide; Source types. A group with
nothing in it is not drawn.

**The engine decides how well a name matched, once, for every group.** Words
are split on white space, every word must occur in the name, case-insensitively
(case-folded), in any order. Nothing is compiled: a `*` is a character (D2c,
D76). The classes, best first:

1. `exact` — the name is the words;
2. `prefix` — the name begins with them;
3. `word` — every word begins a word of the name, where `_`, `-`, `.`, `/`,
   `:` and white space separate words;
4. `substring` — every word occurs somewhere;
5. `text` — found in a body or in contents, not in the name.

A provider only narrows — a SQL `strpos` on the longest word, a walk's
substring test — and returns candidates with the name it matched; the engine
classes them. One function, so `orders` ranks the same in every group.

**Inside a group:** class, then the provider's own order (a tree's breadth
first, nearest first), then the name.

**Best matches:** up to three `exact` or `prefix` hits from any group, above
the groups, by class, then by how recently the person opened them from the
field (S5), then by group order. They are not repeated below.

**No score is compared across providers, because there are none.** A
connection matched by name and a paragraph near by cosine distance are not on
one scale, and a list merged from them would be ordered by accident. When
kept contents arrive, words and meaning are fused by rank inside their own
group (phase 4); the groups keep this order.

Rejected:

- **One list merged by a numeric relevance.**
- **A language model reading the intent of each query.** Seconds of delay, a
  cost per keystroke, and the words sent to a third party (D135).

## D203. Live and kept answer the same cell, and what is kept is never a provider

**A plan is a set of cells**, a place and a field: Connections × names; the
`orders` connection × names; a folder of personal storage × contents. Each cell
gets a way: live, kept, or none with a reason.

**Phase 1: every cell is live or none.** The plan already has the shape so the
contract does not change later.

**From phase 2, what is kept claims a cell** when it covers that place and
field and is within its freshness window. Otherwise the cell stays live where
live is possible: keeping something never makes a thing unfindable that live
would have found. A hit from what is kept says `via: kept` and its `as_of`, and
the row wears D105's mark that it may be stale.

**What is kept is one store asked once** for every cell it claims. It is not a
group and not a provider among providers: a file found by name both live and in
the kept list would otherwise appear twice, and the plan would ask live what
the store had already answered.

**A chunk is evidence, never a target.** Hits from chunks fold into their node;
the best chunk becomes the excerpt and, later, the place a viewer opens at.

**The request, the hit and the outcome do not change when a cell changes
way.** This is the property every later phase is held to.

## D204. Encrypted application content is searched by bounded decryption, never kept

- **Saved-query titles are plaintext** and matched in SQL, `instant`.
- **Saved-query bodies are matched only in the Search tab**, through the
  library's own bounded decryption — the newest 500, D63's rule — in a worker
  thread (S0 moves it off the event loop), as a `costly` provider. Never while
  typing: a keystroke would decrypt up to 500 MiB.
- **Query history is not a provider.** A run is a record of what was executed,
  found in its own place (D63); in this field it would repeat the same SQL a
  hundred times.
- **Conversation, quick-chat and project titles are matched by decrypting the
  newest 500 of each** in a worker thread, `instant`: they are short. Their
  messages are not searched; D141 stands.
- **Nothing encrypted is kept by any phase.** A searchable copy of ciphertext is
  a plaintext copy (D63).

## D205. One field in the workspace header, and hits open through the workspace's own intents

**Where.** `AppLayout` gains a `header-center` slot; the kit imports no
feature. The workspace page fills it. The field grows to 480 px, and below
900 px wide collapses to a search button that opens it over the header.
Preferences and Admin have no field: there is nowhere there to open a hit into.

**Ctrl+K and ⌘K focus it from anywhere in the workspace, editors included.**
The browser's own Ctrl+K (a web search) is prevented. It is the application's
first global shortcut, so it comes with the registry `WorkspaceScene` already
reserves a list for. Escape closes the popup and returns focus where it was,
and is not passed on to the window-level Escape listeners.

**The popup** is a new kit component: a combobox and a grouped list with ARIA
roles, arrows and Enter, a group heading, two lines a row, the excerpt in
segments. Built on `AppPopup`, so it stands above windows; shown on `/ui-kit`.

**A scope chip.** Opened while a catalog panel has focus, the field offers
"In ‹connection›" as a chip: Tab takes it, Backspace drops it. With it the plan
asks that connection only, from the level the catalog stands on — exactly the
catalog's own search.

**Enter opens the Search tab**, a workspace panel in Data that can be detached
(D93): the whole answer, filters by group and by connection, every outcome, and
"Search inside files", which starts S6's job behind D76's confirmation and the
same remembered answer.

**Opening.** A hit's `open` intent goes to one client registry that maps each
intent to an action that exists. For that, S2 lifts `openIntent` out of
`WorkspacePage.vue` into `WorkspaceActions`, so the agent and the search turn
`(connector, node, view)` into a panel in one place; makes the dashboard and
conversation intents work when their space is already alive (today one is read
once at setup and the other is not watched immediately); and gives pipelines an
intent. A guide page opens the guide window; a source type opens New connection
on it; a service opens its tool at the foot of the screen.

**Show in catalog** is `revealInCatalog`, D112's gesture.

**Recent searches**: the last ten, per person and per server in the browser
(D99), remembered on Enter or when a hit is opened and never while typing — the
catalog filter's rule. An empty field shows them, and, after S5, what was last
opened from the field.

## What is kept, by phase: direction, not yet decisions

Each of these becomes a decision when its slice is designed in detail. They are
written now so that phase 1 builds nothing in their way.

### Phase 2 — names, kept

- **An owner's choice per connection**, off by default: "Keep a list of names
  for search", in the connection window, changed only by the owner, the way the
  transfer flag is (D135). A grantee sees the state.
- **Any source with a catalog.** A pass enumerates by walking `list_children`
  within D76's ceilings, or by a cheaper way the source offers: one catalog
  query for PostgreSQL, a `SCAN` for Redis, the explorer's walk.
- **A row per node**: connector, node id, parent, name, kind, location, a
  version token where the source has one (modification time and size for a
  file; PostgreSQL and Redis have none and are compared as sets of names), and
  the pass that last saw it.
- **Deleted only by a complete enumeration.** A pass that hit a ceiling or could
  not read a folder removes nothing under what it could not see; otherwise one
  dropped SSH connection would empty the list.
- **Matched with trigrams** (`pg_trgm`, created by a migration; a concurrent
  index build cannot run inside Alembic's transaction or the application's
  process, the trap LangGraph's `setup()` already taught).
- **Scheduled by a timer in the lifespan**, like the query history sweep and
  the pipeline scheduler, not as jobs: a periodic idempotent pass as a job
  would fill every footer and the job table. "Refresh now" runs the same pass
  as an owned job, so a person who asked sees it.
- **A freshness window per connection**, chosen by the owner like D105's;
  beyond it the cell goes back to live.
- **What DataPlayer writes itself marks the list stale at once.** The thirty
  invalidation sites call one hook handed in at assembly; writers import
  nothing of the index. Changes made elsewhere are seen at the next pass.
- **A plaintext copy of names, and it says so.** D101 encrypts cached values
  because catalog names can be sensitive; a list searchable by the database
  cannot be encrypted. That is the copy the owner agreed to. Switching it off or
  deleting the connection deletes it in the same transaction.
- **Built with the owner's credentials**, as a grantee's live read already is
  (D33). A connection that cannot be opened without a person present — an SSH
  key whose passphrase is held only in memory (D147) — cannot be listed in the
  background and says so.

### Phase 3 — contents, kept as words

- **An owner names a scope**: a connection and a node, with what it covers
  (formats, the largest file). The legacy "mark this folder", for any source
  that has contents.
- **Fed by phase 2's passes**: only what changed is read. Three layers against
  repeated work: an unchanged version is not read, an unchanged content hash is
  not extracted, a chunk whose text is already known is not recomputed.
- **Text is extracted by format, once.** The same extractor serves live
  contents search and the kept index, or the two would disagree about one file.
  Extractors live in the explorer by the import contract; PDF and Office are new
  ones, added when asked.
- **Chunks follow structure** with a locator (a page, a range of lines); words
  are a `tsvector` with the `simple` configuration, because the data is Russian
  and English and a stemmer per language is its own decision.
- **The access filter is inside the query**, before ranking: the connection is
  readable by the person now and switched on.
- **The passes run in a process of their own**, built like the metrics
  collector (D127): reading and extracting is heavy, and the backend is one
  process with one loop (D124). It cannot announce on the socket, so the
  backend reads its state from rows; it needs its own log name; and it carries
  D127's trap of not starting with `docker compose up -d db backend`.

### Phase 4 — meaning

- **A local embedding model in a container of its own**, behind an embedder
  protocol (model, dimensions, token ceiling, the query and passage forms,
  whether it sends data out). Vectors keyed by a chunk's text hash and the
  model; a new model is built beside the old one and switched to when complete.
- **Where vectors live is decided in that slice, by measurement**: `pgvector` in
  the application database means changing its image in `compose.yml` and both
  CI files; a store of its own follows the metrics store (D126).
- **Words and vectors are fused by rank inside the kept group.** Live places
  are never searched by meaning.
- **An external embedding provider** only for chunks of connections whose owner
  allows transfer (D135), with the person's own key (D140); not built until
  asked.

### Rows of database tables

Not planned. A table is found by its name and its columns (S7); a value in its
rows is found with the grid's filter or with SQL. Keeping rows would need a
person to name a key, the text columns and a change column for each table; it is
designed when somebody asks for it.

## Rejected

- **The field never asking a connection's server**, the withdrawn D188. Names in
  a connection are cheap to ask, and tiers, deadlines and the context limit
  bound what a keystroke costs. Waiting for an owner to build an index before a
  table can be found by name is the system built around the index that the
  user's notes argue against.
- **Indexing every connection by default.** A stale second copy of everything,
  a wider leak, hours of work nobody asked for.
- **Contents searched as one types.** D76 made it a gesture with a stated price.
- **A typed prefix language** (`in:`, `type:`). The scope chip and the tab's
  filters say the same with closed controls. A prefix may come later and must
  parse into the same closed filter.
- **History, transcripts and the server log as providers** — D204, D199.

## Slices

Each slice is built with its tests and verified with the checks ENGINEERING.md
names for the sides it touches. Each is useful on its own. Phase 1 is S0–S9;
phases 2–4 are listed to fix the order and are designed in their own specs.

### S0 — corrections the search would multiply

- Access lines lose their query string, as the request context already does
  (D184).
- The contents search counts the bytes it read, not the sizes it passed.
- An `AdapterError` in the middle of a walk ends it with what was found,
  `complete: false` and the reduced sentence.
- The library decrypts in a worker thread.
- Stale documentation: SSH searches (D76's deviation), nine capability codes
  (D13), the history search window is the newest 500 of up to 1,000 runs (D63).

Acceptance: a marker word sent to each existing search route appears in no log
line; a search over a tree holding one 40 MB file and a matching small file
finds the small file over SSH; a walk whose storage fails halfway returns the
earlier matches; the library's search runs off the loop.

### S1 — the engine, three providers and the field

The engine with D197–D203's models, the plan, the deadlines, the outcomes and
the match classes; `POST /api/v1/search`. Providers: connection rows (name, the
source type's title, host and database from the non-secret options), guide
pages (title, headings, body, in memory), source types (the fields the type
catalog matches today). The type catalog window then asks this provider rather
than keeping its own copy of the rule. The header slot, the field, the popup kit
component, Ctrl+K, debounce and abort, recent searches, and the open intents for
these three.

Acceptance: a connection is found by part of its name, its type and its host,
and opens its catalog; a connection the person has no grant on is found by
nobody; a superuser finds nothing more; a switched-off connection is found and
says it is off; a guide page is found by a word in its body and opens at its
page; Ctrl+K focuses the field from inside the SQL editor; Escape gives focus
back; the header holds the field at 1280 and 768 pixels in every theme.

### S2 — every application object

Pipelines, dashboards (owned and granted), saved queries (titles while typing,
bodies in the Search tab, D204), conversations, quick chats and projects by
title (D204), services, SSH keys. `openIntent` lifted into `WorkspaceActions`;
dashboard and conversation intents that work when their space is alive; a
pipeline intent.

Acceptance: each type is found and opens where it lives; somebody else's
pipeline, conversation or key is found by nobody; a dashboard shared with the
person is found and names its owner; a saved query is found by a word in its
body only after Enter; a conversation is found by its title and never by its
messages; opening a dashboard from the field works with the Dashboards space
already shown once.

### S3 — names inside connections, live

Connection providers built from `SupportsNodeSearch`; its cost method and time
budget; cancellation into the walk; the `search` cache area; the context hint;
outcomes per connection; Show in catalog.

- **PostgreSQL gains `SupportsNodeSearch`**: schemas and relations whose names
  hold the words, in one bounded query of `pg_class` and `pg_namespace` with
  `strpos` on a bound value (so `%` and `_` are characters), `LIMIT n + 1` for
  `complete`, under the inspection statement timeout, nodes built by the
  listing's builder with one relation context per schema. `cheap`.
- **Redis gains `SupportsNodeSearch` and `SupportsNodePath`**: a `SCAN` bounded
  by keys looked at and by time, not by matches (today's ceiling counts matches,
  so a rare word walks the whole database); names case-folded and matched in
  the process, since `MATCH` is case-sensitive and compiling `[aA]` classes from
  typed text would be compiling; empty databases skipped by `INFO`. `cheap` up
  to a key count, `costly` above it. The path is computed from the key's name,
  so a found key can be shown in the tree.
- **The explorer** states `cheap` for local storage and `costly` over SSH.

Measured on the way: the time each source takes for a name search on the
development data, recorded under Validation and used to set the deadlines and
the Redis threshold.

Acceptance: `class` typed with a PostgreSQL connection open finds `pg_class`
(a test against a catalog that always holds hundreds of rows, not an empty
schema); `100%` finds nothing rather than everything; a key found in a Redis
database of a thousand keys is shown in its tree; a Redis database above the
threshold is searched on Enter and not while typing; a server that does not
answer is `late` and the other groups are drawn; a newer keystroke cancels the
older walk.

### S4 — the Search tab

Two requests per D200, groups drawn as they arrive, filters by group and by
connection, outcomes with their gestures, "more in this connection", the scope
chip.

Acceptance: an SSH connection's hits appear after the others without moving
them; every connection skipped is listed with its reason; "Nothing found" never
appears while a provider is late or stopped.

### S5 — what was opened recently

A row each time a hit is opened from the field — the person, the target, when —
at most 100 per person, owner only; a target that is gone falls out when it is
next opened. An empty field lists them; recency orders the best matches.

Acceptance: what was opened comes back first; somebody else's list is never
read; a deleted connection's nodes leave the list.

### S6 — inside files, as a job

A job kind `search.contents` over the connections chosen in the tab that have
`content_search`; D76's confirmation and remembered answer; D76's and D152's
bounds per connection and one total; one at a time per person; Stop. The
matches are kept in the backend's memory for 30 minutes and are not written to
the job's row: they are excerpts of people's files, and the job table is
plaintext.

Acceptance: a word inside a local file and inside a file over SSH is found;
the job is in Working and then Recent; Stop ends it with what was found; after
a restart the job is interrupted and its matches are gone.

### S7 — names inside relations

PostgreSQL columns and comments, matched in the Search tab (`costly`): a hit is
its relation, with the column or comment as the excerpt. No column node kind.

Acceptance: `email` finds the tables that have such a column and says which
column; a table comment is found by a word in it.

### S8 — places the browser holds

Open tabs, windows and tab groups (D94), which only the browser knows. They are
matched in the browser by the engine's rule. That rule then exists twice, on
purpose, because the server cannot see these places; one table of cases (words,
name, class) is read by both test suites so the two cannot drift, and the
duplication says why in a comment.

Acceptance: an open tab is found and activated; the shared table of cases fails
both suites when one side changes.

### S9 — the agent

A `search` tool over the providers that allow the agent (D199), bounded like
D134's tools, with D135 checked per connection; "Ask the agent" as the popup's
last row puts the words into a new conversation's composer, unsent.

Acceptance: the agent finds a table by name across connections; a connection
that does not allow transfer is named in a refusal and nothing of it reaches
the model; no saved query is ever in its results.

### Later phases

- **S10 — names kept** (phase 2), its own spec.
- **S11 — contents kept as words** (phase 3), its own spec.
- **S12 — meaning** (phase 4), its own spec.

## Testing

- **Pure:** the match classes (one table of cases, also read by S8's browser
  suite); the planner (cells, modes, context, skips); outcomes; excerpt
  segments, emoji included.
- **Backend:** each provider with an owner, a grantee, a person with no
  standing and a superuser; a switched-off connection never contacted; a source
  without the capability skipped with its reason; deadlines and cancellation
  with a source that never answers; the marker word absent from every log line;
  PostgreSQL against the system catalog; Redis and SSH behind the service
  registry, skipped without their servers.
- **Browser:** debounce and abort, the intent registry, segments rendered as
  text; Playwright for Ctrl+K, typing, Enter, a hit opened in each space, Show in
  catalog, and the header at two widths.

## Open questions for the user

1. While typing, the field asks only the connections open in the workspace,
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

Nothing is built. Each slice records here the checks it ran and their results,
and S3 records its timings.
