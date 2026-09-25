# Transfers as owned jobs

Date: 2026-09-25. Decision: D168. Builds on D81 (owned jobs), D95 (progress
in the footer), D115 (a job nobody was told about), D161, D163, D164 and
D165; the owned transfers promised in
[Interactions between connections](2026-09-25-cross-connector-interactions-design.md).

## The problem

A file copied or moved between connections, and a table saved into a folder
as CSV, run inside one request. There is no progress, nothing can stop them,
and a reload or an upstream timeout loses the answer while the work goes on
or dies unseen. That is why they are held to 20 files and 200 MB, and D161,
D163 and D165 each list "a request, not a job" as a known deviation. The
interactions spec made owned work the condition for raising those ceilings.

A second problem hides under the first. A file bound for an SSH server is
staged whole on this server's disk and only then sent. At 200 MB that is
tolerable; at the ceilings below it is 30 GB of one person's scratch space,
on the disk that holds everybody's personal folders.

## D168. A transfer between connections is an owned job

### What runs as a job

The three paste kinds that move bytes: `file_copy`, `file_move` and
`relation_csv`. A kind declares whether it runs in the request or as a job,
so the route and the client never name one. The two row kinds of D166 stay
requests: their ceiling is D45's 16 MB, set because a file is parsed whole in
memory, and a job would not lift it. Same-connection copy and move stay the
source's own actions (D74).

### Starting one

Paste, and a button of a pair's bar, open the windows they open today — the
name, the conflict — and the checks that decide those windows still answer
at once: a taken name, a selection over the ceiling, missing access. When
they pass, the server writes the job down, starts it and answers; the window
closes. Nothing announces that work has begun (D95): the footer shows it.

- **Ceilings:** at most 1000 files and 10 GB in one paste, one file up to
  10 GB; a CSV stops at 10 GB, as it stops at 200 MB today. Over them, Paste
  refuses before anything starts, with the ceiling in the sentence.
- **Three at a time per person.** A fourth is refused at once, 429, with
  "Three transfers are running — wait for one to finish". The count and the
  new row are one step under a lock on the owner, so two tabs cannot both
  start a third. No invisible queue, the rule D64's runs follow. The number
  is a setting, `TRANSFER_MAX_ACTIVE`, as `QUERY_MAX_ACTIVE_RUNS` is.
- **A Cut is spent when its move starts.** The clipboard forgets the moved
  nodes as soon as the job is accepted, not when it ends.
- **The answer says which it was.** `/paste` answers a discriminated result:
  `done` with D164's result, or `started` with the job.

### While it runs

- **Footer:** the active transfer by what it does and where, with its bytes:
  "Copying to SSH server · 45 MB of 120 MB" and a bar. A CSV has no known
  total and says "Saving orders as CSV · 12 MB written" with no bar: a
  number nobody measured is not shown (D81).
- **Processes:** one row per transfer — "Copy files · Files → SSH server",
  the file in hand and how many of how many, the bytes, and Stop with its
  consequence under it: "Stops at once; files already copied stay", and for
  a move "files already moved stay moved".
- **The catalogs follow it.** The destination re-reads as files are
  published, at most once every two seconds and once at the end, so files
  appear one after another; a move re-reads its source the same way.
- **Nothing in the browser holds it.** Closing the catalog, the pair window
  or the tab does not stop it, and a reload finds it in Processes.

### Stopping and ending

- **Stop takes effect at once**, even inside a large file: the copy checks
  between 1 MB pieces, and between batches for a CSV. The file in hand is
  discarded before the job settles as `cancelled`; files already published
  stay, and for a move their sources stay removed.
- **One file failing is that file's outcome.** A file that changed, vanished
  or found its name taken meanwhile is recorded with its reason, and the
  next one goes. What stops the whole transfer is what no later file could
  survive: a connection that cannot be reached, a grant withdrawn, a
  destination folder gone. The remaining files are "not attempted".
- **Every file has an outcome:** copied or moved, and under which name when
  Keep both renamed it; failed, with the reason; copied while its source was
  kept, for a move whose source changed; not attempted. The job's sentence
  counts them: "Copied 3 of 5 files to reports; 1 failed, 1 not attempted".
  The row lists them, the first ten and how many more.
- **How it ended is told where D113 tells it.** All done: the tab that
  started it says so with the job's sentence, as Paste does now. Anything
  failed, or a restart interrupted it: the job ends `failed` or
  `interrupted` and stays in Needs you until it is dismissed (D115). Stopped
  on request: Recent, with its outcomes — the person pressed Stop and needs
  no reminder of it, the rule D115 keeps for every job.
- **A restart ends it, and nothing resumes.** The sweep marks it
  `interrupted` with the outcomes it had written. Pasting again decides the
  files already there by the conflict rule chosen then.

### What the server adds

- **One job kind, `paste.transfer`,** whose typed payload names the paste
  kind, both connections, the destination place, the conflict rule and each
  item with its size and outcome — the arrangement D123's source operations
  use. Its handler asks the kind to do the work, so a new byte-moving kind is
  a registry entry, not a branch. Its steps are named, as D81 requires; the
  bytes and the counts are measured, not estimated.
- **Both ends are checked again when it starts:** read on the source, write
  on the destination, write on the source for a move. A grant withdrawn
  between Paste and the start fails the job with that sentence.
- **Progress reaches the row at each file and at most once a second within
  one**, and each write is announced, so a listening client and a polling
  one see the same thing.
- **Transfers have threads of their own.** Copying blocks, and a copy of
  10 GB holding a thread of the shared pool for twenty minutes takes it from
  every other blocking call. Transfers run on a limiter of their own, eight
  across the server; one beyond them stays Queued until a slot frees.
- **A file for an SSH server is written there as it arrives,** into the
  temporary name beside its target, then renamed — no longer staged whole on
  this server first. A local folder keeps its staged file beside the target.
  Either way no published file is partial, and this server's disk holds one
  1 MB piece per transfer rather than a whole file.

## Out of scope

- Folders. A folder copied or moved whole is the next step, on this job.
- Rows pasted into a table (D166), and the source-owned copy and move within
  one connection (D74, D95's known deviation).
- Resuming an interrupted transfer, pausing one, and a history of transfers
  beyond the jobs listing.

## Known deviations, accepted with it

- **A crash can leave a staged file.** A process that dies mid-file leaves
  its `.dataplayer-…` temporary beside the target, locally or on the SSH
  server. It is never published under the real name; the startup sweep
  empties this server's scratch but does not reach a connection's disk.

## Acceptance

- Pasting five files into a folder of another connection closes the window
  at once; the footer and Processes show the bytes rising and the file in
  hand; the files appear in the destination one after another.
- Stop in the middle of a large file leaves the files before it, nothing
  under the name of the one in hand, and the job in Recent as stopped.
- A file changed during the transfer is failed with its reason while the
  rest arrive; the job lands in Needs you with the counts.
- A fourth transfer is refused with the sentence above while three run.
- 1000 files or 10 GB pass; more is refused before anything starts.
- A reload during a transfer finds it still running in Processes.
- A grant withdrawn after Paste fails the job when it starts.
- A table saved as CSV runs as a job with bytes written and no bar.
- A file sent to an SSH server never occupies more than one piece of this
  server's disk.

Tests cover the handler — outcomes, stop inside a file, the ceilings, the
concurrency refusal, a withdrawn grant, a restart — on the server; the row,
the footer and the throttled refresh as plain functions; and a copy through
Paste into Processes in the browser.
