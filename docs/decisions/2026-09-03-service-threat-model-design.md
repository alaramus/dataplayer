# What running services on the machine costs

## Goal

The seventh item of phase 4: threat-model socket access, project and container
naming, resource limits, network exposure and concurrent users, before any of
this is enabled outside local development.

A threat model that changes nothing is a wish. This one names five threats and
ends with four changes and one refusal.

## The thing to be honest about first

**A process that can reach the Docker socket owns the host.** Not "can start
containers": it can start one with the host's root filesystem mounted, or with
`--privileged`, and read or change anything on the machine. There is no
configuration of this application that makes that untrue, because the power is
the socket's rather than ours.

Everything below is therefore about limiting what *this application* does with
that power, and about who may ask it to. It is not a defence against somebody
who reaches the socket another way.

## The five, and what each one gets

### 1. Socket access

**Threat.** A defect anywhere in this application — a route that takes a
container name, a path that reaches the engine with a caller's string —
becomes host compromise rather than a bug.

**What is already true.** Nothing a request carries reaches the runtime: the
image, the command, every environment key, the volume and the data path come
from a template written in code (D80), and the only string a client sends is a
key from a closed set and a name that lands in this application's own
database. The client speaks a fixed set of Engine API calls:

| Purpose | Call |
| --- | --- |
| is anything there | `GET /version` |
| fetch an image | `POST /images/create` |
| make a volume | `POST /volumes/create` |
| make a container | `POST /containers/create` |
| start, stop, restart | `POST /containers/{name}/{verb}` |
| inspect, list | `GET /containers/{name}/json`, `GET /containers/json` |
| read output | `GET /containers/{name}/logs` |
| remove | `DELETE /containers/{name}`, `DELETE /volumes/{name}` |

That table is the point: a deployment that puts a filtering proxy in front of
the socket knows exactly which endpoints to allow, and nothing here needs the
ones that would matter most — `exec`, `commit`, `build`, or a create with
`Privileged` or `Binds`.

**What changes.** Nothing in code, and the default stays off
(`SERVICES_ENABLED=false`, socket mounted only in the development override).
This is the refusal: the item asked for a threat model *before* enabling it
outside local development, and the model's answer is that a deployment which
wants this must decide, deliberately, to give one process that power — behind
a filtering proxy if it can.

### 2. Naming

**Threat.** Names are predictable — `dataplayer-svc-<template>-<12 hex of the
service id>` — so a container of that name may exist without this application
having made it, whether by accident or on purpose. Removing it would then
destroy somebody else's container, and starting it would be starting something
unknown.

**What changes.** `remove` inspects first and refuses anything that does not
carry this application's own label. The labels were always what code matches
on (D80); this closes the one place where a name alone was enough to act.

Creation is already safe by the daemon's own rule: a name in use is a 409, and
this application's answer to that is a refusal rather than a takeover.

### 3. Resource limits

**Threat.** A container with no limits can take all of the machine's memory,
all of its processors, or all of its process table. A person asking for a
database is not asking for that, and a runaway one takes the application down
with it.

**What changes.** Every container is created with `Memory`, `NanoCpus` and
`PidsLimit`, from settings with modest defaults — 1 GiB, one processor, 512
processes. Written beside the restart policy rather than in a template,
because a template that could choose its own limits could choose none.

### 4. Network exposure

**Threat.** A database somebody asked this server to start, published on every
interface, is a database on the internet with a password in an environment
variable.

**What is already true.** Nothing is published: a service joins the configured
network and is reached by container name (D83). Where a port is published at
all the binding is `127.0.0.1`, so it is the machine's own, not the network's.
A server with no network configured offers no services rather than starting
unreachable ones.

**What changes.** Nothing. It was designed this way, and this is where it is
written down.

### 5. Concurrent users

**Threat.** Several people, or one person and a loop, start services until the
machine is full. Every service is a container, a volume and a share of the
memory.

**What changes.** A ceiling on how many services one person may hold at once,
from settings, defaulting to five. Everything counts, including a failed
service, because a failed one may still hold a container nobody has looked at.
The refusal names the number and says to remove one.

## What is deliberately not attempted

- **A shared installation is not made safe by this.** The ceiling bounds one
  person; nothing bounds the sum of everybody, and nothing prices a service.
- **No image is verified.** The registry pins tags, not digests, and nothing
  checks a signature.
- **Nothing isolates one person's services from another's.** They share a
  network, so a container of one user's can reach a container of another's.
  Per-user networks are the obvious next step and are not taken here.
- **The socket is not proxied for you.** The endpoint table says what a proxy
  must allow; configuring one is a deployment's work.

## Decision

**D86. Running containers is the machine's power, bounded by what this
application will ask for.** The statement, its consequences and the known
deviations are in [managed services](../architecture/services.md).
