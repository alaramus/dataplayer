# Starting a PostgreSQL and receiving a connection

## Goal

The fourth item of phase 4, and its exit condition: a person requests an
approved service from the connector window, watches it become ready, and
receives a normal encrypted connector — without the browser constructing
anything about a container.

## What had to be settled

The three items before this one left a plan nobody could use: templates
decided what would run (D80), jobs decided how long work is owned (D81), and
the engine decided how a runtime is reached (D82). What was missing is the
last mile — where the container is put, when it counts as ready, and what
becomes of the credentials.

### Where it is put

A managed PostgreSQL has to be reachable *by this server*, which is what will
use it. Two ways were available:

- **publish a port on the host** and connect to it. That needs a free port to
  be found, opens the machine's network surface, and hands the person a way in
  that the threat model has not been asked about;
- **join the network the backend is already on** and reach the container by
  name. Docker resolves a container name on a shared network, which is exactly
  what a connector's `host` field needs.

The second, and nothing is published. `SERVICE_NETWORK` names the network; a
server without one offers nothing at all, because a service that could be
started and never reached is not an offer. That is the third reason the
availability answer can carry, beside "switched off" and "no runtime".

### When it is ready

Not "the container is running": PostgreSQL initialises its data directory on
first start, and the port answers before the server does. The old application
had this right and called `check_connection` up to thirty times; the idea is
kept and the machinery is a job step.

Readiness is asked of *the adapter*, with the very options the connector will
hold. "Ready" means "this connection works", and the only thing that can say
so is the thing that will be used. It is a `ReadinessProbe` protocol for the
same reason the engine is one — so the pilot can be exercised without a
database to wait for — and its one implementation polls once a second until
the template's `startup_timeout_seconds`.

### What becomes of the credentials

They go into the connector, and nowhere else.

```python
config, secrets = split_options(kind, dict(options))
connector = await connector_crud.create(session, name=..., adapter_type=kind.name, ...)
```

The same call an ordinary connector is made by, so the adapter's own model
validates it and D4's schema split encrypts the password without anything
being told that it is one. A service row holds no credentials at all: a
creation that fails before this step leaves a container nobody can use, and
the answer to that is to remove it rather than to store a secret in a second
place.

There is a test that the password appears neither in the connector's `config`
nor in the encrypted blob as plaintext nor in what the API answered.

## What a person does

One button in the source-type catalog — "Start one here" — beside "Create
connection", offered only where this server has a template for that type and
disabled with the server's own reason where it cannot use it.

Then one question: what to call it. The image, the port, the user, the
database and the password are the server's; the name is the only part a person
knows better, and two databases called "PostgreSQL" are two rows nobody can
tell apart.

After that the catalog closes and the work is watched beside the connections:
a step out of the list the server declared, never a percentage. When the job
succeeds the connection is simply there, in the ordinary list, and opening it
reads the catalog of the database that was just made.

A service and its connection are both shown, because both are true of it: the
connection is how a database is used, and the service is the container it
lives in. The service row is the only place its life can be ended.

## How it was verified

- Unit and route tests with a fake engine and a fake probe, including that the
  connector holds exactly what the container was started with, and that a
  service which never answers fails with no connector.
- The whole lifecycle against the real daemon, through the API: created in
  6.1 seconds, `check` answered ok in 6 ms, the catalog listed `public`, then
  stop, start and delete — with the container and the volume gone afterwards.
- A Playwright scenario that starts one from the catalog, waits for the
  connection, opens it, removes the service and deletes the connection. It
  runs in 13 seconds against the development backend, which has the socket.

## Decision

**D83. A ready service is an ordinary connection, and its credentials live
there.** The statement, its consequences and the known deviations are in
[managed services](../architecture/services.md).

## What is not here

Stop and start from the screen, retry, cancellation, a log tail, orphan
discovery, and the deletion semantics that tie a service to the connector it
made — including the rule that deleting a connector must not silently delete a
volume. All of them are the next item.
