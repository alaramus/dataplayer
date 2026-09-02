# Detecting a container runtime

## Goal

The third item of phase 4: detect Docker availability and state the refusal
where a service is offered, so that a screen never offers what pressing the
button would refuse.

## Two questions, not one

"Can this server start containers" turns out to be two questions with
different answers and different remedies.

**May it?** Reaching a container runtime is reaching the machine: a process
that can talk to the Docker socket can start a privileged container and own
the host. That is a deployment's decision, not the code's, so `SERVICES_ENABLED`
defaults to false and the socket is mounted only in `compose.override.yml` —
the development file. Threat-modelling it for anywhere else is the last item of
this phase, and until that lands this is the honest default.

**Can it?** A daemon can be down, restarting, or not there at all, and it can
go away while the server runs. So availability is asked when somebody asks
rather than decided at startup, held to a two-second timeout, and it never
raises: not reaching a daemon is an answer.

The two produce different sentences, and that is the point of separating them —
"Managed services are switched off on this server" is something an
administrator changes; "This server cannot reach a container runtime" may be a
daemon somebody has to start.

## Where the refusal is stated

`GET /services/templates` carries `available` and `unavailable_reason` on every
entry. The runtime is a property of the server rather than of a template, so
the two fields are the same for all of them today — and they belong on the
offer because that is where a person decides.

`POST /services/` refuses with 503 and the same sentence rather than accepting
a job that will fail at its first step. A row and a failed job are a mess left
behind by a question that could have been answered. The job remains the
authority for the case the check cannot cover: a runtime that answered and
then went away produces a failed job with the engine's own sentence, and there
is a test that drives exactly that sequence.

## The client

The Docker Engine API is HTTP, and httpx — already a dependency — speaks it
over a Unix socket with `AsyncHTTPTransport(uds=...)`. So this is one module
holding the requests this application actually makes:

| What | Request |
| --- | --- |
| is anything there | `GET /version` |
| fetch an image | `POST /images/create?fromImage=…&tag=…`, stream read to the end |
| make the volume | `POST /volumes/create` |
| make the container | `POST /containers/create?name=…` |
| start, stop, restart | `POST /containers/{name}/…` |
| remove | `DELETE /containers/{name}?force=true`, then `DELETE /volumes/{name}` |

No SDK, and no `docker compose` subprocess — which is what the old application
did, with the command line built by an f-string.

Three details are worth stating because each is a way of getting it wrong:

- **A pull fails inside a successful answer.** The daemon returns 200 and then
  streams what it is doing; an error is a JSON line in that stream. Reading the
  stream to the end is both how a pull completes and how a failure is noticed.
- **The daemon's words do not cross.** Status codes map to this repository's
  own sentences and the daemon's message goes to the log, because it names
  image digests, socket paths and directories of the host. It is the rule the
  adapters follow for driver text, applied to the other kind of driver.
- **Removal accepts "it was not there".** Its goal is a state rather than an
  event, so 404 is success, and retrying a half-finished removal works.

## What a container is created with

Only what the specification says (D80), plus two rules that belong to every
service rather than to a kind of one:

- a published port is bound to `127.0.0.1`, because a database somebody asked
  this server to start is not one they asked it to publish to the network;
- `RestartPolicy: unless-stopped`, so a service comes back with the machine
  and stays stopped when somebody stopped it.

There is a test that the only mount is the service's own named volume and that
`Binds` never appears: a bind mount is how the old application let a request
reach the host.

## How it was verified

The requests are asserted against `httpx.MockTransport`, which is what makes
"the body a container is created from" a thing a test can hold. That the
detection itself works was checked against the running backend container with
the socket mounted: `GET /services/templates` answers `available: true`, and
without the mount the same route answers with the reason.

## Decision

**D82. A runtime is asked, never assumed, and the offer says so.** The
statement, its consequences and the known deviations are in
[managed services](../../architecture/services.md).

## What is not here

A cache for the probe, a pinned API version, any bound on how many services a
person may start, and the threat model that would let this be switched on
outside local development. The last is the phase's own final item.
