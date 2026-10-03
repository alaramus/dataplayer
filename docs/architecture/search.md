# Search

One search over everything a person may see: their connections and what is
inside them, and the things the application keeps. Read this before adding a
provider, changing what a hit carries, or touching the field in the header.

Decisions here: D197, D198, D199, D200, D201, D202, D203, D204, D205.

```
backend/app/
├── adapters/search.py     the word rule and its classes, SearchBounds, the
│                          capability's models (D76), StatesSearchCost,
│                          SearchesColumns
├── adapters/postgres/search.py, adapters/redis/search.py, explorer/search.py
└── search/
    ├── models.py          the request, places and cells, hits, outcomes, lines
    ├── plan.py            which cells an answer asks, and why not the others
    ├── providers.py       the provider protocol, Asked, Found, match helpers
    ├── engine.py          lanes, deadlines, coalescing, the stream
    ├── nodes.py           connection cells: candidates, asking, backoff
    ├── contents.py        inside files, as a job: its memory and handler (S7)
    ├── excerpts.py        text cut into segments, the words marked
    ├── connections.py     the visible connections, and the rows provider
    ├── recent.py          an empty search: what was opened lately
    ├── open_tabs.py       tabs and tab groups the browser sends
    ├── guide.py, source_types.py, ssh_keys.py
    └── routes.py          POST /search
features: pipelines/, metrics/, queries/, ai/, services/ — search.py each

frontend/src/
├── shared/keys/shortcuts.ts      the shortcut registry (Mod+K)
├── shared/ui/AppCombobox.vue     the kit combobox; AppOption draws its rows
└── features/search/              stream reader, answer reducer, outcome
                                  sentences, intents, the field and the tab,
                                  SearchContents.vue (inside files, S7)
```

```
POST /api/v1/search                  the words in the body; JSON Lines back
POST /api/v1/search/contents         inside files: starts a job (S7)
GET  /api/v1/search/contents/{job}   what it found, while it is held
```

## D197. The search is one engine asking providers, and a source is not a provider

- **A provider answers words with hits for its cells.** Application providers
  are one per kind of application object. A feature's provider lives with the
  feature and is handed to the engine in `app/main.py`, the way the job runner
  gets its handlers (D81); the engine imports no feature. Connection rows, SSH
  keys, the guide and source types live in `app/search/`. The service
  templates a source type is also found by are handed in by `app.services`.
- **Connection providers** are built per answer, one per visible connection,
  from the connection's `SupportsNodeSearch` and, for a `columns` cell, its
  `SearchesColumns`. Nothing in the engine is written per source type.
- **The engine plans, asks, bounds and merges.** `app.search` sits between
  `app.transfers` and `app.jobs` in the import layers, and is listed in every
  SDK-containment contract and in `redis-cache-is-not-coordination`.
- **Catalog search is not replaced.** The catalog's button keeps its route;
  both ask the same capability under the same word rule (D76, D202).
- `NodeView` is in `app.adapters.catalog`; the agent's `OpenIntent` and the
  search's hits both use it.

Rejected: a `DataSource` abstraction beside connections (D1 and D2 already
describe sources). The browser calling one route per provider: the plan, the
budget and the access rule would live in the browser.

Spec: [Universal search](../decisions/2026-10-02-universal-search-design.md)

## D198. A hit is a light pointer with its evidence, never the thing

A `Hit` carries:

- **`target`**, discriminated: `connection`; `node` (connector, node id,
  `parent_id`, `location`, name, kind, an always-empty `sub_key`, `ancestors`
  for a source without a node path, and the `CatalogNode` live fills);
  `object` (a closed `ObjectType` and its id). A chunk is never a target.
- **`key`**, one per target, so a thing found twice in one answer is one hit.
  The engine keeps the first; in this phase the better class arrives first.
- **`title`** and **`detail`**: a node's detail names its connection and
  location; a connection's names its type, that it is switched off, and its
  owner when it is not the person's; a shared dashboard names its owner. A
  quick chat is titled as its history shows it.
- **`facts`**: kind, when it last changed, owner, switched off.
- **`match`**: the field (`name`, `details`, `body`, `contents`, `columns`), its
  class (D202), an optional line, and the excerpt as segments of at most 200
  characters, each marked as a hit or not. No HTML and no offsets cross the API
  (D50); folding can change a string's length (`ß` → `ss`), so positions are
  mapped back one character at a time.
- **`access`**, the person's level where the thing has one. It decides nothing.
- **`open`**, from a closed set: a `NodeView`, `connection` (its window), or an
  object type.

Spec: [Universal search](../decisions/2026-10-02-universal-search-design.md)

## D199. What may be found is decided before anything is asked

