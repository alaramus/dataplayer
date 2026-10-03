# Owned jobs

Work that outlives the request which asked for it: what a job is, how it says
where it has got to, and what happens to one when the process running it stops.
Read this before making something wait, before adding a kind of long work, or
before putting progress on a screen.

Decisions here: D81, D95.

## What exists today

One table, one runner, one topic, owner-scoped reads and cancellation. Its first user is the
lifecycle of a [managed service](services.md); the phase that introduced it
names backup and restore as the second. The third is a source operation
(D123, `app/source_operations/`): a reviewed action over a fixed set of source
targets, whose typed payload in `parameters` holds each target's outcome. The
fourth is a transfer between connections (D168, `app/transfers/`), the same
arrangement for files and bytes, and the one kind bounded per person. The
sixth is a search inside files (`search.contents`, [S7](search.md#d200-a-cell-states-its-cost-and-a-mode-spends-only-what-it-may)),
whose words and matches are held in memory and never in its row.

```
backend/app/jobs/
├── models.py     Job, its kinds and its states
├── crud.py       database access only
├── runner.py     the handler protocol, the task, the restart sweep
├── recovery.py   settling what a stopped process left behind
├── topic.py      jobs on the socket
└── routes.py     owned listing, detail and cancellation
```

```
GET /api/v1/jobs/{job_id}
GET /api/v1/jobs/
POST /api/v1/jobs/{job_id}/cancel
```

## D81. Long work is a row the server owns, not a request that waits

The old application started a container with `asyncio.create_task` and kept
what it knew about it in a process dictionary —
`cache_activity[f'{connector_id}.{user_id}'] = (result, {})` — a single
boolean, invisible to a second worker, lost on reload, and never settled if
the process went away. A request that wanted to know waited, polled, or gave
up.

- **A job is a row before it is a task.** The request validates, writes the
  job down and answers; a task carries it out afterwards. Nothing waits for an
  image pull, and a client that has the id can ask again after a reload.
- **The states are closed**: `queued → running → succeeded | failed |
  cancelled | interrupted`. Cancellation leaves completed effects in place;
  service retry and idempotency are defined by D84. A handler that can say
  how far a stopped job got implements `ExplainsStop`; any other reads
  "Stopped before it finished".
- **Progress is a named step, never a percentage.** A handler declares its
  steps in order, and a step it did not declare raises rather than being
  shown: a person promised a list of steps must not be shown something that is
  not on it. Nothing here knows how long a pull takes, and a number would be
  an invention (the same rule D64 states for a run).
- **The step is written before it is announced**, so a client that polls and a
  client that listens are told the same thing.
- **The socket is a courtesy; the row is the authority.** A message that never
  arrives costs nothing, because `GET /jobs/{id}` reaches the same terminal
  state. That is why nothing is queued in the topic.
- **A kind of work is an object, not a branch.** `JobHandler` is a protocol
  with a kind, its steps and one method; the runner is handed a handler per
  kind when the application is assembled, so adding a kind of work is a new
  class and a line of assembly. The kinds themselves are one closed
  `Literal` — a job whose kind nothing recognises is a job nothing would ever
  carry out — and naming them costs the jobs package no dependency on the
  features that own them.
- **A failure carries the handler's own sentence.** `JobFailed` is what a
  handler raises to say the work cannot be done; anything else is logged and
  becomes "The job could not be completed", because an engine's text names
  sockets, image digests and paths of the machine this runs on. Same rule as
  driver text (D2c).
- **A restart ends what it interrupted, and replays nothing.** A non-terminal
  row at startup becomes `interrupted`. Re-running a create by ourselves is
  how one container becomes two; what a half-finished job left behind is a
  question for whoever looks at the thing it was about.
- **One job at a time per subject.** A second command about the same thing is
  refused with 409 and the id of the job already running, because two jobs at
  once are two processes telling one container what to do and the second would
  report the outcome of a race. `admit_exclusive` makes that hold across
  processes: a transaction-scoped advisory lock on the subject in the
  application database serialises the check and the insert. Source operations
  and restores admit this way and exclude each other on one connection;
  services still check, then create.
- **A job is its owner's.** Somebody else's is not found rather than refused,
  the rule connections already follow (D33).

Known deviations:

- **No generic retry.** Services implement retry and idempotency under D84;
  the runner never replays a job on its own.
- **A job is carried out by the process that accepted it, and there is one
  (D124).** The startup sweep ends every non-terminal row, which is honest only
  because no other process can be running one; under several, a worker
  restarted by its supervisor would end its neighbours' live jobs. Work left
  `queued` by a process that died before starting it is settled as
  `interrupted`, never picked up.
- **Only transfers, pipeline runs and searches inside files are bounded per
  person.** `admit_within` refuses one over `TRANSFER_MAX_ACTIVE` (D168),
  `PIPELINE_MAX_ACTIVE` (D177) or a second search inside files (S7); other
  kinds have no such limit yet.
- **Only pipeline runs and searches inside files are ever removed.**
  `forget_finished` keeps a pipeline's newest hundred and takes the rest with
  the pipeline (D180); `forget_finished_of_owner` keeps a person's newest 20
  searches inside files (S7). Never one still going; every other kind's rows
  stay.
- **Jobs are not fanned out through infrastructure Redis.** The database row
  remains the authority and the accepting process performs it. D104 requires
  measured need and a separate durable delivery contract before that changes.
- **Progress is one step at a time.** A pull that takes four minutes reports
  one step for four minutes: there are no bytes, no layers and no percentage,
  because the engine's own progress stream is not read yet.

Spec: [Owned asynchronous jobs](../decisions/2026-09-02-owned-jobs-design.md)

## D95. Progress is visible in the footer and controls follow execution boundaries

The footer's right-hand button names an active operation, shows its progress
and counts other active operations. Selecting it opens the floating Processes
window with progress, outcomes and available controls. Starting work does not
open the window. Closing or minimizing it never cancels work.
Service startup, retry and deletion use this progress surface without a separate
notification that work has begun; a refused request still reports its error.

Server jobs are read through a bounded, owner-scoped listing, active first,
with an independent active count. Vue-query owns this state; socket events
invalidate it and polling recovers missed events. Job steps remain named and
indeterminate. Cancellation uses the existing endpoint and never implies undo.

Catalog actions register existing requests in an application-scoped local
registry. Uploads report transport bytes and then wait for the server's result;
batches report completed requests. Unknown work is indeterminate. A batch may
pause or stop before its next request, keeping completed effects and reporting
unsent items separately. A stopped upload retains unsent and refused files in
the form. A synchronous request has no fake pause, resume or HTTP-only cancel.
Local history retains the latest 50 finished operations until reload/sign-out
or explicit clearing; active work is never evicted. Signing out also stops
unsent requests. Server jobs can still be read after reload.

Known deviations:

- Archive, extract, copy and move inside a single server request have no
  internal byte/entry progress or cancellation checkpoints yet.
- Server jobs cannot pause. An upload has transport progress, not resumable
  transfer. Native browser downloads remain in the browser's download manager.

Spec: [Operation progress in the footer](../decisions/2026-09-04-operation-progress-design.md)
