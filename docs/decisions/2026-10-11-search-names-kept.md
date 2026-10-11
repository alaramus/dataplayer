# Search, phase 2: names kept

Date: 2026-10-11. Decisions: D212 through D216. Their architecture home is
[search-kept.md](../architecture/search-kept.md). Slice S11 of
[Universal search](2026-10-02-universal-search-design.md), whose "Phase 2"
section gave the direction; this spec makes it decisions and changes one part
of it: where the choice is made.

Status: agreed on 2026-10-11, built on the branch `search-index` to be looked
at before it is merged.

## Outcome

A connection's owner opens **Search index…** from the catalog's Actions menu,
switches on "Keep a list of names" and picks how fresh it must be. A worker
process reads every name the connection holds — schemas and relations, keys,
folders and files — into a table of the application database. From then on a
name in that connection is found as fast as a connection row, the Search tab
says the list was read 12 minutes ago, and a large tree over SSH is found while
typing. A **Search index** tool in the panel at the foot of the screen, opened
from a block on the tool rails, lists every connection whose names are kept,
with its state, its age and Refresh. A connection whose names are kept wears a
small mark in the Connections list.

## What changed from the direction

The direction put the switch in the connection window, beside the transfer
flag. The user moved it: a setting in the window is found by somebody who
already knows it is there, while the catalog's Actions menu is where a person
looks for what can be done to a connection, and a tool on the rails is on
screen all the time. The window keeps a line saying what is kept.

A list is kept for the whole connection. A folder of one, with its contents,
is phase 3's scope; the same window will grow that section then.

## Evidence

- `CatalogActions.vue` already holds one line about the connection itself,
  Backups, a client verb that opens a window (`BackupsDialog`). Search index
  is the second.
- The foot panel's tools are one registry (`bottomTools.ts`) and a rail block
  one more (`toolBlocks.ts`); Services and Logs are lists with states, the shape
  this tool has.
- The metrics collector (D127) is the precedent for a second process: the same
  image, `python -m`, its own log file, connections opened with the owner's
  credentials and no pool.
- `Outcome.way`, `Outcome.as_of`, `Hit.via` and `Hit.as_of` exist since S1 and
  nothing sets `kept` (D203). This phase sets them.
- No adapter enumerates its names today; every search filters by words. The
  live walks are the model: PostgreSQL's one catalog query, Redis's `SCAN`,
  the explorer's breadth-first walk.

## D212. A connection's names are kept by its owner's choice, made from the catalog

- **Search index…** is a line of the catalog's Actions menu about the
  connection, offered on every connection whose type `EnumeratesNames`; on any
  other it is disabled with the reason. It opens one window per connection.
- **Only the owner changes it**, as with transfer (D135): the route answers 403
  to a grantee. A grantee opens the same window read-only and sees the state.
- **Off by default.** Switching it off, or deleting the connection, deletes
  every kept name of it in the same transaction.
- **The window says what it costs**: a plaintext copy of the names in the
  application database, read with the owner's credentials.
- **A freshness window**: 1 hour, 6 hours, 1 day (the default) or 1 week.
- **Seen from three more places**: the Search index tool at the foot (every
  kept connection the person can see, its state, names, age, Refresh, the
  window), a mark beside the name in the Connections list, and a line in the
  connection window's Options page. The mark is on trial: the user decides
  whether it stays after looking at it.
- **Offered where it is needed**: a names cell of a connection the person owns
  that ended `stopped` or `late` offers "Keep names" beside its own gesture.

Spec: [Search, phase 2: names kept](2026-10-11-search-names-kept.md)

## D213. A pass reads names through the source's own enumerator

- **`EnumeratesNames`**, a capability: `enumerate_names(limit, bounds)` yields
  batches of names. PostgreSQL lists schemas and relations in one catalog
  query; Redis scans every database and describes each batch of keys in one
  round trip; the explorer walks breadth first, links not followed, at most
  `MAX_DEPTH` deep — never through `list_children`, which refuses a folder of
  more than 2,000 entries.
- **A kept name is the hit it would be live**: the `CatalogNode`, parent,
  location, ancestors and the name matched (a Redis key's whole name), plus a
  `scope` — the subtree whose reading vouches for it: the parent folder, the
  Redis database, the whole connection for PostgreSQL.
- **A pass that finished deletes what it did not see**, except under a scope
  the source could not read (a folder that failed, a database that dropped).
  A pass stopped by its ceiling (`SEARCH_KEPT_MAX_NAMES`, 200,000) or its clock
  (`SEARCH_KEPT_PASS_SECONDS`, 900) adds and refreshes what it saw and deletes
  nothing, and says it is partial. A pass that failed keeps the old list and
  its sentence.
- **Built with the owner's credentials**, on a connection of its own (D127's
  way). A key whose passphrase lives only in the backend's memory (D147) is
  not held by the worker; the pass fails `locked` and says so.

Spec: [Search, phase 2: names kept](2026-10-11-search-names-kept.md)

## D214. Passes run in one worker process, and the backend reads their state from rows

- **`python -m app.search.keeper`**, the compose service `search-keeper`, the
  backend's image with the user storage mounted. Not in the backend: one SSH
  tree of 100,000 entries must not share D124's one process with every request.
- **Every 5 seconds** it takes what is due: never read, marked stale, asked to
  refresh, or older than half its window — so a list that keeps passing never
  expires. At most two passes at once; one connection never twice.
- **State lives in `search_keep`**: the window, when it was asked for, the last
  pass's start, end, outcome, count and sentence, and `kept_at`, the end of the
  last pass that wrote the list. Refresh is a request column the worker takes.
  The screens poll it; the worker does not announce on the socket.
