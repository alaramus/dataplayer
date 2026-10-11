# Search, phase 3: what files hold, kept

Date: 2026-10-11. Decisions: D217 through D219. Their architecture home is
[search-kept.md](../architecture/search-kept.md), beside phase 2's. Slice S12
of [Universal search](2026-10-02-universal-search-design.md), whose "Phase 3"
section gave the direction; built on phase 2,
[names kept](2026-10-11-search-names-kept.md).

Status: agreed on 2026-10-11, when the user asked for phase 3 after phase 2,
built on the branch `search-index`.

## Outcome

In the Search index window of a file connection, opened from the catalog
standing in `reports`, the owner presses **Keep what files hold in reports**.
The keeper reads the text of the files there right after the names, and from
then on Enter finds `reports/q3.csv`, "Line 2: Q3,1200", at once and without the
job of "Search inside files". A file that did not change is never read again.
The window and the tool at the foot say how many files are kept and how many
the rule left out.

## What changed from the direction

- **One window, not a second place.** The direction had "an owner names a
  scope". It is named in the window phase 2 already opens from the catalog,
  which offers the folder the catalog stands in, or the whole connection.
- **No format list and no size choice.** The direction mentioned formats and
  the largest file. The rule live search reads by — text, the storage's own
  ceiling — is the only one, so the two never disagree; PDF and Office wait
  for somebody to ask, as the direction said.
- **Enter only.** A kept contents cell would be cheap while typing, but the
  field's few rows per group are names, and text inside files is the Search
  tab's (D76 kept contents a gesture of its own).

## D217. A folder's text is kept by its owner's choice, in the same window

- **"What files hold"**, a section of the Search index window on a connection
  whose type has `EnumeratesNames` and `ExtractsText`: the folders whose text
  is kept, each with its count and Stop, and **Keep what files hold in ‹the
  folder the catalog stood in›**, or the whole connection.
- **Through the names**: refused 409 until the names are kept, 422 for a node
  whose kept name is not a folder, 501 for a type that cannot read its text.
  Stopping the names deletes the folders and their text with them.
- **The owner's**, 403 for a grantee, as D212.
- **Stop** deletes the text no other kept folder covers.

Spec: [Search, phase 3: what files hold, kept](2026-10-11-search-contents-kept.md)

## D218. Text is read after the names, only where it changed, by the live rule

- **After every names pass that did not fail**, from the file names just kept
  below the folders: a file whose time and size (`version`) are as kept is not
  opened; one whose bytes hash (`digest`) as kept has its chunks left alone; a
  file the rule does not read is kept as such and not opened again unchanged.
- **One rule with the live search**, `explorer/text.py`: not a folder or a
  link, at most the storage's `file_bytes`, no zero byte in the first 4 KB,
  UTF-8 with replacement. `ExtractsText.extract_text` reads a file whole by it.
- **Chunks** of at most 40 lines or 8,000 characters, each with its first
  line's number, folded once by `casefold`, trigram-indexed.
- **Bounds**: the pass's clock and `SEARCH_KEPT_CONTENTS_BYTES` (512 MB) read
  per pass; what is left is read by the next. A pass stopped short deletes
  nothing; a finished one deletes the text of files no kept name holds and no
  folder covers. Each folder records when it was read, its files, what the rule
  left out and why a pass stopped.
- **A file written in place** through the editor marks the list stale (D216).

Spec: [Search, phase 3: what files hold, kept](2026-10-11-search-contents-kept.md)

## D219. Kept text answers a contents cell on Enter, by the live rule

- **Planned** on Enter for a connection whose list is usable (D215) and has a
  folder read at least once: a `contents` cell, `kept`, `instant`, in the
  connection's group, beside the job that still searches the rest.
- **One query of `search_chunk`**, the standing and `enabled` inside it: every
  word in the folded chunk, up to four chunks per row asked. A chunk can hold
  the words on different lines, so the process keeps a file only when one line
  holds them all — the live rule — and that first line is the hit's line and
  excerpt, a node hit of the file with `field: contents`, class `text`.
- **Said as kept**: `way`, `as_of` and `via` as D215's.

Spec: [Search, phase 3: what files hold, kept](2026-10-11-search-contents-kept.md)

## Rejected

- **A format list and a size per folder**: two rules for one file.
- **Kept text while typing**: the field's rows are names.
- **Whole files as rows**: a hit names a line, and a chunk keeps the row small.

## Slices

- **S12a, backend.** `ExtractsText` and the shared rule; three tables in the
  baseline; the pass after the names; `POST` and `DELETE
  /search/kept/{id}/contents`; the kept contents cell.
- **S12b, browser.** The window's section, the tool's line, the folder offered
  from the catalog.

## Validation

- **S12a.** `pytest tests/search/test_kept_text.py`: 11 passed — a word inside
  a kept folder found on Enter with its line, not in a file whose words are on
  two lines, not outside the folder, not in a binary file; not while typing; an
  unchanged file not read again and a changed one read; a touched file keeps
  its digest; a deleted file's text gone; Stop keeps what another folder
  covers; stopping the names takes the text; the whole connection as a scope;
  an edit in place marks the list stale; 409, 422, 501 and 403. Three of them
  went red with the version check and the one-line rule taken out.
  `pytest tests/search tests/adapters tests/connectors/test_file_routes.py
  tests/connectors/test_action_routes.py`: 2,545 passed, 33 skipped, 6 failed —
  three `demo_lab` cases the test database lacks, and three extension tests
  that installed and removed `pg_trgm`, which the baseline now holds: they and
  the E2E scenario use `fuzzystrmatch`, and pass. `ruff`, `mypy`,
  `lint-imports`: clean.
- **S12b.** `vitest` for the lines, `type-check`, `lint`: clean. In the
  browser against a development database built from the baseline: the window
  opened from `reports` offered it, its text kept within seconds ("1 file"),
  and `1200` on Enter showed `q3.csv`, "Line 2: Q3,1200", in the Search tab.
