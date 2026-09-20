# The container runtime

Whether this server can start containers at all, what it asks of the daemon,
and what giving one process that power costs. What a managed service is, and
what it becomes, is in [services.md](services.md).

Decisions here: D82, D86.

```
backend/app/services/
├── engine.py   what a container runtime must do, and a server without one
└── docker.py   the Docker Engine API, over the socket this server has
```

## D82. A runtime is asked, never assumed, and the offer says so

Whether a server can start containers is a property of the machine, of what the
deployment allows, and of a daemon that can go away while the server runs. So it
is asked, and the answer is part of the offer rather than a surprise at the
moment somebody presses the button.

- **Services are off unless a deployment says otherwise.** `SERVICES_ENABLED`
  defaults to false, because a process that can reach a container runtime can do
  to the host whatever that runtime can. The socket is mounted in
  `compose.override.yml` — development only — and threat-modelling it for anywhere
  else is the last item of the phase.
- **The two reasons are different sentences.** "Managed services are switched off
  on this server" is something an administrator can change; "This server cannot
  reach a container runtime" may be a daemon that is down. Telling them apart is
  the whole value of the answer.
- **Availability is asked when somebody asks**, not decided at startup. A probe
  held to two seconds, and one that never raises: not reaching a daemon is an
  answer, not a failure.
- **Every template says whether it could be started now**, and why not when it
  could not. A screen that offers what will be refused is a screen that lies.
- **Asking for a service without a runtime is refused before a row exists.** A job
  would fail with the same sentence, but a service row and a failed job are a mess
  left behind by a question that could have been answered. The job is still the
  authority if the runtime goes away in between — the check is a moment, and only
  the work is a fact.
- **The client is one module over httpx.** The Engine API is HTTP and httpx speaks
  it over a Unix socket, so a container runtime needs no SDK: `docker.py` holds the
  requests this application actually makes and nothing else.
- **The daemon's words never cross.** Its status codes become this repository's own
  sentences and its message goes to the log, because it names image digests, socket
  paths and directories of the host — the rule the adapters follow for driver text,
  applied to the other kind of driver.
- **A pull reports failure inside a successful answer.** The daemon returns 200 and
  streams what it is doing, so the stream is read to the end: that is both how the
  pull completes and how a failure is noticed.
- **What is created is bounded by the specification.** One named volume and no bind
  mount; a published port bound to `127.0.0.1` rather than to every interface,
  because a database somebody asked this server to start is not one they asked it
  to publish; and `unless-stopped`, so a service comes back with the machine but
  stays stopped when somebody stopped it.
- **Removal accepts "it was not there".** It is the one command whose goal is a
  state rather than an event, and a person retrying a half-finished removal must
  not be told off for the half that worked.

Known deviations:

- **The probe is not cached.** Every listing asks the daemon, and a wedged one
  costs two seconds per request.
- **The API version is not pinned.** The client uses the unversioned paths and gets
  whatever the daemon serves. A daemon far newer than this code could change a
  field it reads.
- **Only Docker is tested.** Podman's socket serves the same API and would probably
  work; nothing here has tried it.

Spec: [Detecting a container runtime](../decisions/2026-09-02-runtime-detection-design.md)

## D86. Running containers is the machine's power, bounded by what this application will ask for

A process that can reach the Docker socket owns the host: it can start a
container with the host's filesystem mounted, or a privileged one, and read or
change anything. No configuration of this application makes that untrue, because
the power belongs to the socket. So the question is what this application will
and will not ask for, and who may ask.

- **The set of calls is fixed and small.** Version, image pull, volume create,
  container create, start, stop, restart, inspect, list, logs, remove. Nothing here
  needs `exec`, `commit`, `build`, `Privileged` or `Binds`, which is what lets a
  deployment put a filtering proxy in front of the socket and know exactly what to
  allow. The list is in the spec, and it is the useful half of the threat model.
- **It stays off by default.** `SERVICES_ENABLED` is false and the socket is
  mounted only in the development override. Enabling it anywhere else is a
  deliberate decision to give one process that power, and this decision does not
  make it for anybody.
- **A container is removed only if this application made it.** Names are
  predictable, so a name is not proof; removal inspects first and refuses anything
  without this application's own label. Creation was already safe by the daemon's
  rule that a name in use is a conflict.
- **Every container is created with limits**: memory, processors and a process
  ceiling, from settings, with modest defaults. Beside the restart policy rather
  than in a template, because a template that could choose its own limits could
  choose none.
- **Nothing is published to the network.** A service joins the configured network
  and is reached by container name; a port published on the host is bound to
  `127.0.0.1`, so it is reachable from the machine this server runs on and from
  nowhere else. A server with no network configured offers nothing rather than
  starting something unreachable.
- **One person may hold only so many services.** A ceiling from settings, counting
  everything including failed ones, refused with the number and what to do about
  it. Not a quota system: a number that turns a loop somebody left running into a
  refusal rather than an outage.

Known deviations:

- **A shared installation is not made safe by this.** The ceiling bounds one
  person; nothing bounds everybody together, and nothing prices a service.
- **No image is verified.** Tags are pinned, digests are not, and no signature is
  checked.
- **Services of different people share a network**, so one person's container can
  reach another's. Per-user networks are the obvious next step.
- **The socket is not proxied for you.** The endpoint list says what a proxy must
  allow; setting one up is a deployment's work.
- **Nothing is audited.** Who started what, and when, is not recorded beyond the
  job rows.

Spec: [What running services on the machine costs](../decisions/2026-09-03-service-threat-model-design.md)