- **It logs to `search-keeper.log`**, read by the Logs panel like the others
  (D184), and is not started by `docker compose up -d db backend` — D127's
  trap, the same answer.
- **Not a job.** A periodic, idempotent pass would fill the footer and the job
  table; the tool at the foot is where its state is seen.

Spec: [Search, phase 2: names kept](2026-10-11-search-names-kept.md)

## D215. A kept list answers the names cell, and what it cannot answer stays live

- **The plan asks the list** for a connection's names cell when the list is
  usable: the connection is switched on, the list has been written, it is not
  stale, it is younger than its window, the cell is not scoped to a level, and
  at least one word is three characters long (what trigrams serve). Otherwise
  the cell is live as before. A usable list makes the cell `instant`, so it is
  asked while typing for every connection, not only those in context.
- **One query** of `search_name`: the connection visible to the person and
  switched on, inside the query (D199); every word in the folded name, as a
  `LIKE` on a bound, escaped value, backed by a trigram index; exact and prefix
  names first, then by length and name, up to the cell's rows plus one. The
  engine classes every hit by the rule, as it does a live one (D202).
- **The answer says where it came from**: the outcome's `way` is `kept`, its
  `as_of` and every hit's are `kept_at`, the hit's `via` is `kept`. A partial
  list answers `stopped` with its notice.
- **Folded once, in the process**, by the rule's own `casefold`, when a name is
  written; so `strasse` finds `straße` in a kept list, which PostgreSQL's
  `lower()` does not do live (D202's deviation).

Known deviations:

- **A scoped search stays live**: "Search in ‹connection›" from a level asks
  the source, because a subtree of a kept list is a different query per source
  type.
- **A switched-off connection keeps its list** until it is switched back on or
  its list is switched off; nothing asks it meanwhile (D20).

Spec: [Search, phase 2: names kept](2026-10-11-search-names-kept.md)

## D216. What renames in DataPlayer marks the list stale at once

- **`NamesChanged`**, a protocol in `app.connectors`, is handed in at assembly;
  `app.search` implements it by setting `stale_at`, and the worker takes the
  connection on its next tick. A stale list is not asked: the cell is live until
  the next pass ends, so a renamed table is never found under its old name.
- **Who calls it**: an action whose result creates, replaces or reloads nodes
  (rename, delete, upload, new file); DDL that creates or drops a relation; a
  SQL commit with a schema effect; a transfer into a connection; a copied table.
  Not a row edit, which would keep a busy database's list stale for ever.
- **A change made elsewhere** is seen at the next pass, within the window.

Spec: [Search, phase 2: names kept](2026-10-11-search-names-kept.md)

## Rejected

- **The switch in the connection window**, the direction's place — see above.
- **A space of its own**, like Pipelines: a space is a mode of work; the index
  is set once and looked at now and then, which is what the foot panel holds.
- **A source action (D9)**: actions belong to a source; the index belongs to
  the application and is the same for every type.
- **Grantees keeping a list**: it is a plaintext copy of the owner's names, so
  it is the owner's consent (D135).
- **Announcing passes on the socket**: the worker is another process (D124);
  polling the state row while a screen shows it is enough.

## Slices

- **S11a, backend.** `EnumeratesNames` for PostgreSQL, Redis and the explorer;
  the tables and `pg_trgm`; the keeper; the routes; the kept cell; the stale
  hook. Acceptance: a pass over the development PostgreSQL keeps `pg_class`;
  `class` finds it with `way: kept` and its `as_of`; a word of two characters
  is answered live; a grantee is refused the switch and sees the state; a
  switched-off connection's kept names are found by nobody; a stale list is
  not asked; a finished pass deletes a dropped table and keeps a folder that
  failed; switching off deletes the names.
- **S11b, browser.** The Actions line and the window, the foot tool and its
  rail block, the mark, the Options line, "Keep names" in the Search tab.

## Validation

Each slice records here the checks it ran and their results.

- **S11a.** `pytest tests/search/test_kept.py`: 19 passed — a pass over the
  development PostgreSQL keeps `pg_class`, found while typing out of context
  as `kept` and `instant` with its `as_of`; an exact name first; `100%` a
  character; `pg` asked live; a stale list and one past its window asked
  live; a switched-off connection's names found by nobody, nor by somebody
  without standing; a grantee refused the switch and Read now and shown the
  state; switching off deletes the names; a finished pass deletes what it did
  not see and keeps an unread folder's; a pass stopped short deletes nothing; a
  failed pass keeps the list and is not retried at once; a type without
  `EnumeratesNames` refused 501; files kept by folder and a deleted file gone
  after the next pass; New file marks the list stale; Redis keys kept with
  their ancestors. `pytest tests/search tests/alembic tests/system
  tests/transfers tests/connectors/test_action_routes.py tests/core` 284 passed,
  2 skipped, on `dataplayer_test`; `pytest tests/queries` 175 passed on the
  development database, which has `demo_lab`. `ruff`, `mypy`, `lint-imports`:
  clean. The migration applied to both databases, `pg_trgm` included.
- **S11b.** `vitest` 2,519 passed (the window's sentences, when Keep names is
  offered, the Actions line), `type-check`, `lint`: clean. In the browser
  against the rebuilt backend and a running `search-keeper`: Search index… in
  pg-warehouse's Actions menu, switched on and saved; 274 names read within
  seconds; the mark in the Connections list; `pipeline` typed with no catalog
  in context answered by pg-warehouse alone, `way: kept`, every other
  connection skipped; the tool at the foot with Read now; the line on the
  connection window's Options page. No Playwright scenario yet.
- **`check-docs`**: clean.
