# Folders carried between connections

Date: 2026-09-25. Decision: D169. Builds on D161 and D163 (files copied and
moved between connections), D168 (transfers as owned jobs) and D74 (a folder
copied or moved within one connection).

## The problem

A file can be copied or moved into another connection; a folder cannot. Ticking
one disables Copy with "Copy files, not folders or links", so a person carries
a tree across by opening every folder and ticking its files, and loses the
empty ones. Within one connection a folder has always gone whole (D74), up to
10,000 entries. Now that a transfer is a job with progress and Stop (D168), the
reason for leaving folders out — a request nobody should wait on — is gone.

## D169. A folder is carried whole between connections

### What is carried

- **Files and folders together.** Copy and Cut take any mix of ticked files
  and folders; Paste, and a button of a pair's bar, run them as one transfer
  through the same two kinds, `file_copy` and `file_move`. What a kind needs
  ticked reads "Tick files or folders to copy" (and "to move").
- **A folder goes whole**: every file below it, and every folder, empty ones
  included, recreated at the destination under the same relative path.
- **A link inside a folder is skipped** and listed as skipped. A link ticked
  itself is refused before anything starts, as a download's archive refuses
  one (D49): a link resolved would carry the tree it points at.
- **Ceilings, checked before anything starts:** at most 10,000 files and
  folders, the ceiling D74 already holds within one connection, and 10 GB,
  D168's. The request walks the folders and stops walking as soon as a
  ceiling is crossed, so a refusal is quick.
- **Not into itself.** Two file connections can open the same personal folder
  at different depths, and a folder pasted into its own subtree would be read
  while it is written. Where both ends are on this machine's disk the real
  paths are compared and the paste is refused; a folder is always carried as
  the list the job walked when it began, so nothing grows under the walk.

### A name that is taken

A taken name opens D162's window as it does for a file. **Keep both** gives
the folder a free name, `reports (1)`. **Replace is not offered when a taken
name is a folder**: the old folder would have to go before the new one had
arrived, and a transfer stopped halfway would leave neither. When every taken
name is a file, the window is what it was. Merging into an existing folder is
not offered.

### While it runs and after

- **Footer:** unchanged — "Copying to SSH server · 120 MB of 3.4 GB".
- **Processes:** the file in hand by its path below what was ticked, and how
  far: "reports/2025/q3.csv — 312 of 4,211". A folder appears in the
  destination catalog when its first entry arrives and fills as the catalog
  re-reads (every two seconds at most, D168).
- **Outcomes by what was ticked.** Each ticked item has one line: "reports —
  4,208 copied, 3 failed, 1 skipped"; a file ticked on its own reads as it
  does today. Under them, the files that did not arrive, each with its
  sentence — the first ten and how many more. The job's sentence counts files:
  "Copied 4,208 of 4,211 files to SSH server; 3 failed, 1 link skipped".
- **Stop** is D168's: at once, what arrived stays.

### A move removes its sources only at the end

A move — of folders and, from now on, of files as well, so one paste follows
one rule — first copies everything. Only then does it remove, at the source,
each file that arrived and is still the version it was read as, and then each
folder that has become empty, deepest first. A folder that still holds
something — a file that failed, a link that was skipped, a file somebody added
meanwhile — stays with what it holds.

- **Stopped or failed before the end:** the source is whole, and the
  destination holds a partial copy the person can see and remove. Nothing is
  split between two connections.
- **Stopped while removing:** every file is already at the destination; what
  was removed stays removed and the rest is still at the source.
- This replaces D163's file-by-file removal, which after a Stop left a batch
  torn across both connections.

### What the server changes

- **The payload holds what was ticked, not every file.** Each ticked item
  keeps its counts — files and bytes planned, arrived, failed, skipped — and
  the transfer keeps a bounded list of the files that did not arrive (the
  first hundred and a count of the rest) and the path in hand. Ten thousand
  per-file records rewritten at every file would be gigabytes of writes.
- **The row is written at most once a second**, and at once at a Stop or the
  end — rather than at every file, as D168 did. (The first draft also wrote at
  once when a ticked item ended; a thousand ticked files made that a thousand
  full writes, so an item's end waits for the next second like the rest.) The
  catalogs still re-read on what arrived, which the payload counts.
- **The walk the job carries out is its own.** The request counts in order to
  refuse early; the job walks again when it starts, so a folder is carried as
  it is then. Totals shown are the request's measurement; a tree that grew
  meanwhile is carried whole, and the bar stops at full.
- **A step for removing:** a move reaches "removing the sources" once
  everything has been copied.

## Out of scope

- Merging into an existing folder; Replace of a folder; carrying links as
  links; file permissions and modification times, which a copy does not keep
  today either.
- The same transfer within one connection, which stays D74's.

## Known deviations, accepted with it

- **Two SSH connections to one server are not compared.** A folder pasted
  into its own subtree through two connections to the same server is carried
  as the list walked at the start, so it cannot recurse, but it is not
  refused either.
- **A crash leaves a partial copy.** What had arrived stays at the
  destination, complete file by file, as D168 leaves a staged file.

## Acceptance

- Ticking a folder enables Copy and Cut; pasting it into another connection
  recreates every file and every empty folder, with the bytes of each file
  unchanged, in one job with a count of files.
- A link inside the folder is skipped and listed; a ticked link is refused.
- More than 10,000 entries or 10 GB is refused before anything starts.
- A folder whose name is taken offers Keep both and not Replace; Keep both
  makes `name (1)`.
- Processes shows the path in hand and "n of m", then one line per ticked
  item and the files that did not arrive.
- Stopping a move halfway leaves the source whole and the partial copy at the
  destination; a completed move leaves no source folder, except one still
  holding a file that failed.
- Moving plain files follows the same rule: sources go only at the end.
- A folder pasted into its own subtree on the local disk is refused.

Tests cover the walk, the ceilings, links, the taken folder name, the
end-of-move removal and Stop at each phase on the server; the item lines as
plain functions; a folder copied through Paste in the browser.