- **Connections are filtered by the one visibility predicate** inside the query
  that lists them (`crud.visible_with_standing`, owner or grant, bounded to
  1,000; it also loads the encrypted secrets, decrypted only for a connection
  that is asked). Nothing without standing is asked, counted or named.
- **Ids from the browser are intersected with that set.** A context hint
  naming one without standing is dropped; a place in `only` naming one answers
  404 exactly as an unknown id does, from a dependency of the route, before the
  stream begins.
- **A grantee's search runs under the owner's credentials** (D33). A grantee's
  `locked` failure reads "Locked by its owner", never the source's sentence,
  which names the owner's key.
- **A switched-off connection is found by name and never asked** (D20).
- **Each application provider applies its feature's rule in its own query**:
  owner only for pipelines, saved queries, conversations, services and keys;
  owner plus grants for dashboards (D129). No superuser mode (D34).
- **An empty search names a recent target only if the person still may**: a
  connection still visible, a node only while its connection is visible and on,
  an object only through the provider that owns its type (`Recalls`).
- **Names kept as copies are not searched**: a share's labels, a pipeline
  card's, a declared reference's. A service is found by its connection's name
  as it is now.
- **The agent asks nothing by default**: a provider is offered to it by a
  decision of its own (S10).

Known deviation:

- **A recently opened node is named from the browser's copy** of its name and
  kind: reading it again from its source would make an empty search no longer
  instant. A node renamed since keeps its old name there; opening a dropped one
  answers D21's 404.

Spec: [Universal search](../decisions/2026-10-02-universal-search-design.md)

## D200. A cell states its cost, and a mode spends only what it may

| Cost | What | Examples |
| --- | --- | --- |
| `instant` | a bounded query of the application database, or memory | connection rows, the guide, source types, titles of pipelines, dashboards, saved queries, chats, services, keys |
| `cheap` | one bounded request to a connection's metadata | PostgreSQL names, local file names, Redis with a known small key count |
| `costly` | many round trips or a large bounded read | names over SSH, a large or unmeasured Redis, PostgreSQL columns, saved-query bodies |
| `job` | minutes | the contents of files |

- **The cost belongs to the cell**, stated without asking anybody. A source
  type states its own through `StatesSearchCost` from the field and what the
  engine remembers of its last search; without it a cell is costly. Redis is
  costly until a search has measured the key count (every database `INFO`
  lists), then cheap while it is at most `SEARCH_CHEAP_KEYS` (20,000).
- **Typing** (150 ms after the last key, two characters at least): `instant`
  cells everywhere, `cheap` cells of the connections in context only (open
  catalogs, current first, at most eight). One deadline, `SEARCH_TYPING_SECONDS`
  (0.4).
- **Search** (Enter, the Search tab): `instant`, `cheap` and `costly`. Cheap
  cells have `SEARCH_CHEAP_SECONDS` (2), costly ones `SEARCH_COSTLY_SECONDS`
  (10) each from when they are asked and `SEARCH_TOTAL_SECONDS` (20) in all. At
  most `SEARCH_MAX_CONNECTIONS` (20) connections are asked — in context, then
  recently opened, then by name — the rest `not asked`.
- **`insist`** asks the places named in `only` whatever their health, backoff
  or the ceiling say. It never overrides the mode: typing still skips costly
  cells.
- **One answer in flight per person and lane.** A newer one cancels the
  older's tasks. The lanes are the field, the Search tab, a gesture in the tab
  and the type catalog, so typing never ends a search the tab is running.
- **Identical cells in flight share one task** when asked in the same mode
  with a deadline at most 0.25 s later than the running task's, and nobody has
  asked it to stop; a later answer gets a task of its own rather than inherit
  less time. The task's own stop check reaches its worker thread, and it is
  cancelled when its last waiter goes. Nothing is shared between people.
