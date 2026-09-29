# Search and the index

The search field in the header, the providers that answer it, and the index
that lets any source be searched by its words and by meaning. Read this before
adding something the field should find, before making a source indexable, and
before touching what the index stores. Searching one catalog live is D76, in
[sources/catalog.md](sources/catalog.md#d76-a-search-is-a-read-of-the-catalog-and-the-words-are-the-filters).

Decisions here: D188, D189, D190, D191, D192, D193, D194.

## What exists today

Nothing below is built. The decisions are the design the slices follow, in
this order: the field with application objects and the guide; scopes and the
content index of explorer storages by words; the embedding service and the
hybrid merge; names scopes for PostgreSQL. A slice that lands records here what
it built and what it did differently.

Terms:

- **Source** — a connection and its adapter (D1, D2). There is no separate
  `DataSource`.
- **Scope** — what a connection's owner asked to be indexed.
- **Item** — a node, later a row, as the index knows it.
- **Chunk** — a piece of an item's text, with a locator.
- **Pass** — one run over a scope.
- **Provider** — anything that answers what is typed in the field.

The package is `backend/app/search/`. In the layer order it stands below the
features (`ai`, `queries`, `pipelines`, `metrics`, `transfers`) and above
`jobs`, `connectors`, `adapters` and `guide`.

## D188. The search field asks providers, and never a connection's server

- A source and a provider are different things. Connections, pipelines,
  dashboards, saved queries, chats and guide pages are found in the
  application's database. The index is one provider. A person's Qdrant or
  Elasticsearch added as a connection is a source and has nothing to do with
  the index.
- One field in the header, focused by Ctrl+K. What is typed goes to every
  provider at once, each with its own time budget. A group appears when its
  provider answers.
- **Groups, never one ranking.** Scores of different providers are not on one
  scale. The provider orders inside a group. A fixed rule orders the groups:
  - an identifier, `schema.table`, a path, a UUID, an email or a number raises
    the providers that match exactly;
  - several words or a question raises content and offers Ask AI;
  - the connection of the panel being looked at raises its own results;
  - `in:<connection>`, `type:<kind>` and `>` for commands narrow explicitly.
- No language model reads the intent. It would add seconds and a cost per
  keystroke, and send the typed words to a third party (D135).
- **The field never sends a request to a connection's server.** Names inside a
  connection are found only through a names scope (D189). Searching one
  connection live stays D76, inside its catalog.
- First providers: commands and places, connections, pipelines, dashboards,
  saved queries, chats, guide pages, the index.
- A provider for a feature lives in that feature and is handed to the search at
  assembly, as the job runner is handed its handlers (D81). The search imports
  no feature above it. Providers for connections and the guide, which are below
  it, live in the search package.
- A result is a pointer. It opens through the workspace's existing intents. An
  index result is a `CatalogNode` with `location` and an excerpt, D76's shape.
- Ask AI sends the typed words to the agent as a new message. The agent gains a
  `search` tool over the same providers, as the person (D133), with results of
  a connection that does not allow transfer withheld (D135).
- Typed words reach the full-text functions as a parameter. Prefixes are parsed
  into a closed filter (D2c).

Spec: [Search across the application, and an index of any source](../decisions/2026-09-29-search-and-index-design.md)

## D189. Nothing is indexed until a connection's owner names a scope

- **Nothing by default**, not even names.
- A scope: connection and root node; depth (subtree or level); `names` or
  `names_and_content`; vectors or not (content only); filters (formats, largest
  file); schedule; on or off.
- Names are what a catalog lists: file and folder names and paths; schemas,
  relations, columns and comments. Content is the text a format reader reads.
- **Only the owner** makes, changes, pauses or removes a scope. It is a policy
  of the connection, like the transfer flag (D135). A grantee sees the scopes
  read-only.
- **The index belongs to the connection.** Everybody who can read the
  connection ([D33](backend.md)) finds what it holds. The scope's form states
  how many people that is, because a search finds in one query what a person
  may never have opened.
- A scope is made from Index… in the catalog's menu on a node, and managed on
  the Index page of the connection's window: state, last pass, size, errors,
  pause, remove.
- A switched-off connection ([D20](sources/contract.md)) returns nothing and its
  scopes do not run. Deleting a connection deletes its index in the same
  transaction. Removing a scope deletes what that scope alone brought in.
- Coverage is said. The content group names the indexed connections and the
  age of each index; with nothing indexed it says so and how to begin.

Known deviations:

- **A grantee finds what the owner indexed, including what they never
  opened.** Accepted: it is what the connection already lets them read.

Spec: [Search across the application, and an index of any source](../decisions/2026-09-29-search-and-index-design.md)

## D190. A source feeds the index through capabilities and knows nothing about it

- Adapters do not import the index. It asks them through protocols:
  - **enumerate** a scope: key, version token, name, kind, `location` (D21),
    type, the times the source states — no content. Any source with a catalog
    can do it by a bounded `list_children` walk; a source may answer cheaper;
  - **version token**: what the source changes when the item changes —
    modification time and size, ETag, commit, `updated_at`. Without one, a
    content hash, which costs a read;
  - **read**: the content capability the source already has;
  - **change feed**: optional, later.
- **Text is extracted by format, not by source**, with the readers of
  [content.md](sources/content.md) (D47, D51, D53). An extractor returns a
  normalised document: title, sections of text with locators (page, line
  range), typed metadata, the source's times.
- Chunks follow structure (headings, paragraphs, JSON and SQL blocks), with a
  ceiling per chunk and per document.
- An item is `(connection_id, node_id, sub_key)`. `sub_key` stays empty until
  rows are indexed and will then hold a row's key.
- The first implementer is the explorer's storage
  ([D150](sources/explorer.md)): personal storage and SSH, and any later
  storage without code of its own. PostgreSQL implements enumeration for names
  scopes.

Known deviations:

- **Rows of tables are not indexed.** A table is found by name, through a names
  scope. Rows need a mapping the person gives: key, text columns, title, change
  column.
- **No change feeds.** Every pass enumerates.

Spec: [Search across the application, and an index of any source](../decisions/2026-09-29-search-and-index-design.md)

## D191. What changed is known from stored versions, never from a clock

- Each item keeps its version token, content hash and the last pass that saw
  it. A pass reads only what differs. A missed pass loses nothing.
- **Deleted is decided only by a complete enumeration.** A pass that hit a
  ceiling or could not read a folder removes nothing under what it could not
  see.
- Three layers against repeated work: same version — not read; same content
  hash — not extracted; known chunk text hash — vector reused. Renaming or
  editing the top of a document does not recompute the rest.
- The extractor, chunker and model versions are stored with what they
  produced. Changing one re-derives in the background.
- A pass is an owned job ([D81](jobs.md)), one at a time per scope, with named
  steps (enumerating, comparing, reading) and ceilings on entries, bytes read
  and file size. A ceiling hit is said on the pass and the scope.
- A schedule per scope. SSH has a longer minimum than personal storage, since
  each read is a transfer (D152). Index now runs a pass at once.
- What the application writes itself — an upload, an edit (D48), a transfer
  (D168), a DDL change (D27) — is queued at once, as a hint; the schedule still
  runs. Writers do not import the index: the hint is a notice the index
  subscribes to at assembly.

Rejected: "modified within the last minute", the legacy watcher's rule. A pass
that did not run in that minute lost the change for good.

Spec: [Search across the application, and an index of any source](../decisions/2026-09-29-search-and-index-design.md)

## D192. Words first, meaning second

- Words: a `tsvector` per chunk (`simple` configuration: the data is Russian and
  English) and trigrams on names. An item is found by words as soon as its text
  is extracted.
- Meaning: vectors arrive later from D193's queue. An item states its stage:
  listed, extracted, by words, by meaning, or failed with a safe sentence.
- Both legs run and merge by reciprocal rank fusion, which uses ranks and needs
  no calibration. Several models are one leg each.
- Vectors find paraphrase and the other language and miss identifiers, codes,
  numbers and names; words do the reverse. A reranker is later, on measurement.
- **The access filter is inside the query, before ranking**: readable by the
  person now, switched on. Filtering after a vector top K loses results;
  pgvector's iterative scan keeps HNSW filtered.
- A result carries a `CatalogNode`, `location`, excerpt, the chunk's locator and
  when the item was read. Opening reads the live node; a gone one says "removed
  since it was indexed".

Spec: [Search across the application, and an index of any source](../decisions/2026-09-29-search-and-index-design.md)

## D193. Vectors are computed by a local model in a service of its own

- An embedder is a protocol: model id, dimensions, token ceiling, query and
  passage forms, `sends_data_out`. The only implementation is a client of a
  local service.
- The service is a compose container with an HTTP interface (TEI, Ollama or an
  ONNX server, chosen when built). Not in the backend: that is one process
  ([D124](backend.md)), and a model takes 0.5–2 GB and whole cores.
- One model for the server, set by a setting. A scope chooses only vectors or
  not.
- Vectors are keyed by chunk text hash and model. A new model is built in the
  background and switched to when complete; the old vectors are removed. Never a
  mix.
- Multilingual: multilingual-e5 small, base or large, or bge-m3, chosen by
  measuring on real documents.
- Embedding is the slow step — tens of chunks a second on a CPU. A queue puts
  what a person asked for before scheduled work.
- Without the service the index works by words and says so, as D103 reports a
  degraded cache.

Known deviations:

- **No external providers.** When one comes, it gets chunks only of connections
  that allow transfer ([D135](ai.md)) and receives the typed query too.
- **No images.** CLIP would be another modality of the same protocol.

Spec: [Search across the application, and an index of any source](../decisions/2026-09-29-search-and-index-design.md)

## D194. The index lives in the application's PostgreSQL

- Scopes, items, chunks and vectors are tables of the application database,
  with pgvector, `tsvector` and pg_trgm. The image changes from `postgres:18` to
  one with pgvector.
- Behind an index store protocol, so the engine can change.
- The access filter, ranking and the cascade from a deleted connection are one
  query and one transaction, with nothing new to run or back up. A dedicated
  engine only on measured need, as D104 decided for Redis.
- A million 1024-dimension chunks is about 4 GB of vectors plus HNSW.
  `halfvec` and a smaller model cut it two to five times.

Known deviations:

- **The index is a plaintext copy of indexed sources.** Searchable text cannot
  be encrypted as D101 encrypts cache values, so backups of the application
  database hold excerpts of every indexed source. Removal deletes; it never
  hides.
- **Indexed text is untrusted input to the agent** — D136's accepted deviation
  through a new door.

Spec: [Search across the application, and an index of any source](../decisions/2026-09-29-search-and-index-design.md)
