# Managed services

A service this server starts on the machine it runs on, and the connector such
a service becomes. Read this before adding a template, changing what a service
is started with, or letting anything about a container come from a request.

Decisions here: D80, D82, D83, D84, D85, D86, D87, D88, D89, D90.

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
├── readiness.py   waiting until it answers, and filling it once it does
├── jobs.py        create, start, stop, restart, delete as job handlers
├── tools.py       a container run once for its exit code
├── backups.py     copying a database out and putting it back, as jobs
├── backup_routes.py  the backups of one person, and the two commands
└── routes.py      the templates, and the lifecycle
```

```
GET    /api/v1/services/templates
GET    /api/v1/services/unclaimed
DELETE /api/v1/services/unclaimed/{container_name}
POST   /api/v1/services/
GET    /api/v1/services/
GET    /api/v1/services/{service_id}
POST   /api/v1/services/{service_id}/start
POST   /api/v1/services/{service_id}/stop
POST   /api/v1/services/{service_id}/restart
POST   /api/v1/services/{service_id}/retry
GET    /api/v1/services/{service_id}/logs
GET    /api/v1/services/{service_id}/credentials
DELETE /api/v1/services/{service_id}
GET    /api/v1/backups/
GET    /api/v1/backups/offer
POST   /api/v1/backups/
POST   /api/v1/backups/restore
DELETE /api/v1/backups/{filename}
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
- **There are two templates.** PostgreSQL and Redis, which is what proves
  the registry is not one image with steps around it ([D85](#d85-the-second-service-is-what-proves-the-first-one-was-not-a-shape)).
- **What a person may name is a short list.** The role and the database, and
  only where the template opens them
  ([D88](#d88-two-ways-to-ask-for-a-service-and-neither-of-them-names-a-container));
  everything about the container stays the template's.

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
- **Where this application reaches a service is its container name on a
  shared network.** That is what a name resolves on, so a server with no
  network configured offers nothing: a service that could be started and not
  used is not an offer. A port on the host is a second thing with a different
  audience — the person who started it, in their own tools — and it is bound
  to the loopback address and numbered by the runtime
  ([D89](#d89-a-generated-password-is-shown-once-where-it-becomes-useful)).
- **How much a person is asked depends on which of the two ways they asked**
  (D88). The image, the command, the volume and the port number are the
  server's in both.
- **A service and its connection are both shown, because both are true.** The
  connection is how a database is used; the service is the container it lives
  in, and its row is the only place its life can be ended.

Known deviations:

- **A service cannot be stopped or started from the screen.** The routes are
  there and the jobs work; removal, retry, stopping a job and reading its
  output are drawn, and the two lifecycle commands are not.
- **Nothing bounds how long a create may hold a job.** How many services a
  person may hold and what each may take of the machine are answered by
  [D86](#d86-running-containers-is-the-machines-power-bounded-by-what-this-application-will-ask-for).
- **The readiness probe opens a connection per attempt** and keeps nothing, so
  a database that takes two minutes is asked a hundred and twenty times.
- **A service is reachable from this server only.** A person cannot point
  `psql` at it from their own machine.

Spec: [Starting a PostgreSQL and receiving a connection](../superpowers/specs/2026-09-03-service-pilot-design.md)

## D84. What goes wrong is a state somebody can act on

A lifecycle is only as good as what it does when a step fails, a person
presses twice, or somebody removes a container by hand. Each of those is
answered here, and the answers share one rule: nothing is guessed on the
person's behalf, and nothing is quietly undone.

- **Asking twice is asking once, when the caller says so.** A request may
  carry a `request_id`; a second request of this owner with that id answers
  with the service the first one made. Chosen by the client for the reason a
  run's id is (D64): only the caller knows that two requests are one
  intention. Without one, two requests are two services — because they may
  well be.
- **Retry means starting over, not carrying on.** A password is settled once
  per attempt and lives only in the connector that attempt would have saved,
  so a container left by a failed one has a password nobody knows. Creation
  therefore begins by taking away whatever an earlier attempt left, including
  the volume: the data in it is a database initialised with that unknown
  password. A first attempt finds nothing and skips the step.
- **A service that already has a connection is not retried.** That one is
  finished, and remaking it would destroy a database somebody is using; the
  answer names removal instead.
- **A job can be stopped, and what it had already done is left standing.**
  There is no `cancelling` state: a task stops at its next await. Undoing its
  work here would be this application guessing at what somebody wanted kept,
  so a cancelled create leaves a service to retry or remove — which is why
  removal is the way out of every state.
- **Stopping something that has already ended is not an error.** The caller
  asked for it to be over, and it is.
- **What this application believes and what the runtime reports are both
  shown.** A row says `running` while the container is `missing` when somebody
  removed it by hand; a server that could not ask says `unknown` rather than
  guessing. The whole point of the pair is that they can disagree, and one
  question to the daemon answers for every row rather than one per service.
- **A service's own output can be read**, bounded to the last few hundred
  lines. The daemon multiplexes two streams into one body with a header per
  chunk, and the header is stripped rather than shown. This application's own
  log is not a user's to read, and neither are the runtime's words about the
  machine.
- **A container this installation made that no row claims is findable**, by
  label rather than by name, and removable. It is an administrator's question
  and an administrator's route: what runs on the machine is not one user's
  business, and what turns up may be anybody's.
- **Deleting a connection never touches a container or a volume.** It deletes
  a row of this application, and the service it was made by keeps running with
  its data — which the confirmation says in so many words. That is the rule
  the roadmap asked for: a volume is not deleted by anything but an explicit
  removal of the service that owns it.
- **Removing a service leaves the connection behind.** It may be shared, it
  may be named in somebody's query history, and it is not that command's to
  destroy. It stops working, and its owner removes it when they choose.

Known deviations:

- **Cancellation reaches only the process that accepted the job.** Another
  process's job is refused with 409 rather than stopped, which is the same
  boundary D81 already records.
- **Retry is the only repair.** A container that exists and works but whose
  connector was never saved cannot be adopted — its password is gone — so it
  is taken away and made again.
- **Orphan discovery is a question, not a sweep.** Nothing runs on a timer;
  an administrator asks and decides.
- **A log tail is a request, not a stream.** There is no following along, and
  a service that prints faster than it is read loses the middle.
- **Nothing warns before a retry destroys the earlier attempt's data.** The
  button says so, and there is no second confirmation.
- **A removed service's connection is not marked broken.** It fails its next
  health check like any other connection that stopped answering.

Spec: [When starting one goes wrong](../superpowers/specs/2026-09-03-service-recovery-design.md)

## D85. The second service is what proves the first one was not a shape

A registry with one entry is a class with extra steps. Redis is the second,
and it was chosen by the roadmap because it is unlike PostgreSQL in exactly
the ways that matter: it takes its password on the command line, it has no
data directory to build, and this application cannot read what is in it.

- **A command may carry a credential.** The official Redis image has no
  environment variable for a password: it is told `redis-server --requirepass
  …`. So `command` is written as values rather than strings, resolved the way
  the environment is. A template that could only write constants there could
  not describe the image at all — and the alternative, letting the *client*
  supply a command, is what D80 exists to forbid.
- **A template may generate one credential and use no others.** Redis has no
  user and no database name; `credentials` holds a password and nothing else,
  and the slots a template never mentions are simply absent.
- **Redis is a source type of this application**, registered like any other.
  It arrived with the connection check as its only capability, and the catalog
  said exactly that — "This type only checks that it can reach the source" —
  because what a type can do is derived from its driver rather than listed
  beside it. When the key space arrived
  ([D91](sources/contract.md#d91-a-key-space-is-a-catalog-grouped-by-the-separator-its-names-already-use)),
  the same list grew in the same commit.
- **Its options are a discriminated union**, password or none, for the reason
  PostgreSQL's are (D16): one model with an optional password is a form that
  asks half its users for something to leave empty, and a `SecretStr | None`
  is not what D4's split recognises as a secret.
- **The `redis` client is imported by `adapters/redis/` and by nothing else**,
  the rule `psycopg` and the file-format libraries already follow, and it is
  enforced by a contract of its own.

Known deviations:

- **A Redis service's password is visible to anybody who can inspect the
  container**, because it is on the command line. The same person can read the
  volume the data is in, so the exposure is bounded by access to the runtime —
  which is the threat model's own subject.
- **A Redis service is not backed up.** `SupportsBackup` names a program that
  dumps a source, and this one names none: what Redis writes is a snapshot in
  a volume that goes with the service.

Spec: [A second service, and the first source that only connects](../superpowers/specs/2026-09-03-redis-pilot-design.md)

## D86. Running containers is the machine's power, bounded by what this application will ask for

A process that can reach the Docker socket owns the host: it can start a
container with the host's filesystem mounted, or a privileged one, and read or
change anything. No configuration of this application makes that untrue,
because the power belongs to the socket. So the question is not how to make it
safe — it is what this application will and will not ask for, and who may ask.

- **The set of calls is fixed and small.** Version, image pull, volume create,
  container create, start, stop, restart, inspect, list, logs, remove. Nothing
  here needs `exec`, `commit`, `build`, `Privileged` or `Binds`, which is what
  lets a deployment put a filtering proxy in front of the socket and know
  exactly what to allow. The list is in the spec, and it is the useful half of
  the threat model.
- **It stays off by default.** `SERVICES_ENABLED` is false and the socket is
  mounted only in the development override. Enabling it anywhere else is a
  deliberate decision to give one process that power, and this decision does
  not make it for anybody.
- **A container is removed only if this application made it.** Names are
  predictable, so a name is not proof; removal inspects first and refuses
  anything without this application's own label. Creation was already safe by
  the daemon's rule that a name in use is a conflict.
- **Every container is created with limits**: memory, processors and a process
  ceiling, from settings, with modest defaults. Beside the restart policy
  rather than in a template, because a template that could choose its own
  limits could choose none.
- **Nothing is published to the network.** A service joins the configured
  network and is reached by container name; a port published on the host is
  bound to `127.0.0.1`, so it is reachable from the machine this server runs
  on and from nowhere else. A server with no network configured offers nothing
  rather than starting something unreachable.
- **One person may hold only so many services.** A ceiling from settings,
  counting everything including failed ones, refused with the number and what
  to do about it. Not a quota system: a number that turns a loop somebody left
  running into a refusal rather than an outage.

Known deviations:

- **A shared installation is not made safe by this.** The ceiling bounds one
  person; nothing bounds everybody together, and nothing prices a service.
- **No image is verified.** Tags are pinned, digests are not, and no signature
  is checked.
- **Services of different people share a network**, so one person's container
  can reach another's. Per-user networks are the obvious next step.
- **The socket is not proxied for you.** The endpoint list says what a proxy
  must allow; setting one up is a deployment's work.
- **Nothing is audited.** Who started what, and when, is not recorded beyond
  the job rows.

Spec: [What running services on the machine costs](../superpowers/specs/2026-09-03-service-threat-model-design.md)

## D87. A program that is not a statement runs in a container of its own

`pg_dump` and `pg_restore` are programs. This application's image has neither,
and installing them would fix their version — a `pg_dump` older than the
server it is pointed at refuses to run, correctly. So the source is asked what
version it is, and the program runs in the image of that version.

- **The engine runs a program once**: create, start, wait, read what it
  printed, remove — the removal in a `finally`, because a container kept for
  its exit code is one nobody will look at again.
- **The source says what to run.** `SupportsBackup` answers with an image, an
  argv and an environment; a source that cannot say does not implement it and
  the route answers 501, the rule every capability follows.
- **The password is in the environment, never in the arguments.** Arguments
  are visible to anything that can list processes, and `PGPASSWORD` is what
  libpq documents for this.
- **A backup is a file in the owner's personal storage**, written there by the
  program itself: the storage is a named volume, so the container mounts it
  and writes where the file source will list it. No copying out of a
  container, no streaming through the application, no path on the host. A
  deployment that has not said which volume gets no offer, because a dump
  written inside a container that is then thrown away is worse than a refusal.
- **Both are jobs**, with the same durable state, named steps and socket as
  everything else the server owns (D81) — a dump of anything real is minutes.
- **A restore says that it is meant.** `--clean` drops every object in the
  dump from the target first, so the request carries `understood` and one
  without it is refused. The handler does not check again: a job carries out
  what was decided.
- **Which backup travels in the job's `parameters`**, a small column for a
  kind of work that needs more than a subject. Never a secret: a job row is
  not encrypted.
- **A backup is named, not pathed.** The name is matched against the files in
  one folder, so nothing resolves a path a client wrote — D8's containment
  rule, kept by having nothing to contain. Deleting one is that same match and
  then an `unlink`: no job, because removing a file is not minutes of work.
- **Which sources this is offered for is read off the driver.** `SupportsBackup`
  puts a `backup` capability on the type, the button is greyed out where the
  type does not declare it, and pressing it anyway answers 501. Two questions,
  not one: whether the machine can run the program at all is the offer, and
  whether this source can name one is the capability.
- **Backing up is the owner's.** Copying a database out whole is every row,
  every schema and every function in one file the caller keeps, which is more
  than a read.

Known deviations:

- **Only PostgreSQL.** Redis has no equivalent here, and the file source's
  answer to "back this up" is that it is already files. Both say so by not
  declaring the capability, which is what greys the button out.
- **No schedule and no retention.** A backup happens when somebody presses the
  button, and stays until they delete it.
- **A dump is not verified.** Nothing reads it back to check it can be
  restored, and a truncated one is found out at the moment it matters.
- **A restore may be pointed only at the connection the screen offers it
  for.** Nothing in the model forbids restoring into another connection of the
  same kind; nothing offers it either.
- **The program's own last line is passed on when it fails.** It is the
  program's words about a database rather than the daemon's about the machine,
  and it may still name a host or a database.

Spec: [Copying a database out, and putting it back](../superpowers/specs/2026-09-03-backup-and-restore-design.md)
\n
## D88. Two ways to ask for a service, and neither of them names a container

One button that starts a database is a demonstration; a form with eight fields
is a configuration screen. Both are wanted, and they are not the same request,
so they are two shapes rather than one shape with everything optional.

- **An automatic start carries nothing at all.** Not the name either: somebody
  who has not been asked for one has not got one in mind, so the server calls
  it what it is and which one of them it is — "PostgreSQL 1", "PostgreSQL 2".
  It publishes a port and fills the database, because a demonstration nobody
  can connect to and which holds nothing demonstrates nothing.
- **A chosen start names what is a person's to decide**: what the connection
  is called, the role and the database to create inside it, whether it is
  reachable from the machine, and whether to put a sample schema in it. That
  is the whole list.
- **Which credentials may be named is the template's to say.** `choosable` is
  a closed set per template, and a value for a slot it did not open is refused
  rather than dropped — a Redis server has no role, and somebody who typed one
  should be told so. PostgreSQL opens the role and the database; Redis opens
  nothing.
- **The password is never on that list.** A chosen one would have to be
  written down between the request and the job that uses it, and the only
  encrypted home for a service's password is the connector it becomes
  ([D4](backend.md)). It is made up by the server in both modes.
- **A request is a discriminated union**, so "automatic" is a thing a client
  says rather than a thing it fails to say, and both shapes forbid unknown
  keys: a request that names an image, a command, a volume or a port number
  does not validate. That is D80 stated a second time, where a client can
  reach.
- **The names a person may write are letters, digits and underscores.** They
  become an environment variable in a container specification and a role in
  somebody's server, and neither takes a quote.

Known deviations:

- **The automatic name is not unique across a rename.** It avoids the names a
  person's services already have at the moment it is chosen; renaming a
  connection afterwards can make two of them agree.
- **A chosen start cannot ask for a password.** The reason is above, and the
  consequence is that somebody automating this cannot decide credentials in
  advance.
- **Sample data is all or nothing.** One schema, the project's own, and no
  choice of what goes in.

Spec: [Two ways to start a service, and what comes back](../superpowers/specs/2026-09-03-service-start-modes-design.md)

## D89. A generated password is shown once, where it becomes useful

A service is used through the connection it became, so this application never
needs to say its password out loud. A person who started a database usually
wants to open it in their own tools as well, and the password is one they were
never asked for — so it is shown, once, at the moment the service is ready.

- **Once, and the row remembers.** `credentials_shown_at` is stamped when the
  answer is given, and asking again is refused rather than answered. The
  window says so before it shows anything, because a warning under something
  the reader has already closed is not a warning.
- **It is read out of the connector**, where the job encrypted it (D4). There
  is no second home for it, and nothing is written down to make this route
  possible.
- **The address is the one somebody else could use**: `127.0.0.1` and the port
  the runtime picked, not the container name the connector holds — that
  resolves only on the network this server is on. A service started without a
  port says why there is no address instead of showing one that would fail.
- **The parts, and then the whole thing as one line.** A form asks for a host
  and a port; a terminal takes a URL. The line is written by the source type
  that owns the grammar (D15), never joined together by the screen, and it is
  the only place in this application where a password is put into a string
  anybody sees.
- **The port is the runtime's answer.** The request says only whether to
  publish; Docker picks a free port and the create job reads it back off the
  container. This application never binds a socket to find out what is free
  and then races whoever took it in between.
- **Automatic starts open the window by themselves**, and only they: somebody
  who filled in a form knows what they asked for, and somebody who pressed one
  button has been told nothing yet. Until it has been shown, the services
  window offers it.

Known deviations:

- **A closed window loses the password.** There is no second reveal; the
  service can be started again, which makes a new one.
- **The reveal is not audited.** That it happened is a stamp on the row and
  nothing more.
- **A published port is on the loopback only**, so "from outside" means from
  the machine this server runs on. Reaching it from another machine is that
  machine's tunnel to arrange.

Spec: [Two ways to start a service, and what comes back](../superpowers/specs/2026-09-03-service-start-modes-design.md)

## D90. An empty database demonstrates nothing, so an automatic start fills one

A server this application starts is empty: one schema, no rows, and every
screen the application is made of saying "nothing here". The project already
has a schema worth exploring — the one it develops against, with enums,
domains, composite types, generated columns, arrays, ranges, partitions and a
few hundred rows — so that is what goes in.

- **The same two files, not a copy of them.** They moved out of the repository
  root and into `adapters/postgres/sample_data/`, beside the driver that runs
  them: the development fixture and the sample data of a started service are
  now one thing, and a second copy of a three-hundred-line schema is a second
  copy that drifts.
- **It is a capability, read off the driver.** `SupportsSampleData` is what
  makes the offer appear on a template; a source that cannot be filled is
  skipped rather than refused, because the person asked for a database and
  this is the part of the answer that source cannot give.
- **Nothing a client sends reaches a statement.** The script is this
  repository's own text, run against a server this application has just
  started. Running somebody's script against somebody's server is what the
  query console is for, with the unlock and the confirmation it carries.
- **The step is reached, not announced.** A service started without sample
  data never shows a step in which nothing happened.
- **A failure to fill fails the creation.** The database is up and usable, but
  a person who asked for something to look at and received an empty server
  would otherwise have to work out why themselves.

Known deviations:

- **What goes in differs by source, and so does how much.** PostgreSQL gets
  the schema this project develops against; Redis gets a hundred and ten keys
  across eight namespaces, covering every type it has, some with an expiry and
  some without. Both are written out rather than generated, so a demonstration
  made twice is the same demonstration.
- **The schema is the development fixture.** It was written to exercise this
  application's own type handling rather than to tell a story, so it is a
  demonstration of breadth rather than of a business.
- **It ships in the image.** Sample data used to be mounted only into the
  development prestart container; it is part of the application now, because
  starting a filled database is something the application does.

Spec: [Two ways to start a service, and what comes back](../superpowers/specs/2026-09-03-service-start-modes-design.md)
