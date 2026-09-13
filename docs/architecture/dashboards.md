# Dashboards

Metrics from agents and connections, the store they are kept in, the process
that collects them, and the card that draws them. Read this before changing
anything that ingests, stores or shows a metric.

Decisions here: D125, D126, D127, D128, D129, D130.

**Implementation status:** DB1 — the store, its setup, collection, agents,
catalog and history —, DB2 — the screen, dashboards, widgets, the agents window
—, DB3 — live points, process tables, ready-made layouts, a widget in a window
— and DB4 — connections reporting about themselves — are implemented. DB5 and
DB6 are in the spec; rollups, restart notices and sharing are not there yet.

## What exists today

**Data | Dashboards** at the foot of the screen covers the workspace with the
dashboards card. Before a store exists the card offers a superuser to start
TimescaleDB or connect an existing one, and tells anybody else that an
administrator sets it up. With a store it lists the person's dashboards and the
sources their agents reported; a dashboard is a 12-column grid of charts and
tiles, widgets are added by ticking series, moved by their header, resized by
their corner, renamed in place and expanded to fill the grid, and the whole is
saved a moment after the last change. The agents window registers an agent and
shows its key and the Compose file to start it with.

Points an agent sends appear on open charts and tiles within a couple of
seconds, without the dashboard re-reading anything. A host that sends its
process table has a `processes` leaf in the tree, which becomes a table sorted
by CPU, memory or PID. Selecting a host in the Add window offers its ready-made
layouts — today one, *Linux host* — filled with what that host reports, and
placed under what the dashboard already holds. Any widget opens in a floating
window, which stays when the screen is switched back to Data.

A PostgreSQL or Redis connection reports about itself once its owner switches
reporting on in the Sources window, choosing how often. Its series sit beside the
agents in the tree under the connection's own name, anybody the connection is
shared with can draw them, and selecting it offers the layout its type declares:
*PostgreSQL database* or *Redis server*. Counters of a connection are drawn as
rates per second.

A person registers agents and receives the key each reports under. The `metrics` process receives their
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
├── dashboards.py   Dashboard, its widget union and limits
├── presets.py      ready-made layouts and resolving them against a host
├── live.py         the `metrics.points` topic
├── poller.py       connections polled for metrics, in the metrics process
└── routes.py       /metrics

backend/app/adapters/
├── metrics.py            SupportsMetrics, a sample, a recipe and a layout
├── postgres/metrics.py   pg_stat_database and pg_stat_activity; its layout
└── redis/metrics.py      INFO; its layout

