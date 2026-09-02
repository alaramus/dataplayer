# Owned jobs

Work that outlives the request which asked for it: what a job is, how it says
where it has got to, and what happens to one when the process running it stops.
Read this before making something wait, before adding a kind of long work, or
before putting progress on a screen.

Decisions here: D81.

## What exists today

One table, one runner, one topic, one read route. Its first user is the
lifecycle of a [managed service](services.md); the phase that introduced it
names backup and restore as the second.

```
backend/app/jobs/
├── models.py     Job, its kinds and its states
├── crud.py       database access only
├── runner.py     the handler protocol, the task, the restart sweep
├── recovery.py   settling what a stopped process left behind
├── topic.py      jobs on the socket
└── routes.py     GET /jobs/{job_id}
```

```
GET /api/v1/jobs/{job_id}
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
  interrupted`. Cancellation is not among them yet — stopping a pull halfway
  has semantics of its own, and it arrives with retry and idempotency.
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
  report the outcome of a race.
- **A job is its owner's.** Somebody else's is not found rather than refused,
  the rule connections already follow (D33).

Known deviations:

- **No cancellation.** `aclose` cancels tasks at shutdown, and the sweep ends
  their rows, but a person cannot stop a job they started.
- **No retry, and no idempotency key.** Asking twice makes two jobs; the
  one-at-a-time rule is what stops them overlapping.
- **A job is carried out by the process that accepted it.** Another process
  can read the row but will not pick up work left `queued` by a process that
  died before starting it — that row is settled as `interrupted` instead.
- **Nothing bounds how many jobs one user may have.** Runs have an admission
  limit; jobs do not yet.
- **Progress is one step at a time.** A pull that takes four minutes reports
  one step for four minutes: there are no bytes, no layers and no percentage,
  because the engine's own progress stream is not read yet.

Spec: [Owned asynchronous jobs](../superpowers/specs/2026-09-02-owned-jobs-design.md)
