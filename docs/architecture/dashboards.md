# Dashboards

Metrics from agents and connections, the store they are kept in, the process
that collects them, and the card that draws them. Read this before changing
anything that ingests, stores or shows a metric.

Decisions here: D125, D126, D127, D128, D129, D130.

**Implementation status:** DB1 — the store, its setup, collection, agents,
catalog and history — is implemented, without a screen. DB2–DB6 are in the
spec; D125 and the dashboard half of D129 state what those slices must meet,
not what the application does.

## What exists today

A superuser sets the store up through the API: starts the `timescaledb`
template or connects an existing database. A person registers agents and
receives the key each reports under. The `metrics` process receives their
packets and writes samples and process snapshots; the web process answers the
catalog of what a person's agents reported and the history of chosen series,
raw or bucketed. Development starts an agent in the `monitor-agent` Compose
profile under `METRICS_DEV_AGENT_KEY`, which prestart registers for the first
superuser.

```
backend/app/metrics/
├── packets.py      an agent packet as samples and a process snapshot; pure
├── units.py        the unit of a field
├── counters.py     growing counters as increments
├── keys.py         issuing, fingerprinting and sealing agent keys
├── models.py       MetricsAgent, MetricsStoreSetting, and the API models
├── crud.py         application-database access
├── migrations.py   the store's numbered schema
├── store.py        the store: series ids, writes, catalog, history, purge
├── holder.py       the web process's handle on the store
├── history.py      raw or which bucket width; pure
├── access.py       who may read a series
├── setup.py        store status, starting it, connecting one
├── jobs.py         the service create job, delivering a store setting
├── collector.py    the metrics process
└── routes.py       /metrics
```

```
GET    /api/v1/metrics/store
POST   /api/v1/metrics/store/start          superuser
POST   /api/v1/metrics/store/connect        superuser
GET    /api/v1/metrics/agents
POST   /api/v1/metrics/agents
PATCH  /api/v1/metrics/agents/{agent_id}
DELETE /api/v1/metrics/agents/{agent_id}
GET    /api/v1/metrics/agents/{agent_id}/key
POST   /api/v1/metrics/agents/{agent_id}/key
POST   /api/v1/metrics/agents/{agent_id}/purge
GET    /api/v1/metrics/catalog
POST   /api/v1/metrics/history
```

The store tests need a TimescaleDB whose role may create databases, named by
`TEST_METRICS_STORE_URL`; without it they are skipped. The compatibility source
`v2_30_pg18` serves locally — at `127.0.0.1`, because `localhost` on Windows
tries IPv6 first and waits out the connect timeout on every connection.

## D125. Dashboards are a space of their own

A **Data | Dashboards** switch at the foot of the screen, before the library of
queries, replaces the whole workspace with one dashboards card: dashboards and
sources on the left, a 12-column grid of widgets on the right.

- The data workspace is hidden, not closed: panels, their state and an open
  transaction (D66) survive the switch.
- A panel of the hidden space is not on screen for D67's pause rule.
- Anything opened into the data workspace switches back to it first.
- Floating windows and the taskbar belong to both spaces.
- The chosen space is remembered per browser.
- Agents and adding widgets are floating windows (D14); a widget's own settings
  are edited on the widget.

Rejected: a route of its own, which unmounts the panels; a panel in the work
column, which keeps the columns the user wants gone.

Spec: [Dashboards](../decisions/2026-09-13-dashboards-design.md)

## D126. The metrics store is a TimescaleDB that belongs to the installation

Samples live in a TimescaleDB of their own, not in the application database.
Chunking, retention, compression and continuous aggregates are the extension's.

- **Not a connection.** One installation setting holds the address, with the
  credentials encrypted under the connector key (D4). No catalog, console,
  share or list of connections reaches it. A store owned as a superuser's
  connector would give that superuser every person's metrics (D34) and would
  break every dashboard when that connector or account went.
- **Set up on first entry by a superuser**, one of two ways: start the
  `timescaledb` template, whose create job writes the store setting instead of
  a connector, publishes no port and does not count against D86's ceiling; or
  connect an existing database, accepted when the check succeeds and the
  extension is installed or installable (D120). Anybody else is told an
  administrator has not set Dashboards up.
