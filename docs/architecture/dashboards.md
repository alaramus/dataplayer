# Dashboards

Metrics from agents and connections, the store they are kept in, the process
that collects them, and the card that draws them. Read this before changing
anything that ingests, stores or shows a metric.

Decisions here: D125, D126, D127, D128, D129, D130.

**Implementation status:** designed on 2026-09-13; nothing is implemented.
Slices DB1–DB6 are in the spec. Until a slice lands, a decision below states
the contract that slice must meet, not what the application does.

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

- D83 does not hold for this one service.
- There is one store per installation.

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
