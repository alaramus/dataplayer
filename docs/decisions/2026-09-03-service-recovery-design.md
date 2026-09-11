# When starting one goes wrong

## Goal

The fifth item of phase 4: retry, idempotency, cancellation, a log tail,
orphan discovery and deletion semantics — with the roadmap's own sentence at
the centre of it, that deleting a connector must not silently delete a volume.

The pilot before it works when everything works. This is the other half.

## The one that decided the shape: retry

The obvious meaning of retry is "carry on where it stopped": the container is
there, so start it and go on to the connector. It is wrong here, and the
reason is the credential rule from D83.

A password is settled once per attempt, and its only home is the connector
that attempt would have saved. A container left behind by an attempt that
failed before that step therefore has a password *nobody knows* — not the
person, not the server. Starting it would produce a service nobody can open,
and PostgreSQL sets the password when it initialises its data directory, so
the volume cannot be kept either.

So **retry means starting over**, and creation begins with a step that takes
away whatever an earlier attempt left. A first attempt finds nothing and skips
it, which is why the step is reached rather than announced up front.

Two consequences worth stating:

- a service that already has a connection is refused a retry — that one is
  finished, and remaking it would destroy a database somebody is using;
- there is no adoption of a working container whose connector was never
  saved. The password is gone; it is taken away and made again.

## Idempotency, which is the caller's word

`request_id` is optional and chosen by the client, exactly as a run's id is
(D64): only the caller knows that two requests are one intention — a double
press, a POST the network retried. A second request of the same owner with the
same id answers with the service the first one made and the job that is making
it. Without an id, two requests are two services, because they may well be.

Scoped to the owner: an id somebody else chose says nothing about what this
person asked for.

## Cancellation, and what it does not do

There is no `cancelling` state. A task stops at its next await, and this
runner knows the difference between "somebody pressed stop" and "the process
is going away" because the ids it was asked to stop are written down — the
first settles the row as `cancelled`, the second leaves it for the startup
sweep to call `interrupted`.

What the work had already done is left standing. Undoing it would be this
application guessing at what somebody wanted kept; instead a half-made service
is a thing to retry or to remove, and removal is the way out of every state.

Stopping something that has already ended answers with it rather than
refusing: the caller asked for it to be over, and it is.

## Two truths about a container

A service row says what this application believes. The runtime says what is
actually there. The listing carries both, because the interesting case is when
they differ:

| Row says | Runtime says | What happened |
| --- | --- | --- |
| running | running | ordinary |
| running | missing | somebody removed the container by hand |
| running | unknown | this server could not reach a runtime |

One question answers for the whole list — `GET /containers/json` filtered by
label — rather than one inspection per row. `missing` and `unknown` are kept
apart deliberately: an empty answer from a working daemon means every
container is gone, and no answer at all means nothing about any of them.

## Logs

`GET /services/{id}/logs` returns the last lines the container printed, at
most five hundred. The daemon interleaves the two streams into one body with
an eight-byte header per chunk, so the header is stripped — a person reading
why PostgreSQL would not start should not have to read framing bytes. A body
that does not parse as frames is returned as it stands rather than mangled,
because a container with a TTY has no headers at all.

Its own output and nothing else: this application's log is not a user's to
read, and the runtime's words about the machine are not either.

## Orphans

Containers are matched by label, which is why the label exists (D80): a name
is for a person to read and could be changed. A container this installation
made whose service id no row claims is listed by `GET /services/unclaimed`
and can be removed there, with its volume.

It is an administrator's route. What runs on the machine is not one user's
business, and what turns up may be anybody's.

## Deleting, which the roadmap asked about by name

> Deleting a connector must not silently delete a volume.

It does not delete one at all. Deleting a connection deletes a row of this
application; the service that made it keeps running with its data, and the
confirmation says so in as many words when there is a service behind it. The
converse holds too: removing a service takes the container and the volume —
that is what it is for — and leaves the connection, which may be shared, may
be named in somebody's query history, and is not that command's to destroy.

Neither half is quiet, and neither half reaches into the other.

## How it was verified

Nineteen tests through the routes with a fake engine, including a fake that
can be held mid-pull so that cancellation is about cancelling rather than
about who was faster. Then against the real daemon: the same request id twice
gave one service, the listing reported `running`, the log tail came back as
PostgreSQL's own lines with no framing, `unclaimed` was empty, and removal
left nothing behind.

## Decision

**D84. What goes wrong is a state somebody can act on.** The statement, its
consequences and the known deviations are in
[managed services](../architecture/services.md).

## What is not here

A second template — Redis is the next item — and the threat model that would
let any of this be switched on outside local development, which is the item
after that.
