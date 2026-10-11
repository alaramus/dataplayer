# Search: names, text and meaning kept

A connection's names kept in the application database, so the search finds a
large tree, a remote server or a large key space by name without asking it;
the text of the files below chosen folders, found on Enter; and, when a local
model runs, vectors of both, so Enter finds by meaning as well.
The search itself — the engine, cells, outcomes, the field and the tab — is in
[search.md](search.md). Read this before changing what a pass reads, the
`search-keeper` process, the kept cell, or what marks a list stale.

Decisions here: D212, D213, D214, D215, D216, D217, D218, D219, D220, D221, D222.

```
backend/app/
├── adapters/search.py         KeptName, NameBatch
├── adapters/protocol.py       EnumeratesNames, ExtractsText
├── adapters/explorer/text.py  what counts as text, for live and kept alike
├── adapters/postgres/search.py, adapters/redis/search.py,
│   adapters/explorer/search.py   enumerate_names, each source's own walk
├── connectors/names.py        NamesChanged, handed in at assembly (D216)
└── search/
    ├── keep.py                search_keep, search_name, the API models
    ├── kept.py                state, the owner's switch, the kept queries, stale
    ├── kept_text.py           the text pass after the names, and its passages
    ├── kept_meaning.py        name passages, vectors, pruning
    └── embedder.py            Embedder, LocalEmbedder (TEI)
    ├── keeper.py              python -m app.search.keeper: the passes
    └── keep_routes.py         /search/kept

frontend/src/features/searchIndex/
├── state.ts                   what a list is said to be, when Keep names is offered
├── api.ts                     vue-query, polled while a pass is near
├── searchIndexWindow.ts       which connection's window is open
├── SearchIndexDialog.vue      the window: the switch, the window, Read now
├── SearchIndexTool.vue        the tool at the foot
└── SearchIndexCommand.vue     its block on the rails
```

```
GET  /api/v1/search/kept                          every kept list the person can see
GET  /api/v1/search/kept/{connector_id}           one connection's, kept or not
PUT  /api/v1/search/kept/{connector_id}           the owner's switch and window
POST /api/v1/search/kept/{connector_id}/refresh   read it now
POST   /api/v1/search/kept/{connector_id}/contents   keep a folder's text
DELETE /api/v1/search/kept/{connector_id}/contents   stop, ?node_id=
```

## D212. A connection's names are kept by its owner's choice, made from the catalog

- **Search index…** is a line of the catalog's Actions menu about the
  connection, beside Backups, offered on every connection; on a type without
  `EnumeratesNames` it is disabled with the reason. One window, drawn once by
  the workspace and opened from wherever a list is mentioned.
- **Only the owner changes it** (D135's rule): 403 for a grantee, who opens the
  same window read-only and sees the state. 404 for anybody without standing.
- **Off by default.** Off, or the connection deleted, deletes the names in the
  same transaction.
- **The window says what it costs**: a plaintext copy of the names, read with
  the owner's credentials; contents are never copied.
- **Freshness**: 1 hour, 6 hours, 1 day (default) or 1 week.
- **Seen from two more places**: the Search index tool at the foot, opened by
  a block on the tool rails, and a line on the connection window's Options
  page.
- **Offered where it is needed**: a names cell of the person's own connection,
  asked live and `stopped` or `late`, offers "Keep names".

Rejected: a mark after the name in the Connections list. Tried and taken out;
that list stays an icon, a name and a state dot.

Spec: [Search, phase 2: names kept](../decisions/2026-10-11-search-names-kept.md)

## D213. A pass reads names through the source's own enumerator

- **`EnumeratesNames.enumerate_names(limit, bounds)`** yields `NameBatch`es.
  PostgreSQL: one catalog query of schemas and relations, no sizes. Redis:
  `SCAN` of every database, each batch described in one round trip. Explorer:
  breadth first, links not followed, `MAX_DEPTH` deep, stepped a batch at a
  time on a worker thread — never `list_children`, which refuses 2,000 entries.
- **A kept name is the live hit's pointer** — node, parent, location,
  ancestors, the matched name — plus its `scope`: the folder it was listed in,
  the Redis database, or the whole PostgreSQL connection.
- **A finished pass deletes what it did not see**, except under a scope the
  source reported `unread` (equal, or below it by `/`). A pass with a `notice`
  — `SEARCH_KEPT_MAX_NAMES` (200,000) or `SEARCH_KEPT_PASS_SECONDS` (900) —
  writes what it saw and deletes nothing, `partial`. A failed pass keeps the
  list and its time and says why.
- **The owner's credentials, no pool** (D127's way). A key whose passphrase
  only the backend holds (D147) fails the pass `locked`, said in words.

