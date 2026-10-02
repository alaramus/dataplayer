# Search

One search over everything a person may see: their connections and what is
inside them, and the things the application keeps. Read this before adding a
provider, changing what a hit carries, or touching the field in the header.

Decisions here: D197, D198, D199, D200, D201, D202, D203, D204, D205.

```
backend/app/
├── adapters/search.py     the word rule and its classes, SearchBounds,
│                          the catalog search's models (D76)
└── search/
    ├── models.py          the request, places and cells, hits, outcomes, lines
    ├── plan.py            which cells an answer asks, and why not the others
    ├── providers.py       the provider protocol, Asked, Found, match helpers
    ├── engine.py          lanes, deadlines, coalescing, the stream
    ├── excerpts.py        text cut into segments, the words marked
    ├── connections.py     the visible connections, and the rows provider
    ├── guide.py           guide pages
    ├── source_types.py    source types and the services that start them
    └── routes.py          POST /search
```

```
POST /api/v1/search        the words in the body; JSON Lines back
```

## D197. The search is one engine asking providers, and a source is not a provider

- **A provider answers words with hits for its cells.** Application providers
  are one per kind of application object. A feature's provider lives with the
  feature and is handed to the engine in `app/main.py`, the way the job runner
  gets its handlers (D81); the engine imports no feature. Providers for what
  sits below the engine — connection rows, SSH keys, the guide, source types —
  live in `app/search/`. The service templates a source type is also found by
  are handed in by `app.services`.
- **Connection providers** are built by the engine, one per connection the
  person can read, from the connection's `SupportsNodeSearch`. Nothing in the
  engine is written per source type.
- **The engine plans, asks, bounds and merges.** `app.search` sits between
  `app.transfers` and `app.jobs` in the import layers, and is listed in every
  SDK-containment contract and in `redis-cache-is-not-coordination`.
- **One route**, `POST /api/v1/search`.
- **Catalog search is not replaced.** The catalog's button keeps its route;
  both ask the same capability under the same word rule (D202).
- `NodeView`, the views a node opens in, is in `app.adapters.catalog`; the
  agent's `OpenIntent` and the search's hits both use it.

Rejected: a `DataSource` abstraction beside connections (D1 and D2 already
describe sources). The browser calling one route per provider: it would put the
plan, the budget and the access rule in the browser.

Known deviations:

- **Connections are found as rows, not searched inside** (S4).
- **Only connection rows, the guide and source types are providers** (S5 adds
  the rest).

Spec: [Universal search](../decisions/2026-10-02-universal-search-design.md)

## D198. A hit is a light pointer with its evidence, never the thing

A `Hit` carries:

- **`target`**, discriminated by kind: `connection` (an id); `node` (connector,
  node id, `parent_id`, `location`, name, kind, an always-empty `sub_key`, the
  optional `ancestors` and the optional `CatalogNode` live fills); `object` (a
  closed `ObjectType` and its id). A chunk of a document is never a target.
- **`key`**, one string per target, so a thing found twice in one answer is one
  hit. The engine keeps the first; the better class arrives first in this phase.
- **`title`** and **`detail`**: the second line names the source type of a
  connection, that it is switched off, and its owner when it is not the
  person's.
- **`facts`**: the kind, when the thing last changed, its owner, whether it is
  switched off — what the Search tab filters by.
- **`match`**: the field (`name`, `details`, `body`, `contents`, `columns`), its
  class (D202), an optional line, and the excerpt.
- **The excerpt is segments**, each marked as a hit or not, at most 200
  characters. No HTML and no offsets cross the API (D50): a Python offset
  counts code points and a JavaScript one UTF-16 units. Folding can change a
  string's length (`ß` → `ss`), so positions are mapped back one character at
  a time.
- **`access`**, the person's level where the thing has one. It decides nothing.
- **`open`**, from a closed set: a `NodeView`, `connection` (its window), or an
  object type.

A node found later from what is kept may lack its `CatalogNode` and still be
the same hit. Contents are never copied into an answer.

Spec: [Universal search](../decisions/2026-10-02-universal-search-design.md)

