# Managed services

A service this server starts on the machine it runs on, and the connector such
a service becomes. Read this before adding a template, changing what a service
is started with, or letting anything about a container come from a request.

Decisions here: D80, D82, D83.

## What exists today

A closed registry of approved templates, the plan one of them turns into, the
five things that can happen to a service — each an [owned job](jobs.md) — the
routes that ask for them, and a client for the Docker Engine API. Whether this
installation runs services at all is a setting; whether a runtime answers is
asked of it.

```
backend/app/services/
├── templates.py   the closed set: what may run, and what it becomes
├── plan.py        one service fully decided — names, credentials, container
├── models.py      ManagedService, and what a client reads
├── crud.py        database access only
├── engine.py      what a container runtime must do, and a server without one
├── readiness.py   waiting until the source itself answers
├── docker.py      the Docker Engine API, over the socket this server has
├── jobs.py        create, start, stop, restart, delete as job handlers
└── routes.py      the templates, and the lifecycle
```

```
GET    /api/v1/services/templates
POST   /api/v1/services/
GET    /api/v1/services/
GET    /api/v1/services/{service_id}
POST   /api/v1/services/{service_id}/start
POST   /api/v1/services/{service_id}/stop
POST   /api/v1/services/{service_id}/restart
DELETE /api/v1/services/{service_id}
```

## D80. An approved service is written in code, and a client names one

The old application let the connector form describe the container. Ticking
"Deploy in Docker" sent `options.docker`, and `compose_file_creater.py` read
`image`, `commands`, `main_port`, `data_path`, `container_config_path` and
`host_config_path` straight out of it, rendered a Mako template with them and
ran the result through a `docker compose` command line built with an f-string.
A client that could name an image could run any image; one that could name a
host path could mount any directory into it.

- **A template is a value in `templates.py`**, and `SERVICE_TEMPLATES` is a
  tuple rather than a registry something can add to at runtime. There is
  nothing to implement for a service — unlike an adapter type, which registers
  a driver — so a template is data, and data a test can pin down.
- **A client sends a key and nothing else.** `template_for` is the one place a
  string becomes a template, and a key that names none does not resolve.
- **The image is pinned to a version.** `latest` is a statement about the day
  somebody presses the button rather than about what will run.
- **Every environment key is in the template**, and every value is either a
  constant written there or a slot the server settled. A key that is not
  declared is not passed.
- **What may stand where is a type, not a check.** A credential slot — user,
  password, database — belongs to one service and is settled before it starts;
  a placement slot — host, port — is settled when the service is put
  somewhere. The environment accepts only the first kind, so a container
  cannot ask for a port that nothing has assigned yet, and mypy is what says
  so.
- **The password is made here**, once per service, from `secrets` over letters
  and digits. The old frontend generated it in the browser. A template cannot
  choose its own alphabet, because a template that could would eventually
  choose a weak one.
- **Nothing names a path on the host.** A service gets one named volume,
  mounted where the image keeps its data; the data path is the image's
  business and is stated rather than guessed.
- **Names and labels are the server's.** A container is
  `dataplayer-svc-<template>-<service id>` and its volume is that plus `-data`,
  so what one installation made is visible in `docker ps`; the labels
  `dataplayer.service`, `dataplayer.template` and `dataplayer.owner` are what
  code matches on, because a name is for people to read and may be changed.
- **A plan holds the credentials it started the container with**, and the
  connector is filled from the same plan. The old application read the two out
  of different places, and could start a container with one password while
  saving a connector that held another.
- **The connector a service becomes goes through the adapter's own options
  model**, so it is validated exactly as one somebody typed, and the password
  lands in the encrypted blob by [D4](backend.md) without anything being told
  it is a secret.
- **Neither the plan nor the container spec has a readable `repr`.** One
  traceback with a spec in a local variable would put a password in a log for
  good.

Known deviations:

- **An image is pinned by tag, not by digest.** `postgres:18` is a moving
  target within its major version. A digest would be exact; keeping digests
  current is its own maintenance, and the tag is what the project's own
  `compose.yml` uses.
- **There is one template.** PostgreSQL is the pilot the roadmap names, and
  Redis arrives with its own item once the lifecycle is right.
- **A person cannot choose the database or the user.** Both are constants of
  the template. Letting them be typed would be a value from a client in an
  environment variable, which is a smaller thing than an image but still not
  this slice's to allow.

Spec: [Approved service templates](../superpowers/specs/2026-09-02-service-templates-design.md)

## D82. A runtime is asked, never assumed, and the offer says so

Whether a server can start containers is not a property of the code: it is a
property of the machine, of what the deployment allows, and of a daemon that
can go away while the server runs. So it is asked, and the answer is part of
the offer rather than a surprise at the moment somebody presses the button.

- **Services are off unless a deployment says otherwise.** `SERVICES_ENABLED`
  defaults to false, because a process that can reach a container runtime can
  do to the host whatever that runtime can. The socket is mounted in
  `compose.override.yml` — development only — and threat-modelling it for
  anywhere else is the last item of the phase.
