# The backend runs as one process

## Problem

`backend/Dockerfile` started the application with `fastapi run --workers 4`,
while `docs/architecture/realtime.md` said of the connector health monitor that
"today there is one process". Development never showed the difference:
`compose.override.yml` replaces the command with `fastapi dev`, one reloading
process, and the end-to-end suite runs against that.

Everything the lifespan in `app/main.py` builds belongs to the process that
built it. Read against four workers, the code gives:

- **Open transactions (D66).** `QuerySessions` holds the leased connection. A
  statement, Commit or Rollback that reaches another worker finds no lease and
  answers 404 "No such open transaction".
- **Captured results (D64).** `QueryResults` holds the rows in memory. A page,
  filter or download that reaches another worker answers 404 "This result is no
  longer available".
- **Cancelling a run (D64).** The cancel route writes `cancelling` and asks the
  local `QueryRunner`, which does not hold the run and returns false. The task
  in the other worker is never told; when its statement succeeds, `_mark`
  re-reads the row, finds `cancelling` and records `cancelled` for a query that
  ran to the end.
- **Cancelling a job (D81).** Refused with 409 by any worker but the one that
  accepted it.
- **Topics (D18, D19).** Each worker has its own `TopicSet`. A user whose tabs
  reach different workers gets a health monitor in each, and a socket hears
  only what its own worker probed or was told: a manual check, a run event, a
  job event and an access request are delivered only when the HTTP request that
  caused them reached the same worker as the socket. Runs and jobs fall back to
  polling; the access request waits for the attention poll.
- **Startup sweeps (D64, D81, D123).** Every worker runs the lifespan. uvicorn's
  supervisor restarts a worker that dies or stops answering, and the restarted
  one marks every non-terminal run and job `interrupted`, marks running
  source-operation targets unknown and deletes every restore snapshot — the
  live work of the other three included.
- **Pools and the memory cache (D10, D31).** Already recorded as per process:
  connections multiply and entries are not shared.

## Decision

The backend is one process. The image says `--workers 1` explicitly, because
without the flag uvicorn takes the count from `WEB_CONCURRENCY`. Each of the
areas above states in its architecture file that it is correct because of this
decision, instead of assuming it silently or describing four workers.

The application is network-I/O bound and asynchronous throughout (D3), and
blocking work already runs on threads, so one process is not the bottleneck
four workers were meant to remove. No measurement said otherwise.

A test reads `backend/Dockerfile` and the compose files, and fails when the
image names any count but one or a compose file names a count at all.

## Rejected alternatives

- **Keep four workers and document the consequences.** Transactions and result
  pages would fail at random, by which worker a request happens to reach. A
  known deviation is for a limitation, not for a core feature that does not
  work.
- **Make every piece multi-process now.** A shared channel for topics, routing
  a transaction or a result to the process that holds its connection or its
  memory, cancellation carried by the row and noticed by the holder, and a
  startup sweep that ends only the work of processes that are gone. Each is its
  own design with its own failure modes. D104 requires a measured need before
  Redis carries anything beyond the read cache, and there is none.
- **Sticky routing in front of four workers.** uvicorn's workers share one
  listening socket and have no affinity; a balancer in front of separate
  processes could pin a user, but not the startup sweep, and it would move the
  contract into infrastructure this repository does not describe.

## Consequences

Scaling out is a design change, not a setting. Before a second process exists,
every item under Problem has an answer.

Nothing detects several processes at runtime. A deployment that replaces the
command or runs two containers behind a balancer reproduces the problem, and
this is recorded as a known deviation of D124.