## D199. What may be found is decided before anything is asked

- **Connections are filtered by the one visibility predicate** inside the query
  that lists them (`crud.visible_with_standing`, owner or grant, bounded to
  1,000). A connection without standing is never asked, counted or named.
- **Ids from the browser are intersected with that set.** A context hint naming
  one without standing is dropped silently; a place in `only` naming one answers
  404 exactly as an unknown id does, before the stream begins. A route that
  streams cannot change its status after the first line, so the refusal is a
  dependency of the route, not its body.
- **`read` is enough.** A grantee's search runs under the owner's credentials,
  as every grantee's read does (D33).
- **A switched-off connection is found by name and never asked** (D20).
- **An application provider applies its feature's rule in its own query**; the
  engine passes the person and never filters afterwards.
- **No superuser mode** (D34). The server log is not a provider.
- **Names kept as copies are not searched**: a share's labels, a pipeline
  card's, a declared reference's.
- **The agent asks nothing by default**: a provider is offered to it by a
  decision of its own (S10).

Spec: [Universal search](../decisions/2026-10-02-universal-search-design.md)

## D200. A cell states its cost, and a mode spends only what it may

| Cost | What | Examples |
| --- | --- | --- |
| `instant` | a bounded query of the application database, or memory | connection rows, the guide, source types |
| `cheap` | one bounded request to a connection's metadata | PostgreSQL names, a small Redis database, a local tree |
| `costly` | many round trips or a large bounded read | a tree over SSH, a large Redis database, saved-query bodies |
| `job` | minutes | the contents of files |

- **The cost belongs to the cell** and is stated without asking anybody, so a
  dead server cannot hold the plan.
- **Typing** (150 ms after the last key, two characters at least): `instant`
  cells everywhere, `cheap` cells of the connections in context only — the
  connections whose panels are open, current first, at most eight. One deadline,
  `SEARCH_TYPING_SECONDS` (0.4).
- **Search** (Enter, the Search tab): `instant`, `cheap` and `costly`, in one
  streamed answer. Cheap cells have `SEARCH_CHEAP_SECONDS` (2), costly ones
  `SEARCH_COSTLY_SECONDS` (10) each and `SEARCH_TOTAL_SECONDS` (20) in all. At
  most `SEARCH_MAX_CONNECTIONS` (20) connections are asked, in context first;
  the rest are `not asked`.
- **A job** is never planned; contents are looked inside on request.
- **One answer in flight per person and lane.** A newer one cancels the older's
  tasks. The lanes are the field, the Search tab, a gesture in the tab and the
  type catalog, so typing in the field never ends a search the tab is running.
- **Identical cells asked by one person share one task**, cancelled when the
  last answer waiting for it goes. Nothing is shared between people.
- **Application cells share one session and run one after another**: they are
  instant. A cell of its own cost runs in a task and a session of its own.
- **Worker-thread work runs under one limiter** (`SEARCH_THREADS`, 4).
  `SearchBounds` — a deadline, a stop check, the limiter — is an argument of its
  own, never a field of a request model.
- **Rows**: 5 a group while typing, 50 a cell in Search, D76's 500 for a cell
  asked alone. **Words**: 2 to 200 characters, at most 8 words.
- **Nothing is cached.** A typed query rarely repeats, and a cache would have to
  refuse answers cut by time.
- **The words are neither stored nor logged.** They travel in a POST body, a
  failed provider is logged as private (D184), and a test types a marker word
  and finds it in no log line.

Spec: [Universal search](../decisions/2026-10-02-universal-search-design.md)

## D201. An answer is a stream of cells, and says what happened to each

- **JSON Lines over the POST**: a `plan` line listing every cell with its group,
  cost and way; one `cell` line per cell as it finishes, with its outcome and
  hits; one `best` line; one `end` line. FastAPI streams a generator route as
  `application/jsonl` and states the item type in OpenAPI, so the client's line
  types are generated.
