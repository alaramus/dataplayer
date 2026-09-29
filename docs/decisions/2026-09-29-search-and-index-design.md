# Search across the application, and an index of any source

Date: 2026-09-29. Decisions: D188, D189, D190, D191, D192, D193, D194.
Builds on D76 (searching one catalog), D81 (owned jobs), D33 and D135 (who
reads a connection, and what may leave the server).

Nothing here is built yet. This is the design the slices at the end follow.

## The problem

There is no way to find something across the application. What exists is per
place:

- D76 searches one connection's catalog, live: a name, or the text inside
  files, by walking the tree within ceilings. It is as wide as one connection,
  slow on a large tree, and knows no meaning: "invoice" does not find "счёт".
- Connections, pipelines, dashboards, saved queries and chats each have their
  own list with its own filter.
- The guide (D183) cannot be searched.

The header has room for one field that works everywhere.

The legacy application had a file index. A folder was marked for indexing, a
watcher looked at it every 60 seconds, new and changed files went through a
local embedding model into Qdrant, and a search by meaning was fast. Its code
shows four things:

- **A change was detected by the clock.** `file_watcher.was_modified_within`
  took a file as changed if its modification time fell in the last minute. A
  pass that did not run in that minute lost the change for good. It was later
  patched with "re-index whatever is not in the index" (AI-#648).
- **A chunk's id was `uuid5(user_id:path:chunk_index)`.** Renaming a file
  re-indexed it whole. An edit near the top shifted every chunk index after it.
  A shared file was indexed once per person.
- **The vector store was two things at once.** It was a connector type (the
  Qdrant and FAISS adapters) and a part of the file adapter
  (`file_explorer/qdrant_operations.py`). The file source knew about Qdrant,
  which is why indexing could only ever be about files.
- **Worth keeping:** vectors of different models in different collections,
  chunking by structure (Markdown, JSON, SQL), and the model in a container of
  its own (`onnxserver`).

What was asked: index any source, not only files; one field in the header that
finds application objects, connections, indexed documents and the text inside
them, without the person choosing first where to look.

## Terms

- **Source** — a connection and its adapter with optional capabilities (D1,
  D2). Nothing new. A `DataSource` abstraction beside it would be a second
  registry of the same thing.
- **Scope** — what a connection's owner asked to be indexed: a node, and what
  is under it.
- **Item** — a node, and later a row, as the index knows it: identity, version,
  metadata, stage.
- **Chunk** — a piece of an item's text, with a locator: a page, a range of
  lines.
- **Pass** — one run over a scope: enumerate, compare, read what changed.
- **Provider** — anything that answers what is typed in the field. The index is
  one provider.

## D188. The search field asks providers, and never a connection's server

**A source and a provider are different things.** Connections, pipelines,
dashboards, saved queries, chats and guide pages have no connector. They are
found in the application's own database. The index is one provider among them.
A person's own Qdrant or Elasticsearch, added as a connection, is a source like
any other and has nothing to do with the application's index. The legacy
application mixed the three.

**One field, several providers, groups.** The field is in the header and Ctrl+K
focuses it. What is typed goes to every provider at once. Each has its own time
budget, and each group appears when its provider answers, so a slow group does
not hold back a fast one.

**Not one ranking.** A connection matched by name and a paragraph close by
cosine distance are not on one scale. A list merged from them would be ordered
by accident. Inside a group the provider orders. Between groups a fixed rule
orders:

- text shaped like an identifier, `schema.table`, a path, a UUID, an email or a
  number raises the providers that match exactly;
- several words, or a question, raises content and offers Ask AI;
- the connection of the panel being looked at raises its own results;
- `in:<connection>`, `type:<kind>` and `>` for commands narrow explicitly.

A language model reading the intent on each keystroke was rejected: seconds of
delay, a cost per keystroke, and the typed words sent to a third party (D135).
Rules are deterministic and can be tested.

**The field never sends a request to a connection's server** — not to find
names, not to check a result. Table names in a database are found only if the
owner made a names scope (D189). Searching one connection live stays D76,
inside its catalog, where the person chose the connection.

Rejected: asking every switched-on database for matching relation names while
searching. It would be fresh and copy nothing. But every search would reach
every server, a server that is down would hold its group until a timeout, and
the owner decided that nothing reaches a connection unless asked for.

**The first providers:** commands and places; connections, by name, type and
host; pipelines; dashboards; saved queries; chats; guide pages; the index
(D190–D192).

**A provider for a feature lives with that feature** and is handed to the
search when the application is assembled, the way the job runner is handed its
handlers (D81). The search package imports no feature above it. A provider for
something below it in the layers — connections, the guide — lives in the
search package.

**A result is a pointer.** It opens through intents the workspace already has:
open in the workspace, show in the catalog. An index result is a `CatalogNode`
with `location` and an excerpt, D76's shape, so a found file opens, is shown in
its catalog and offers its actions like any node.

**Ask AI** sends the typed words to the agent as a new message. The agent gains
a `search` tool over the same providers. It runs as the person (D133), and
results of a connection that does not allow transfer are withheld like any
other tool result (D135).

**Typed words are matched, never compiled** (D2c). They reach the full-text
functions as a parameter. The prefixes are parsed by the field into a closed
filter.

## D189. Nothing is indexed until a connection's owner names a scope

**Nothing by default.** The application makes no scope, not even for names. A
person who never asks has an empty index and a field that finds application
objects and the guide.

**A scope** is:

- a connection and a root node;
- depth: the node's whole subtree, or its level only;
- what is taken: `names`, or `names_and_content`;
- whether chunks get vectors, for content only;
- filters: formats, the largest file;
- a schedule, and whether the scope is on.

Names are what a catalog lists: file and folder names and paths; schemas,
relations, columns and their comments. Content is the text inside, as far as a
format reader reads it.

**Only the owner makes, changes, pauses or removes a scope.** A scope is a
policy of the connection, like the transfer flag (D135), not a preference of a
person. A grantee sees the connection's scopes and cannot change them.

**The index belongs to the connection.** Everybody who can read the connection
(D33) finds what it holds. The legacy per-person index is gone. This is the
same as browsing, with one difference the form says out loud: a search finds
in one query what a person may never have opened. The form states how many
people can read the connection.

**Where a scope is made:** Index… in the catalog's menu on a node, the way a
folder was marked in the legacy application; and an Index page in the
connection's window listing every scope with its state, last pass, what it
holds, errors, pause and remove.

**What ends it:**

- a switched-off connection (D20) returns nothing, and its scopes do not run;
- deleting a connection deletes its index in the same transaction;
- removing a scope deletes what that scope alone brought in.

**Coverage is said.** "Nothing matched" and "did not look" are different
answers (D76). The content group says which connections are indexed and how old
each index is. With nothing indexed it says so, and says how to begin.

## D190. A source feeds the index through capabilities and knows nothing about it

The index is a package of its own. Adapters do not import it. It asks them
through protocols, as routes do.

- **Enumerate** a scope: for each item its key, version token, name, kind,
  `location` in the source's words (D21), type and the times the source states
  — no content. Every source with a catalog can do this through a bounded
  `list_children` walk with D76's ceilings. A source may answer more cheaply:
  an object store's listing, one catalog query.
- **Version token:** what the source itself changes when the item changes —
  modification time and size, an ETag, a commit, `updated_at`. A source without
  one gets a content hash, which costs a read.
- **Read:** the content capability the source already has. Nothing new.
- **Change feed**, optional and later: what changed since a cursor. Without
  one, a pass enumerates.

**Text is extracted by format, not by source.** A PDF from personal storage,
from SSH and from a later object store is read by one extractor. The readers
are the ones content.md already has (D47, D51, D53). An extractor returns a
normalised document: a title, sections of text each with a locator (page, line
range), typed metadata, and the times the source states.

**Chunks follow structure:** headings, paragraphs, JSON and SQL blocks, with a
ceiling per chunk and per document.

**An item is `(connection_id, node_id, sub_key)`.** `sub_key` is empty until
rows are indexed. It will hold a row's key, so rows arrive without changing
what a key means.

**The first implementer is the explorer's storage (D150).** Personal storage
and SSH get indexing through the storage interface, and a later storage gets it
with no code of its own. This is where "not built around files" holds: files
are the first thing behind a general interface, not the shape of it.
PostgreSQL implements enumeration for names scopes.

## D191. What changed is known from stored versions, never from a clock

**Each item keeps** its version token, its content hash and the pass that last
saw it. A pass enumerates, compares, and reads only what differs. A pass that
did not run loses nothing: the next one compares against the same stored state.

**Deleted is decided only by a complete enumeration.** An item that a pass over
the whole scope did not see is removed. A pass that hit a ceiling or could not
read a folder removes nothing under what it could not see. Otherwise a network
blip on SSH would empty the index.

**Three layers against repeated work:**

- the version is unchanged — the item is not read;
- the content hash is unchanged (touched, renamed) — the text is not extracted;
- a chunk's text hash is already known — its vector is reused.

Renaming, copying, or editing the top of a document does not recompute the
rest. This is what the legacy `uuid5(user_id:path:chunk_index)` could not do.

**What produced an item is stored with it:** the extractor, chunker and model
versions. Changing one re-derives in the background. A changed model is D193's
rebuild.

**A pass is an owned job (D81),** one at a time per scope. Its steps are named:
enumerating, comparing, reading. It has ceilings on entries, bytes read and
file size, and a ceiling hit is said on the pass and on the scope.

**A schedule per scope,** not one global interval. Personal storage can be
looked at every minute. SSH has a longer minimum, since each read is a transfer
(D152). Index now runs a pass at once.

**What the application writes itself is queued at once:** an upload, an edit
(D48), a transfer (D168), a DDL change (D27). It is a hint, not a feed; the
schedule still runs, because the application is not the only writer. Writers do
not import the index: the hint travels through a notice the index subscribes to
at assembly.

## D192. Words first, meaning second

**Words:** a `tsvector` per chunk, and trigrams on names. An item can be found
by its words as soon as its text is extracted.

**Meaning:** vectors arrive later, from D193's queue. An item says which stage
it reached: listed, extracted, found by words, found by meaning, or failed with
a safe sentence.

**Both legs run and are merged by reciprocal rank fusion.** RRF uses ranks, so
the two scores never have to be calibrated against each other. Vectors of
several models are one leg per model.

Why both: vectors find a paraphrase and the other language, and miss
identifiers, error codes, numbers and names; words do the reverse. A reranker
over the top fifty is a later step, if measurements ask for it.

Word search uses the `simple` configuration. The data is Russian and English,
and a stemmer per language is its own decision.

**The access filter is inside the query, before ranking:** the connection is
readable by the person now, and switched on. A filter applied after the top K
of a vector search loses results. pgvector's iterative scan keeps an HNSW
search filtered.

**A result says its age.** It carries a `CatalogNode`, `location`, an excerpt,
the chunk's locator, and when the item was read. Opening reads the live node;
one that is gone says "removed since it was indexed" rather than failing.

## D193. Vectors are computed by a local model in a service of its own

**An embedder is a protocol:** model id, dimensions, token ceiling, the query
and passage forms (e5 models prefix both differently), and `sends_data_out`.
The first and only implementation is a client of a local embedding service.

**The service is a container in compose** with an HTTP interface: Hugging Face
TEI, Ollama or an ONNX server, chosen in the slice that builds it. It is not in
the backend's process. That is one process (D124), and a model takes 0.5–2 GB
and whole cores. A container can be limited by Docker and later given a GPU.

**One model for the server,** chosen by a setting. A scope chooses only whether
its chunks get vectors.

**Vectors are keyed by the chunk's text hash and the model.** Changing the
model builds the new vectors in the background; search switches once they are
complete, and the old ones are removed. An index mixing two models is silently
wrong.

**The model is multilingual.** Candidates, to be chosen by measuring on real
documents:

| Model | Dimensions | Note |
| --- | --- | --- |
| multilingual-e5-small | 384 | fastest on a CPU |
| multilingual-e5-base | 768 | the middle |
| multilingual-e5-large | 1024 | the legacy one |
| bge-m3 | 1024 | long input |

**Embedding is the slow step.** A large model on a CPU does tens of chunks a
second, so a million chunks take hours. A queue puts what a person asked for —
a new scope, Index now — before scheduled work.

**Without the service the index works by words,** and says so on the scope and
in the field, the way D103 reports a degraded cache.

**External providers are not built.** The door left for them is
`sends_data_out` and vectors keyed by model. A provider's embedder would get
only chunks of connections that allow transfer (D135); the rest stay on the
local model or on words. The typed query would reach it too.

## D194. The index lives in the application's PostgreSQL

Scopes, items, chunks and vectors are tables in the application database, with
pgvector, `tsvector` and pg_trgm. The database image changes from
`postgres:18` to one with pgvector.

**Behind an index store protocol,** so the engine can change without changing
the indexer or the providers.

**Why here:** the access filter, the ranking and the cascade from a deleted
connection are one query and one transaction. There is nothing new to run,
watch or back up. A dedicated engine (Qdrant, OpenSearch) comes only on
measured need, as D104 decided for Redis.

**Size:** a million chunks of 1024 dimensions is about 4 GB of vectors, and
HNSW adds to that and wants memory. `halfvec` and a 384–768-dimension model cut
it two to five times.

**The index is a plaintext copy** of what indexed sources hold. Searchable text
cannot be encrypted the way D101 encrypts cached values. Backups of the
application database hold excerpts of every indexed source. Removing a scope or
a connection deletes; it never hides.

**Indexed text is untrusted input to the agent.** A document can carry
instructions, which is D136's accepted deviation met through a new door.

## Rejected

- **A `DataSource` abstraction beside connections.** A second registry of what
  D1 and D2 describe, and D2a's families again.
- **Indexing everything connected by default.** A stale second copy of every
  source, a wider leak, and hours of embedding. The owner asks.
- **The index as a connector type,** as the legacy Qdrant and FAISS adapters
  were. The application's index is not a source a person browses.
- **An index per person.** The same file indexed once per reader, and two
  people with the same access finding different things.
- **Live name search across databases from the field,** and **a language model
  reading the intent** — see D188.
- **One merged ranking** — see D188.
- **The model inside the backend's process** — see D193.
- **Detecting change by a recent modification time** — the legacy watcher; see
  D191.
- **A separate search engine from the first day** — see D194.

## Order of work

Each slice is useful on its own.

1. The field, with commands and places, application objects and the guide. No
   index.
2. Scopes and the content index for explorer storages, by words only; passes as
   jobs; the Index page and menu item; the agent's `search`.
3. The embedding service, vectors, and the hybrid merge.
4. Names scopes for PostgreSQL.

Later, each when it is asked for:

- rows of tables — a person names the key, the text columns, the title and the
  change column; without that mapping a table is noise and cannot be tracked;
- external embedding providers;
- change feeds;
- images, as another modality of the same embedder protocol (the legacy
  application used CLIP).

## Known deviations

- Rows of tables are not indexed. A table is found by name only, through a
  names scope.
- There are no change feeds: every pass enumerates.
- There are no external embedding providers and no images.
- Where the field stands beside what the header already carries — the leading
  control, detached windows' tabs (D93), a waiting pair (D167) — is decided in
  slice 1.
