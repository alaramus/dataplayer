# Owned asynchronous jobs

## Goal

The second item of phase 4: model create, start, stop, restart and delete of a
managed service as jobs the server owns — durable state, realtime progress,
and a request that never waits for an image pull.

The phase names this as the thing it actually builds. Managed services are its
first user; backup and restore is the second, and the reason it is here rather
than inside the PostgreSQL adapter is that building a second job model inside
an adapter is how the old application ended up with several.

## What the old application had

```python
asyncio.create_task(create_service_image(...))
...
cache_activity[f'{inserted_id}.{user_id}'] = (result, {})
```

A task nobody holds, and a boolean in a dictionary in one process. Four things
follow, and all four were felt:

- a reload lost it, so a person who refreshed the page while an image was
  pulling had no way back to what was happening;
- a second worker never saw it, so the answer depended on which process the
  next request landed on;
- there was no state between "not known yet" and "true or false" — no step, no
  reason, no time;
- nothing settled it. A process that stopped mid-pull left an entry that would
  have said "not ready" for ever, and a container half made.

The readiness loop underneath it was `30 × 10s` of `check_connection`, inside
the same task, with the result of the last attempt winning.

## What replaces it

A row, a task, and a topic.

**A job is a row before it is a task.** `POST /services/` validates the
template key, writes the service down, writes the job down, starts a task and
answers with both. The answer is what was *accepted*, and the job's own route
is where the outcome is read. Nothing waits for a pull — which is the one
requirement the roadmap states in so many words.

**The states are closed and few:**

```text
queued → running → succeeded
                 ↘ failed
                 ↘ interrupted
```

Cancellation is deliberately absent. Stopping a pull halfway leaves a partial
image and possibly a container; that has semantics of its own and arrives with
retry and idempotency, which the roadmap puts in a later item.

**Progress is a named step.** A handler declares `steps` in order — for a
create, "pulling the image", "creating the container", "starting the
container" — and `progress.reached(name)` writes the step and its position
into the row before announcing it on the socket. Two consequences, both
deliberate:

- a step the handler did not declare raises. A person is shown a list of steps
  and then watched through it; showing them something that is not on the list
  is worse than failing;
- there is no percentage. Nothing here knows how big an image is or how fast
  the network is, and D64 already settled that a run "may show … elapsed time
  … but never invents a percentage".

**A kind of work is an object.** `JobHandler` is a protocol — a kind, its
steps, and `carry_out` — and the runner is handed one handler per kind at
assembly. So `service.create` is a class, not a branch in a dispatcher, and
`backup.create` later is another class and one more line where the application
is put together. The kinds are one `Literal` in the jobs package: naming them
costs no dependency on the features that own them, and a kind nothing
recognises is a kind nothing would ever carry out.

**Failure has two shapes.** `JobFailed` carries a handler's own sentence and
becomes the job's message. Anything else is logged and becomes "The job could
not be completed" — because an engine's text names sockets, image digests and
paths of the machine this runs on, which is exactly the rule the adapters
follow for driver text. There is a test that a `permission denied on
/var/run/docker.sock` never reaches the owner.

**A restart ends what it interrupted.** Every non-terminal row becomes
`interrupted` at startup, and nothing is replayed. Re-running a create by
ourselves is how one container becomes two; what a half-finished job left is a
question for whoever looks at the service, and the next item of the phase — the
pilot — is where "what is actually there" gets an answer.

**One job at a time per subject.** A second command about the same service is
409 with the id of the job that is already running, so a client can watch that
one instead. Two at once would be two processes telling one container what to
do.

## The engine is a protocol, and the honest implementation is `NoEngine`

Nothing in this slice talks to Docker. `ServiceEngine` is a protocol with the
five verbs a service's life is made of, and the implementation the application
runs with is `NoEngine`, which refuses everything with "This server has no
container runtime, so it cannot run services".

That is not a stub standing in for something unfinished — it is the truth
about this deployment: the backend runs in a container with no socket mounted,
and detecting a runtime is the next item. A person asking for a service today
gets a job that fails at its first step with a sentence they can act on, which
is a better state to ship than a route that pretends.

It also makes the model testable the way it should be tested: a fake engine
that records what it was told and can refuse on demand, driven through the
real HTTP routes and the real runner, proves the lifecycle without a daemon.

## Where the credentials are not

A service row holds no password. The credentials a service is started with
belong in the connector it becomes — one encrypted home, D4's schema split —
and a creation that fails before the connector exists leaves nothing usable.
That is why the create handler here stops at "started": waiting for readiness
and saving the connector arrive with the pilot, together with the engine that
makes either possible.

## Decision

**D81. Long work is a row the server owns, not a request that waits.** The
statement, its consequences and the known deviations are in
[owned jobs](../architecture/jobs.md).

## What is not here

Cancellation, retry, idempotency keys, a log tail, orphan discovery and a
bound on how many jobs one person may have. All are named by the roadmap item
that follows the pilot, and each is an addition to this model rather than a
change to it.