- **An outcome per cell**: `way`, `as_of`, and `status` — `complete`, `stopped`
  (a ceiling, with the source's notice), `late` (with the deadline it was given),
  `failed` (a kind and a safe sentence; `locked` stays its own kind, and
  `owned` says whether the person may unlock it), or `skipped` with a reason:
  switched off, cannot search, unreachable (with `since`), too costly for this
  mode, not in context while typing, not asked. `more` says whether asking the
  cell alone would find more.
- **One cell's failure never fails the answer.** An unexpected exception is
  logged privately with a ref, and the sentence carries it.
- **"Nothing found"** is `end.nothing_found`: true only when every cell asked
  was `complete`. `end.asked` counts them.
- **Not paged.** The first N of each cell and its `more`; "More in this
  connection" asks that cell alone.
- **Groups have fixed places.** The plan line names every group before anything
  is found, so a screen reserves a group's place and a late cell fills it
  without reordering what is drawn.

Spec: [Universal search](../decisions/2026-10-02-universal-search-design.md)

## D202. Groups in a fixed order, and one rule for how well a name matched

- **Groups, in order:** Connections; one group per connection, in context
  first; Favorites; Pipelines; Dashboards; Conversations; Services; SSH keys;
  Guide; Source types. Open tabs first from S9. `Group.rank` carries the order.
- **One word rule**, in `app.adapters.search`: words split on white space,
  case-folded; every word must occur in the name, in any order; nothing is
  compiled, a `*` or `%` is a character.
- **Classes, best first:** `exact` (the name is the words), `prefix` (it begins
  with the first word), `word` (every word begins a word of the name, `_ - . / :`
  and white space separating), `substring`, `text` (found in a detail, a body or
  contents, not the name), `meaning` (reserved).
- **One table of cases**, `tests/utils/word_cases.py`, is read by the tests of
  every implementation.
- **Inside a group:** class, then the provider's own rank, then the name.
- **Best matches:** up to three `exact` or `prefix` hits from the instant and
  cheap cells, by class, then recency, then group; sent once, when those cells
  are in. The field draws them above the groups and not again below.
- **No score is compared across places**, and no model reads the intent of a
  query.

Spec: [Universal search](../decisions/2026-10-02-universal-search-design.md)

## D203. Live and kept answer the same cell, and what is kept is never a provider

- **A plan is a set of cells**, each answered `live`, `kept` or `none`. In this
  phase every cell is live or none; the plan and the outcome already carry the
  way, so a later phase that keeps names changes no request, hit or outcome.
- **What is kept will be one store asked once** for every cell it claims, its
  hits folded into their place's group; a chunk is evidence, never a target.

Spec: [Universal search](../decisions/2026-10-02-universal-search-design.md)

## D204. Encrypted application content is searched by bounded decryption, never kept

- Saved-query titles are plaintext and matched in SQL, `instant`. Bodies are
  matched only in Search mode, through the library's bounded decryption — the
  newest 500 — on a worker thread under the search's limiter, a `costly` cell.
- Query history is not a provider.
- Conversation, quick-chat and project titles are matched by decrypting the
  newest 500 of each on a worker thread, `instant`. Messages are not searched
  (D141).
- Nothing encrypted is kept by any phase.

Known deviation:

- **Not built yet** (S5).

Spec: [Universal search](../decisions/2026-10-02-universal-search-design.md)

## D205. One search, opened from the header or by Ctrl+K, and hits open through the workspace's own intents

- **Where:** a `header-center` slot in `AppLayout`, holding a compact button on
  the workspace; Mod+K (Ctrl+K, ⌘K on a Mac) opens the same search over
  everything, at the top of the window. Not in a terminal (D148), not while a
  dialog is open.
- **The popup** is a kit combobox over a grouped list; Enter opens the Search
  tab, a `navigate` panel holding the whole answer.
- **Opening** goes through one client registry of intents; `openIntent` moves
  into `WorkspaceActions` so the agent and the search open a node in one place.
- **Show in catalog** is `revealInCatalog`, with a busy catalog duplicated
  rather than wiped.
- **What the browser keeps:** the last ten searches in session storage, never
  words that found a saved query's body, cleared on sign-out.

Known deviation:

- **Not built yet** (S2, S3).

Spec: [Universal search](../decisions/2026-10-02-universal-search-design.md)