Spec: [Search, phase 2: names kept](../decisions/2026-10-11-search-names-kept.md)

## D214. Passes run in one worker process, and the backend reads their state from rows

- **`search-keeper`**, `python -m app.search.keeper`: the backend's image, the
  user storage mounted, its own `search-keeper.log` read by the Logs panel.
  Not started by `docker compose up -d db backend`.
- **A tick every 5 seconds** takes what is due — never read, stale, asked to
  refresh, or past half its window — at most two passes at once. A failed pass
  is tried again after the smaller of half its window and ten minutes. A pass
  left running by a stop is ended `failed` when the process starts.
- **State is `search_keep`**: window, `stale_at`, `refresh_asked_at`, the last
  pass's start, end, outcome, notice and kind, and `kept_at` /
  `kept_started_at` / `kept_notice` of the pass that last wrote the list.
- **Not a job and not on the socket**: the screens poll, every 2 seconds while
  a pass is near and every 30 otherwise.

Spec: [Search, phase 2: names kept](../decisions/2026-10-11-search-names-kept.md)

## D215. A kept list answers the names cell, and what it cannot answer stays live

- **Usable**: written, not stale (`stale_at` before `kept_started_at`),
  younger than its window, the connection switched on, the cell not scoped to
  a level, and one word of three characters or more. Then the cell is `kept`
  and `instant` — asked while typing for every connection, outside the
  connection ceiling, never held back by health or backoff.
- **One query of `search_name`**, the standing and `enabled` inside it (D199):
  every word as a `LIKE` on a bound, escaped value over the trigram index;
  exact, then prefix, then shortest name first, rows plus one. The engine
  classes the hits again by the rule.
- **Said as such**: the outcome's `way` is `kept` and its `as_of` and every
  hit's are `kept_at`; the hit's `via` is `kept`. A partial list answers
  `stopped` with its notice.
- **Folded once, in the process**, by `casefold`: `strasse` finds `straße`.

Known deviations:

- **A scoped search stays live**: a subtree of a kept list is a different query
  per source type.
- **A switched-off connection keeps its list** until it is switched on again or
  the list is switched off; nothing asks it meanwhile (D20).

Spec: [Search, phase 2: names kept](../decisions/2026-10-11-search-names-kept.md)

## D216. What renames in DataPlayer marks the list stale at once

- **`NamesChanged`** (`app.connectors.names`) is handed in at assembly as
  `app.search.kept.names_changed`, which sets `stale_at`. A stale list is not
  asked; the worker reads it on its next tick.
- **Callers**: an action whose result creates, replaces or reloads nodes, or
  that failed after a reviewed plan; a table created from rows; a SQL commit
  or auto-commit run with a schema effect; a transfer's arrival. Not a row edit.

Known deviation:

- **A pipeline's paste** does not mark a list stale; the next pass sees it.

Spec: [Search, phase 2: names kept](../decisions/2026-10-11-search-names-kept.md)

## D217. A folder's text is kept by its owner's choice, in the same window

- **"What files hold"** in the Search index window, on a type with
  `EnumeratesNames` and `ExtractsText`: the kept folders with their counts and
  Stop, and "Keep what files hold in" the folder the catalog stood in, or the
  whole connection (`node_id` empty).
- **Through the names**: 409 until they are kept, 422 for a node whose kept name
  is not a folder, 501 for a type without the capabilities, 403 for a grantee.
  The names switched off take every folder and its text with them.
- **Stop** deletes the text no other kept folder covers.

Spec: [Search, phase 3: what files hold, kept](../decisions/2026-10-11-search-contents-kept.md)