- **Connections**: `SEARCH_PARALLEL_CONNECTIONS` (4) asked at once per answer,
  one connection's cells one after another, and one search at a time per
  person and connection across lanes. A connection already pooled is searched
  through its pool, borrowed and never closed; any other through a connection
  of its own (D127's way), so a fan-out never pushes another person's pool out.
  PostgreSQL runs under a statement timeout of the time left. A source's own
  deadline is a little before the cell's, so a walk stopped by time hands over
  what it found.
- **Dead servers are not asked again and again.** A connection the person's
  health monitor (D19) last could not reach — network or timeout; a refused
  password or a locked key is an answer — is `unreachable` with `since`. One
  that missed (network or timeout, or late on Enter with at least half its
  time) is backed off per person in memory, doubling like D19's; a miss during
  an answer leaves that connection's later cells in it unasked.
- **Worker threads**: `SEARCH_THREADS` (4) under one limiter. Costly work hands
  its token back between 50 ms slices; the limiter is first in first out, so
  instant cells run between two slices of a saved-query body walk.
- **Rows**: 5 a group while typing, 50 a cell in Search, 500 for a cell asked
  alone. **Words**: 2 to 200 characters, at most 8. Text the browser sends (a
  tab's title, a recent node's name) is cut, not refused.
- **Nothing is cached, and the words are neither stored nor logged.** They
  travel in a POST body; a failed provider is logged as private (D184).
- **Contents are a job (S7)**, `search.contents`, never a cell: started from
  the Search tab over the connections of the answer whose type has
  `SearchesContents` (the plan marks them `contents`), ticked by the person,
  behind D76's warning and its remembered answer. One at a time per person
  (`admit_within`, 409); the connections one after another, each under D76's
  and D152's own bounds and at most 100 matches, all of them under
  `SEARCH_CONTENTS_SECONDS` (600) and 500 matches, on the search's own thread
  limiter. Each connection is resolved again when the job runs, with the
  owner's credentials and a borrowing store. Stop sets the walk's stop check
  and keeps what it found.
- **Its words, places and matches live in process memory**, keyed by job id,
  for `SEARCH_CONTENTS_HELD_SECONDS` (1,800) after it ends (D124), and never in
  the row: `parameters` carries counts and how long they are held, the step
  and message never quote the words, and an unexpected failure is logged as
  private. `GET /search/contents/{job}` answers 404 unless the caller owns the
  job, drops what came from a connection the caller can no longer read or
  that is switched off, and says `held: false` once they are gone — expired,
  or a restart, which ends the job `interrupted` (D81). A person's finished
  searches are pruned to the newest 20 when a new one starts.

Spec: [Universal search](../decisions/2026-10-02-universal-search-design.md)

## D201. An answer is a stream of cells, and says what happened to each

- **JSON Lines over the POST**: a `plan` line listing every cell with its group,
  cost and way; one `cell` line per cell as it finishes; one `best` line; one
  `end` line. FastAPI streams a generator route as `application/jsonl` and states
  the item type in OpenAPI, so the client's line types are generated.
- **An outcome per cell**: `way`, `as_of`, and `status` — `complete`, `stopped`
  (a ceiling, with the source's notice), `late` (with its deadline), `failed` (a
  kind and a safe sentence; `locked` stays its own kind and `owned` says who may
  unlock it), or `skipped`: switched off, cannot search, unreachable (with
  `since`), too costly for this mode, not in context while typing, not asked.
  `more` says whether asking the cell alone would find more.
- **One cell's failure never fails the answer.** An unexpected exception is
  logged privately with a ref, and the sentence carries it.
- **"Nothing found"** only when `end.nothing_found`: every cell asked was
  complete. **Not paged**: "More in this connection" asks the cell alone.
- **Groups have fixed places.** The plan line names every group first, so a
  screen keeps a pending group's place and a late cell fills it.

Spec: [Universal search](../decisions/2026-10-02-universal-search-design.md)

## D202. Groups in a fixed order, and one rule for how well a name matched

- **Groups:** Open tabs; Connections; one group per connection, in context
  first; Favorites; Pipelines; Dashboards; Conversations; Services; SSH keys;
  Guide; Source types. `Group.rank` carries the order.
- **One word rule**, in `app.adapters.search`: words split on white space,
  case-folded; every word occurs in the name, in any order; nothing is
  compiled. Catalog search uses it too (D76).
- **Classes, best first:** `exact`, `prefix` (begins with the first word),
  `word` (every word begins a word; `_ - . / :` and white space separate),
  `substring`, `text` (a detail, a body, contents or columns), `meaning`
  (reserved). A source that meets more matches than its limit keeps the
  best-classed ones and says it stopped.
- **One table of cases**, `tests/utils/word_cases.py`, is read by the tests of
  the application providers, the explorer, PostgreSQL and Redis.
- **Inside a group:** class, the provider's own rank, the name. **Best
  matches:** up to three `exact` or `prefix` hits from instant and cheap cells,
  by class, recency, group; the field draws them first and not again below.
- **No score is compared across places**, and no model reads a query's intent.

Known deviations:

- **PostgreSQL folds in SQL**, as `lower(x::text COLLATE "default")`, each word
  bound as the rule folds it and as typed. `lower()` does not fold `ß` to `ss`,
  so `strasse` does not find `straße`; under a C or POSIX default collation a
  non-ASCII letter is found only in the case typed; a word start is recognised
  after a plain space only. The engine re-classes every hit by the rule.
- **Saved-query titles are classed in the process**, the owner's newest 1,000
  titled documents read in one query, the cell `stopped` when there are more —
  not matched in SQL as D204 first said, for the same folding reason.

Spec: [Universal search](../decisions/2026-10-02-universal-search-design.md)

## D203. Live and kept answer the same cell, and what is kept is never a provider

- **A plan is a set of cells**, each answered `live`, `kept` or `none`. In this
  phase every cell is live or none; the plan and the outcome already carry the
  way, so a later phase that keeps names changes no request, hit or outcome.
- **What is kept will be one store asked once** for every cell it claims, its
  hits folded into their place's group; a chunk is evidence, never a target.

Spec: [Universal search](../decisions/2026-10-02-universal-search-design.md)

## D204. Encrypted application content is searched by bounded decryption, never kept

- Saved-query titles are plaintext, an instant cell (see D202's deviation).
- Bodies are matched only in Search mode, through the library's own bound — the
  newest `QUERY_SEARCH_MAX_DOCUMENTS` — decrypted in 50 ms slices on a worker
  thread under the search's limiter, one walk per person at a time, checking
  for a stop between documents, a costly cell. A hit keeps the title, the line
  and one excerpt, never the body.
- Query history is not a provider.
- Conversation, quick-chat and project titles: the newest 500 of each
  decrypted on a worker thread, instant. Messages are not searched (D141).
- Nothing encrypted is kept by any phase. Words that found a body are not kept
  among the browser's recent searches.

Spec: [Universal search](../decisions/2026-10-02-universal-search-design.md)

## D205. One search, opened from the header or by Ctrl+K, and hits open through the workspace's own intents

- **Where.** `AppLayout` has a `header-center` slot; only the workspace fills
  it, with a button drawn as a field with its keys, collapsing to an icon below
  160 px of measured room so a waiting pair (D167, its title cut) never covers
  it. The search opens at the top of the window on `--dp-layer-search`, above
  floating windows and the activity sheet, below Quasar's menus where its list
  opens.
- **Mod+K** (Ctrl+K; ⌘K on a Mac, where Ctrl+K stays CodeMirror's kill-line)
  through `shared/keys/shortcuts.ts`, the application's shortcut registry: one
  capture-phase listener, matched by key or by code so any layout works, never
  inside an element marked `data-owns-keys` (a terminal, D148) or while an
  `[aria-modal="true"]` is open. The empty scene lists registered shortcuts.
- **`AppCombobox`**, on `AppPopup` with `no-focus`, `no-refocus`,
  `no-parent-event`, `fit`: focus stays in the input, `aria-activedescendant`,
  no row active until an arrow, Enter opens the active row or the Search tab,
  "Show all results" last, a polite status line, the first Escape closes the
  list and keeps the words, the next returns focus.
- **A scope**: opened while a catalog has focus, the first row offers "Search
  in ‹connection›" from the level the catalog stands on (a tree's grouping);
  the right arrow takes it, Backspace removes it.
- **The Search tab**, panel kind `search`, role `navigate`, stores nothing but
  its id, so a restored layout or tab group (D94) brings it back empty. It holds
  the whole answer in the plan's order, filters by group, connection, kind and
  time changed, and draws every outcome with its gesture on lane `follow`.
  Enter while another space is shown opens it in a window over that space.
  "Search inside files" (S7) offers the answer's connections that can be
  read inside, none ticked; its matches are rows like any node hit, a line
  with its number, read every second until the job ends. Its progress is the
  footer's (D95); its entry in Recent offers "Show results" while they are
  held, then says "Its matches are no longer held" with "Search again" — with
  the words while this browser tab still holds them in memory
  (`shared/search/contentsWords.ts`, emptied on sign-out).
- **Opening** goes through one registry typed over every `OpenIntent`
  (`features/search/intents.ts`), and `WorkspaceActions.openIntent` serves the
  agent and the search alike: floated over a covered space, a connection
  outside the browser's first page read from the server. A space is told which
  object it is asked for before it is shown, so a dashboard, a pipeline, a
  conversation or a project opens whether or not its space was shown before.
- **Show in catalog** (D112) on every node hit: a catalog holding a search, a
  filter or ticks is not moved, another catalog of the connection shows the
  node; one on that level behind search results leaves them first. A Redis key
  is opened down the hit's `ancestors`.
- **What the browser keeps**: the last ten searches in session storage, per
  server, never words that found a saved query's body, emptied on sign-out;
  and the last 50 targets opened from the field or the tab (S6), the target
  only, in local storage per person and server (`shared/search/opened.ts`),
  sent as `recent` with every request and emptied on sign-out. An empty field
  shows the recent searches, then what the server still names of those
  targets.
- **What the browser tells**: every request, the empty field's included, sends
  as `browser` each open tab and window — the title on its tab, its connection
  or else its kind as the detail, the Search tab and the Connections column
  left out — then each saved tab group by name, at most 200
  (`features/search/browser.ts`). A tab opens by its panel id, a group after
  D94's warning.

Known deviations:

- **The agent has no search tool** (S10).
- **A conversation outside the first 100 of the AI list** is replaced by the
  newest once the list loads.

Spec: [Universal search](../decisions/2026-10-02-universal-search-design.md)
