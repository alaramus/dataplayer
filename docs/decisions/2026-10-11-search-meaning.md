# Search, phase 4: meaning

Date: 2026-10-11. Decisions: D220 through D222. Their architecture home is
[search-kept.md](../architecture/search-kept.md), beside phases 2 and 3. Slice
S13 of [Universal search](2026-10-02-universal-search-design.md), whose "Phase
4" section gave the direction.

Status: agreed on 2026-10-11 after a discussion of the model, its runtime, the
store and what is embedded; built on the branch `search-index`.

## Outcome

`docker compose --profile meaning up -d embedder` starts a local model. From
then on everything a connection keeps — its names, and the text below the
folders its owner chose — gets vectors, and Enter finds "пользователи" as the
table `user` and "счета март" as a line about "invoices for march", each row
saying "By meaning" after what the words found. Without the service nothing
changes. The Search index window says how much the model has read.

## Decided in the discussion

- **The model**: `intfloat/multilingual-e5-small` — Russian and English, 384
  dimensions, about half a gigabyte, fast on a processor. It can be replaced;
  vectors are kept per model.
- **The runtime**: Hugging Face Text Embeddings Inference, its CPU image, in a
  container of its own under a compose profile, not started by default. The
  model is downloaded from Hugging Face on the first start. **`HF_TOKEN`**,
  optional, is handed to that container only: an anonymous download can be
  made to wait in a queue for minutes, a token's is not.
- **The store**: pgvector in the application database, so the standing, the
  switched-on connection and the nearness are one query, as for the words.
  The database image becomes `pgvector/pgvector:0.8.1-pg18-trixie` in compose
  and CI — trixie, because the bookworm build's older glibc collates text
  differently from the `postgres:18` the volumes were made with.
- **What is embedded**: names as well as text, so "клиенты" finds `customers`
  in a database, not only in files.
- **When**: Enter only, as kept text.
- **External providers later**: not built. The protocol says whether a model
  sends text out; one that does is refused until the owner's transfer flag
  (D135) and their key (D140) decide which passages may go, and the words a
  person types never go.

## D220. One local model, behind a protocol, started on request

- **`Embedder`** (`app/search/embedder.py`): `info()` — the model's name and
  its token ceiling, nothing when none answers; `queries()` and `passages()`,
  each with its own prefix (`EMBEDDINGS_QUERY_PREFIX`, `…_PASSAGE_PREFIX`,
  e5's `query: ` and `passage: `); `sends_out`. `LocalEmbedder` speaks TEI's
  `/info` and `/embed`, believes `/info` for 30 seconds either way, and
  remembers the last 128 queries.
- **`EMBEDDINGS_URL`** switches it on; compose points it at the `embedder`
  service, so starting the profile is all it takes. Empty is off.
- **A model that sends text out is not used.** Writing one means checking
  D135 per connection before its passages are sent and the owner's key (D140)
  — a second implementation, nothing else changes.

Spec: [Search, phase 4: meaning](2026-10-11-search-meaning.md)

## D221. Passages are embedded once per text and model, in the database

- **`search_passage`**: a kept name — "name (location)" — or a run of a kept
  file's non-empty lines of at most 1,000 characters, inside the model's 512
  tokens, with its first line's number. Written with the chunks (D218) and
  with the names, deleted with them.
- **`search_vector`**, keyed by the passage text's digest and the model: the
  same text in two files or two connections is embedded once, and a file read
  again unchanged costs nothing. The column is `vector` without a dimension,
  so every model's vectors live in one table; there is no index yet — a
  search compares one connection's passages exactly, measured at 150 ms for a
  whole answer.
- **The keeper embeds** after the text of each pass (D218), and every minute
  looks for lists the model has not read all of — kept before it started — and
  reads them. It prunes vectors no passage holds, and another model's once
  this one's are whole: a new model is built beside the old.
- **The window** says how many passages there are and how many the model has
  read, or that no model runs.

Spec: [Search, phase 4: meaning](2026-10-11-search-meaning.md)

## D222. Meaning adds to a kept cell what the words missed, said as such

- **On Enter**, in a kept names cell (D215) and a kept contents cell (D219):
  the query is embedded, the nearest passages of that kind found with the
  standing and `enabled` inside the query, at least `EMBEDDINGS_MIN_SIMILARITY`
  (0.8) near, one per node, at most five.
- **After the words**: class `meaning` orders last (D202); a node the words
  already found is not repeated; the cell's row ceiling holds.
- **A row says "By meaning"**, then where the name is or the run of lines,
  opened at its first line; nothing in it is marked, since no word matched.
- **Nothing when no model answers**, and nothing while typing.

Known deviation:

- **A hit by meaning opens at its passage's first line**, not the line that
  made it near: the model ranks runs of lines, not lines.

Spec: [Search, phase 4: meaning](2026-10-11-search-meaning.md)

## Rejected

- **Ollama**: fewer multilingual embedding models; TEI needs no code of ours.
- **A store of its own**: the access filter would be a second query.
- **A switch per folder**: the service running is the switch.
- **Meaning while typing**: the field's rows are names.

## Validation

- **Backend.** `pytest tests/search/test_kept_meaning.py`: 14 passed, with a
  stand-in model that knows eight words in two languages — "клиенты" finds
  `customers.csv`, "счета март" a line about invoices in a kept folder, the
  words first and meaning adding what they missed, nothing while typing,
  nothing without a model or from one that sends text out, the state's
  counts, a text embedded once across connections, a list kept before the
  model read by it later, an old model's vectors pruned only once the new one's
  are whole, passages following renamed names, the local embedder's prefixes
  and remembered queries and its silence when down. Two went red with the
  fusion taken out. `pytest tests/search`: 170 passed, 2 skipped. `ruff`,
  `mypy`, `lint-imports`: clean.
- **Real model.** `multilingual-e5-small` downloaded in about 45 seconds
  without a token. "как выдать доступ пользователю" against "grant permissions
  to a user" 0.858, against an unrelated passage 0.748. The 279 names of the
  development database embedded within seconds; whole answers in about 150 ms.
  "пользователи" → `user` first; "расписание запусков" → `schedulenote`,
  `pipelineschedule`; "ключи доступа" → `providerkey` … `sshkey`; "панели
  мониторинга" missed `dashboard` — the small model on short English names.
- **Browser.** `vitest` for the rows and the window's line, `type-check`,
  `lint`: clean. The Search tab shows `user` with "By meaning · pg-warehouse ·
  public".