## D218. Text is read after the names, only where it changed, by the live rule

- **After every names pass that did not fail**, from the kept file names below
  the folders: same `version` (time and size), not opened; same `digest`,
  chunks untouched; not text by the rule, kept as such and not opened again.
- **One rule with the live search**, `explorer/text.py`: no folder or link, at
  most the storage's `file_bytes`, no zero byte in the first 4 KB, UTF-8 with
  replacement.
- **Chunks** of 40 lines or 8,000 characters with their first line's number,
  `casefold`ed once, trigram-indexed.
- **Bounds**: the pass's clock and `SEARCH_KEPT_CONTENTS_BYTES` (512 MB); the
  rest waits for the next pass. Only a finished pass deletes, and only text no
  kept name holds or no folder covers. A folder keeps when it was read, its
  files, what was left out and why it stopped.
- **An edit in place** through the editor marks the list stale (D216).

Spec: [Search, phase 3: what files hold, kept](../decisions/2026-10-11-search-contents-kept.md)

## D219. Kept text answers a contents cell on Enter, by the live rule

- **On Enter** for a connection whose list is usable (D215) and has a folder
  read once: a `contents` cell, `kept`, `instant`, in the connection's group;
  the job still searches the rest. Never while typing.
- **One query of `search_chunk`**, standing and `enabled` inside it, every word
  in the folded chunk, four chunks per row asked. A file counts only when one of
  its lines holds every word — the live rule — and that line is the hit's line
  and excerpt.
- **Said as kept**: `way`, `as_of` and `via`, as D215.

Spec: [Search, phase 3: what files hold, kept](../decisions/2026-10-11-search-contents-kept.md)

## D220. One local model, behind a protocol, started on request

- **`Embedder`**: `info()` (model name, token ceiling, nothing when none
  answers), `queries()` and `passages()` with their own prefixes
  (`EMBEDDINGS_QUERY_PREFIX`, `EMBEDDINGS_PASSAGE_PREFIX`), `sends_out`.
  `LocalEmbedder` speaks Text Embeddings Inference; `/info` is believed 30 s
  either way, the last 128 queries are remembered.
- **The `embedder` service** under the compose profile `meaning`, model
  `EMBEDDINGS_MODEL` (`intfloat/multilingual-e5-small`), downloaded on first
  start into its volume; optional `HF_TOKEN` is passed to it alone.
  `EMBEDDINGS_URL` points the backend and the keeper at it; empty is off.
- **A model that sends text out is not used.** An external provider is a second
  implementation that must first check D135 per connection and use the owner's
  key (D140); the words a person types never leave the server.

Spec: [Search, phase 4: meaning](../decisions/2026-10-11-search-meaning.md)

## D221. Passages are embedded once per text and model, in the database

- **`search_passage`**: a kept name as "name (location)", or a run of a kept
  file's non-empty lines of at most 1,000 characters with its first line's
  number; written and deleted with the names and the chunks.
- **`search_vector`** keyed by the text's digest and the model, `vector` with no
  dimension, in the application database (pgvector,
  `pgvector/pgvector:0.8.1-pg18-trixie`). No index: a search compares one
  connection's passages exactly.
- **The keeper** embeds after each pass's text, and every minute reads what a
  model started later has not; it prunes vectors no passage holds, and another
  model's once this one's are whole.
- **The window** shows passages and how many the model has read.

Spec: [Search, phase 4: meaning](../decisions/2026-10-11-search-meaning.md)

## D222. Meaning adds to a kept cell what the words missed, said as such

- **On Enter**, in a kept names cell and a kept contents cell: nearest passages
  of that kind, standing and `enabled` inside the query, at least
  `EMBEDDINGS_MIN_SIMILARITY` (0.8) near, one per node, at most five.
- **After the words**, class `meaning`, never repeating a node they found,
  within the cell's rows. A row says "By meaning" and nothing in it is marked.
- **Nothing** without a model, and nothing while typing.

Known deviation:

- **A hit by meaning opens at its passage's first line**: the model ranks runs
  of lines, not lines.

Spec: [Search, phase 4: meaning](../decisions/2026-10-11-search-meaning.md)