- **The two reasons are different sentences.** "Managed services are switched
  off on this server" is something an administrator can change; "This server
  cannot reach a container runtime" is something that may be a daemon that is
  down. Telling them apart is the whole value of the answer.
- **Availability is asked when somebody asks**, not decided at startup. A
  probe held to two seconds, and one that never raises: not reaching a daemon
  is an answer, not a failure.
- **Every template says whether it could be started now**, and why not when it
  could not. A screen that offers what will be refused is a screen that lies.
- **Asking for a service without a runtime is refused before a row exists.** A
  job would fail with the same sentence, but a service row and a failed job
  are a mess left behind by a question that could have been answered. The job
  is still the authority if the runtime goes away in between — the check is a
  moment, and only the work is a fact.
- **The client is one module over httpx.** The Engine API is HTTP and httpx
  speaks it over a Unix socket, so a container runtime needs no SDK: `docker.py`
  holds the requests this application actually makes and nothing else. The old
  application shelled out to `docker compose` with an f-string command line.
- **The daemon's words never cross.** Its status codes become this
  repository's own sentences and its message goes to the log, because it names
  image digests, socket paths and directories of the host — the rule the
  adapters follow for driver text, applied to the other kind of driver.
- **A pull reports failure inside a successful answer.** The daemon returns
  200 and streams what it is doing, so the stream is read to the end: that is
  both how the pull completes and how a failure is noticed.
- **What is created is bounded by the specification.** One named volume and no
  bind mount; a published port bound to `127.0.0.1` rather than to every
  interface, because a database somebody asked this server to start is not one
  they asked it to publish; and `unless-stopped`, so a service comes back with
  the machine but stays stopped when somebody stopped it.
- **Removal accepts "it was not there".** It is the one command whose goal is
  a state rather than an event, and a person retrying a half-finished removal
  must not be told off for the half that worked.

Known deviations:

- **The probe is not cached.** Every listing asks the daemon, and a wedged one
  costs two seconds per request.
- **The API version is not pinned.** The client uses the unversioned paths and
  gets whatever the daemon serves. A daemon far newer than this code could
  change a field it reads.
- **Only Docker is tested.** Podman's socket serves the same API and would
  probably work; nothing here has tried it.
- **Nothing bounds how many services one person may start**, or how much of
  the machine they may take. Both belong with the threat model.

Spec: [Detecting a container runtime](../superpowers/specs/2026-09-02-runtime-detection-design.md)

## D83. A ready service is an ordinary connection, and its credentials live there

The point of the whole phase, and the shape that makes it safe: a person asks
for a database, and what they receive is a connector like any other — the same
table, the same validation, the same encryption, the same screens. Nothing
downstream can tell where it came from, which is what stops a started service
becoming a second kind of connection with rules of its own.

- **The connector is filled from the same plan the container was started
  with.** One `settle_credentials` per service, one plan, and both the
  environment and the options read from it. The old application read them from
  two places and could save a connector that did not match its own container.
- **It goes through the ordinary path**: the adapter's own options model
  validates it and [D4](backend.md)'s schema split encrypts what is declared
  `SecretStr`. Nothing was told that a password is a secret.
- **A service row holds no credentials.** The connector is their one home. A
  creation that fails before that step leaves a container nobody can use, so
  the service is marked failed and can be removed — which is why removal is
  the way out of every state.
- **Ready means the source answered**, not that a container is running. The
  create job asks the adapter's own connection check, once a second, until the
  template's timeout; PostgreSQL initialises its data directory on first start
  and the port answers before the server does. The probe is a protocol, like
  the engine, so a job can be exercised without a database to wait for.
- **Where a service is reached from is its container name on a shared
  network.** That is what a name resolves on, so a server with no network
  configured offers nothing: a service that could be started and not used is
  not an offer. Nothing is published on the host — opening a port on the
  machine is a separate decision, and it belongs with the threat model.
- **The one thing a person is asked is what to call it.** The image, the port,
  the user, the database and the password are the server's (D80); a name is
  the only part of it they know better, and a second database called
  "PostgreSQL" is a row nobody can tell from the first.
- **A service and its connection are both shown, because both are true.** The
  connection is how a database is used; the service is the container it lives
  in, and its row is the only place its life can be ended.

Known deviations:

- **Removing a service leaves its connection behind.** It stops working, and
  nothing says so beyond the health check going red. Deleting a connector,
  meanwhile, leaves the container running. Both are the deletion semantics the
  next item of the phase owes, together with the rule that deleting a
  connector must not silently delete a volume.
- **A service cannot be stopped or started from the screen.** The routes are
  there and the jobs work; only removal is drawn.
- **Nothing bounds how many services a person may start**, how much of the
  machine they may take, or how long a create may hold a job.
- **The readiness probe opens a connection per attempt** and keeps nothing, so
  a database that takes two minutes is asked a hundred and twenty times.
- **A service is reachable from this server only.** A person cannot point
  `psql` at it from their own machine.

Spec: [Starting a PostgreSQL and receiving a connection](../superpowers/specs/2026-09-03-service-pilot-design.md)