- **Its schema is not Alembic's.** Numbered migrations in the metrics module, a
  version table in the store, applied on connect and on start of the metrics
  process under an advisory lock. Continuous aggregates are created outside a
  transaction.
- **Retention is a policy.** Raw points 30 days and process snapshots 14 days
  until continuous aggregates arrive; history is bucketed on read to the number
  of points asked for, raw as `[ts, value]`, aggregated as `[ts, avg, min, max]`.
- Agents and dashboards stay in the application database with their owners.

Known deviations:

- D83 does not hold for this one service. `ManagedService.purpose` says so,
  and every person-scoped query of the services module reads connections only.
- There is one store per installation.
- **The store's service row belongs to the superuser who started it.** Deleting
  that account deletes the row; the container keeps running and serving, but
  shows among the containers no row claims, where an administrator could
  remove it.
- **A store that stops answering is found out when somebody asks.** The status
  says `unreachable`; nothing watches it in between.

Spec: [Dashboards](../decisions/2026-09-13-dashboards-design.md)

## D127. Metrics are collected by one process of their own

A `metrics` service from the backend image receives UDP and, later, polls
connections. It is one process, holding the port and every counter's previous
sample. The web process reads the store and never writes points.

- Not inside the web application, although that is one process too (D124): its
  reloads and deploys would drop packets and counter state, the stream would
  share the event loop with every request, and a port bound in the lifespan
  would be one more thing scaling the web process out has to answer.
- It reads the store setting from the application database and waits while
  there is none.
- It publishes `METRICS_UDP_PORT` (9999/udp) and joins `SERVICE_NETWORK`.
- The receive loop never awaits; a bounded queue drops and counts. Points are
  written in batches.
- A packet whose key no agent holds is dropped before any write.
- Live display reads newer points from the store on a short interval; no
  channel between processes.

Known deviations:

- **The process re-resolves every series every fifteen seconds.** A purge in
  the web process deletes series rows the process still holds ids of; points
  written under such an id in that window are lost. Re-resolving is an upsert
  per series per interval.
- **A batch that fails to write is dropped**, and counted in the log line the
  process writes every minute.

Spec: [Dashboards](../decisions/2026-09-13-dashboards-design.md)

## D128. A series belongs to a typed source, and access follows its owner

A source is an agent plus the host its packet named, or a connection. The
identity of a series is `(source, metric, field, label)`. No host name is
invented for a connection.

- An agent's series are its owner's; a connection's series follow D33; a
  superuser is not special (D34).
- The agent key is issued by the server, stored hashed for lookup and encrypted
  for showing to the owner, and rotatable. It is the only proof a UDP packet
  carries.
- The agents window gives a Compose snippet with the address, the key, a fixed
  `hostname` and no `iftop` action.

Known deviation: **deleting an agent keeps its samples** until retention
removes them; purging is a separate command. Its series stay in the store,
readable by nobody, because nobody owns the agent any more.

Spec: [Dashboards](../decisions/2026-09-13-dashboards-design.md)

## D129. A dashboard is a stored layout of typed widgets, read through one access check

A dashboard has an owner, a name, options and widgets. A widget is a
discriminated union by type, identified by uuid, naming series ids rather than
names. Limits: 12 columns, 20 widgets, 200 series per history request, titles of
120 characters, ranges from 60 s to one year.

- Every read of points — history and live — asks one question: may this user
  read these series, directly or through this dashboard.
- Saving refuses a widget naming a series the saver cannot read.
- A grant on a dashboard (D33's levels) will let its holder read exactly the
  series on it; until sharing lands the answer is the owner alone.

Spec: [Dashboards](../decisions/2026-09-13-dashboards-design.md)

## D130. What an agent sends is interpreted in one place, and a restart is read from the data

One module turns a packet into points and process snapshots: text numbers,
echoed header rows, label fields, positional arrays, tables summarised, growing
counters stored as increments. A host whose `uptime` goes down has restarted;
repeated restarts become an attention item (D115).

Known trap: `sys_monitor_agent` 1.14.0 with the `iftop` action crashes with
SIGSEGV in a container without traffic and restarts about every 33 seconds,
sending one set of samples per restart.

Spec: [Dashboards](../decisions/2026-09-13-dashboards-design.md)