frontend/src/
├── stores/space.ts               which space fills the screen
├── shared/workspace/WorkspaceRoot.vue
│                                 `covered` and the `cover` slot: sections
│                                 not drawn, panels parked alive
└── features/dashboards/
    ├── api.ts                    vue-query for everything above
    ├── gridLayout.ts             grid arithmetic; pure
    ├── dashboardModel.ts         changes to a dashboard's content; pure
    ├── widgetSpecs.ts, catalog.ts
    │                             ticked series into widgets; the catalog as
    │                             index and tree; pure
    ├── seriesFormat.ts, chartOption.ts, statReading.ts, setupStage.ts,
    │   agentSnippet.ts           what is drawn and said; pure
    ├── livePoints.ts             socket points onto a history; pure
    ├── DashboardsSpace.vue       the card
    ├── StoreSetup.vue            before there is a store
    ├── DashboardView.vue, DashboardGrid.vue, WidgetFrame.vue
    ├── WidgetBody.vue            the widget of a type, on the grid or in a window
    ├── TimeseriesWidget.vue, StatWidget.vue, ProcessesWidget.vue, SeriesChart.vue
    ├── WidgetWindow.vue          one widget in a floating window
    ├── AddWidgetsDialog.vue, AgentsDialog.vue
    └── SpaceSwitch.vue
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
GET    /api/v1/metrics/processes?agent_id=&host=&sort=&limit=
GET    /api/v1/metrics/presets?agent_id=&host=  |  ?connector_id=
GET    /api/v1/metrics/connectors
PUT    /api/v1/metrics/connectors/{connector_id}      owner
GET    /api/v1/metrics/dashboards
POST   /api/v1/metrics/dashboards
GET    /api/v1/metrics/dashboards/{dashboard_id}
PUT    /api/v1/metrics/dashboards/{dashboard_id}
DELETE /api/v1/metrics/dashboards/{dashboard_id}
```

The store tests need a TimescaleDB whose role may create databases, named by
`TEST_METRICS_STORE_URL`; without it they are skipped. The compatibility source
`v2_30_pg18` serves locally — at `127.0.0.1`, because `localhost` on Windows
tries IPv6 first and waits out the connect timeout on every connection. The
suite shares the development database; the metrics tests put back the store
setting they found, while agents and dashboards go the way users do. The
`dashboards.spec.ts` scenarios start the store when the stack has none, and send
agent packets to `METRICS_UDP_PORT` themselves.

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

The engine learns nothing about dashboards: `WorkspaceRoot` takes `covered`
and draws a `cover` slot instead of the sections. Panels lose their targets,
park and deactivate, which is what a grid's pause rule already reads as not on
screen. The page switches back to Data on anything it opens, and on any change
to the tree or the panel set while covered — a tab group restored from the
header, a column brought back from the bar.

Known deviations:

- **The rail is a fixed 260 pixels** and cannot be resized or put aside.
- **A widget in a window is a copy** taken when it was opened, with the range
  and interval of that moment. Moving or removing it on the dashboard does not
  reach the window, a sort chosen in the window is not saved, and like every
  window it does not survive a reload (D14).

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
- **It binds the port as it starts**, before any store exists, and keeps it
  when the store changes. A published UDP port nobody listened on for minutes
  left Docker Desktop forwarding an agent's packets nowhere until the container
  was recreated; what arrives without a store is counted and dropped.
- **Live points come from the store, not from this process.** A subscription
  to `metrics.points` names nothing: one monitor per watching user reads, every
  two seconds, the points written since the last round for every series that
  user may read, and the screen lays them onto the raw histories it holds.
  Arguments on the subscribe frame were the alternative, and would have changed
  the transport every topic shares (D18) for a stream an agent sends a few dozen
  series of every half minute. The collector marks a series seen a moment before
  its batch is written, so a series seen without a newer point is asked again
  until ten seconds have passed.

- **Connections are polled here too**, and only here: every connection whose
  owner switched reporting on and which is itself switched on, on the interval
  the owner chose (15 s to 5 min), with the owner's stored credentials and no
  pool, at most four at once and ten seconds each. A connection that cannot be
  read backs off the way health does (D19). A counter becomes a rate per second
  over the time between two polls, so its meaning does not change with the
  interval; the first poll after a start draws no rate.

Known deviations of the live points:

- **Points of series nobody is looking at are pushed too**, bounded by what the
  person's agents report.
- **A reconnect loses the points in between** until the widget reads its
  history again: on its interval, or on a reload when the interval is Off.
- **A bucketed history takes no live points**: a sample is not an average over
  a width. It is read again on the dashboard's interval.
- **The topic has a store handle of its own**, a second small pool in the web
  process, because topics are built before the lifespan builds anything else.

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
invented for a connection: its series carry an empty host, and a screen names
them after the connection.

- **Whether a connection reports is its own capability**, `SupportsMetrics`,
  read off the driver like every other (D2, D13), with the layouts it declares.
  PostgreSQL and Redis implement it; the file source does not, and switching it
  on answers 501.
- **Switching reporting on is the owner's decision alone**: it is this server
  polling their database. Anybody the connection is shared with sees whether it
  reports and reads its series.
- **Reporting is a row of the metrics module**, not a field of the connector:
  the connector knows nothing of dashboards.

- An agent's series are its owner's; a connection's series follow D33; a
  superuser is not special (D34).
- The agent key is issued by the server, stored hashed for lookup and encrypted
  for showing to the owner, and rotatable. It is the only proof a UDP packet
  carries.
- The agents window gives a Compose snippet with the address, the key, a fixed
  `hostname` and no `iftop` action.

Known deviations:

- **Deleting an agent keeps its samples** until retention removes them; purging
  is a separate command. Its series stay in the store, readable by nobody,
  because nobody owns the agent any more. The same holds for a deleted
  connection.
- **A connection's series stay readable after its reporting is switched off**,
  and after the connection itself is: they are history, not a source.
- **A grant taken away is noticed at the next read**, the way D33's is; points
  already on screen stay there until then.

Spec: [Dashboards](../decisions/2026-09-13-dashboards-design.md)

## D129. A dashboard is a stored layout of typed widgets, read through one access check

A dashboard has an owner, a name, options and widgets. A widget is a
discriminated union by type, identified by uuid, naming series ids rather than
names. Limits: 12 columns, 20 widgets, 200 series per history request, titles of
120 characters, ranges from 60 s to one year.

- Every read of points — history and live — asks one question: may this user
  read these series, directly or through this dashboard.
- Saving refuses a widget naming a series the saver cannot read.
- A save names the version it was read at; a second tab saving in between is
  refused with 409, and the screen reads the dashboard again rather than
  overwriting it.
- Widget types today: `timeseries`, one chart per (metric, unit) of the ticked
  series; `stat`, a tile for a state such as uptime; and `processes`, the newest
  process table of one host of one agent within the last hour, which reads the
  agent rather than a series and so is checked against the agent's owner. There
  is no widget type to choose.
- **A ready-made layout is recipes, resolved on the server.** A recipe names a
  metric and fields, never series ids, which differ on every install; the
  server fills it from one host's catalog and leaves out what that host does not
  report. The gaps are closed on the screen by the grid arithmetic every move
  uses, so the layout is not compacted in two places. Layouts are declared per
  kind of source: agents have *Linux host*, and a connection's type declares
  its own through `SupportsMetrics`.
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
