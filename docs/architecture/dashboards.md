# Dashboards

Metrics from agents and connections, the store they are kept in, the process
that collects them, and the card that draws them. Read this before changing
anything that ingests, stores or shows a metric.

Decisions here: D125, D126, D127, D128, D129, D130.

## What exists today

**Data | Dashboards | AI** at the foot of the screen chooses the application
space (D141); Dashboards covers the workspace with its card. Before a store
exists the card offers a superuser to start TimescaleDB or connect an existing
one, and tells anybody else that an administrator sets it up. With a store it
lists the person's dashboards and the sources their agents reported. A dashboard
is a 12-column grid of charts and tiles; widgets are added by ticking series,
moved by their header, resized by their corner, renamed in place and expanded to
fill the grid, and the whole is saved a moment after the last change. The
Dashboards rail head can become a name filter; filtering changes the rail list
without changing the open dashboard. The Sources window registers an agent,
shows its key and the Compose file that starts `dataplayer-monitor-agent` with
it, and lists the hosts the person's agents
report: the system, processors and memory, the agent's version, how long each
has been up and when it was last heard.

Points an agent sends appear on open charts and tiles within a couple of
seconds, without the dashboard re-reading anything. A host that sends its process
table has a `processes` leaf in the tree, which becomes a table sorted by CPU,
memory or PID, with each process's state, resident size and how long it has run,
and how many processes the host has. Selecting a host in the Add window offers
its ready-made layouts — today one, *Linux host* — filled with what that host
reports and placed under what the dashboard already holds. Any widget opens in a
floating window, which stays when the screen is switched back to Data.

A PostgreSQL or Redis connection reports about itself once its owner switches
reporting on in the Sources window, choosing how often. Its series sit beside the
agents in the tree under the connection's own name, anybody the connection is
shared with can draw them, and selecting it offers the layout its type declares:
*PostgreSQL database* or *Redis server*. Counters of a connection are drawn as
rates per second.

The store keeps raw samples for a week, compressed after a day, and averages over
five minutes and over an hour for longer; a long range is read from them without
the screen knowing. A superuser sees where the store is, what it takes and how
long it keeps what in the *Metrics store* window, opened from the rail or from a
store that stopped answering, and removes it from there. A host that keeps
restarting is an item in the activity sheet.

The owner of a dashboard shares it from its Share window, with a person, to view
or to edit, and the window says that this shows them the owner's agents' hosts on
it. The person finds it under *Shared with you* in the rail and draws it from
series they could not read otherwise. Somebody who may only view can pick another
range for themselves, and nothing they do is saved. The window also carries the
dashboard's link, which opens it for anybody holding access and tells anybody
else that it does not exist or was not shared with them.

The `metrics` process receives agents' datagrams, checks them and writes samples,
process tables, restarts and what each host is; the web process answers the
catalog of what a person's agents reported and the history of chosen series, raw
or bucketed. Development starts an agent in the `monitor-agent` Compose profile
under `METRICS_DEV_AGENT_KEY`, which prestart registers for the first superuser.

```
backend/app/metrics/
├── protocol.py     DPMA/1: a datagram, its signature, its body, its freshness; pure
├── counters.py     a connection's counters as rates
├── keys.py         issuing, fingerprinting and sealing agent keys
├── models.py       MetricsAgent, MetricsStoreSetting, and the API models
├── crud.py         application-database access
├── migrations.py   the store's numbered schema
├── store.py        the store: series ids, writes, catalog, history, purge
├── holder.py       the web process's handle on the store
├── history.py      raw or which bucket width, from which table; pure
├── access.py       who may read a series and a dashboard
├── setup.py        store status, starting it, connecting one
├── jobs.py         the service create job, delivering a store setting
├── collector.py    the metrics process
├── dashboards.py   Dashboard, its widget union and limits, its grants
├── presets.py      ready-made layouts and resolving them against a host
├── live.py         the `metrics.points` topic
├── poller.py       connections polled for metrics, in the metrics process
├── restarts.py     a restart from a new agent process, and when restarts need a person; pure
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
    │   agentSnippet.ts, storeFacts.ts, hostFacts.ts, railWidth.ts, railEntry.ts
    │                             what is drawn and said; pure
    ├── attention.ts              a host that keeps restarting, for the sheet
    ├── sharing.ts                what a standing allows, a dashboard's link; pure
    ├── intent.ts                 a followed link waiting for the dashboards
    ├── livePoints.ts             socket points onto a history; pure
    ├── DashboardsSpace.vue       the card
    ├── StoreSetup.vue            before there is a store
    ├── DashboardView.vue, DashboardGrid.vue, WidgetFrame.vue
    ├── WidgetBody.vue            the widget of a type, on the grid or in a window
    ├── TimeseriesWidget.vue, StatWidget.vue, ProcessesWidget.vue, SeriesChart.vue
    ├── WidgetWindow.vue          one widget in a floating window
    ├── DashboardsRailNarrow.vue  the rail pushed aside to its icons
    ├── AddWidgetsDialog.vue, AgentsDialog.vue, StoreDialog.vue
    ├── DashboardShareDialog.vue  who may see a dashboard, and its link
    ├── DashboardLinkPage.vue     the /dashboards/:id address
    └── SpaceSwitch.vue
```

```
GET    /api/v1/metrics/store
POST   /api/v1/metrics/store/start          superuser
POST   /api/v1/metrics/store/connect        superuser
GET    /api/v1/metrics/store/usage          superuser
DELETE /api/v1/metrics/store                superuser
GET    /api/v1/metrics/restarts
GET    /api/v1/metrics/hosts
GET    /api/v1/metrics/agents
POST   /api/v1/metrics/agents
PATCH  /api/v1/metrics/agents/{agent_id}
DELETE /api/v1/metrics/agents/{agent_id}
GET    /api/v1/metrics/agents/{agent_id}/key
POST   /api/v1/metrics/agents/{agent_id}/key
POST   /api/v1/metrics/agents/{agent_id}/purge
GET    /api/v1/metrics/catalog
POST   /api/v1/metrics/history                   a dashboard_id reads through it
GET    /api/v1/metrics/processes?agent_id=&host=&sort=&limit=&dashboard_id=
GET    /api/v1/metrics/presets?agent_id=&host=  |  ?connector_id=
GET    /api/v1/metrics/connectors
PUT    /api/v1/metrics/connectors/{connector_id}      owner
POST   /api/v1/metrics/connectors/{connector_id}/purge   owner
GET    /api/v1/metrics/dashboards
POST   /api/v1/metrics/dashboards
GET    /api/v1/metrics/dashboards/{dashboard_id}            read
GET    /api/v1/metrics/dashboards/{dashboard_id}/catalog    read
PUT    /api/v1/metrics/dashboards/{dashboard_id}            write
DELETE /api/v1/metrics/dashboards/{dashboard_id}            owner
GET    /api/v1/metrics/dashboards/{dashboard_id}/grants     owner
PUT    /api/v1/metrics/dashboards/{dashboard_id}/grants     owner
DELETE /api/v1/metrics/dashboards/{dashboard_id}/grants/{user_id}  owner
```

Traps in the tests. The store tests need a TimescaleDB whose role may create
databases; by default the compatibility source `v2_30_pg18`, at `127.0.0.1`
rather than `localhost`, which on Windows tries IPv6 first and waits out the
connect timeout on every connection. `TEST_METRICS_STORE_URL` names another, and
without one answering the store tests are skipped
([backend.md](backend.md#tests-and-the-servers-they-need)). The suite shares the
development database, so the metrics tests put back the store setting they found.
`dashboards.spec.ts` starts the store when the stack has none and sends signed
DPMA/1 datagrams to `METRICS_UDP_PORT` itself. Tests write points days in the
past, outside every refresh policy's window, so a test reading a rollup refreshes
it first (`refresh_rollups` in the metrics conftest); their moments are counted
back from now rather than fixed, because which table history reads depends on how
old a range is.

## D125. Dashboards are a space of their own

A **Data | Dashboards** choice at the foot of the screen, extended with AI by
D141, replaces the whole workspace with one dashboards card: dashboards and
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

The engine learns nothing about dashboards: `WorkspaceRoot` takes `covered` and
draws a `cover` slot instead of the sections. Panels lose their targets, park and
deactivate, which is what a grid's pause rule already reads as not on screen. The
page switches back to Data on anything it opens, and on any change to the tree or
the panel set while covered — a tab group restored from the header, a column
brought back from the bar.

Known deviations:

- **The rail is resized and pushed aside the way a workspace column is, but it is
  not a section of the workspace.** The gap beside it drags it from 200 pixels to
  two fifths of the space, so the dashboard stays the wider card; the header
  button narrows it to forty pixels of icons — New alone in its head, then the
  dashboards, Sources and the store — and the header button or a press on the gap
  brings it back. Width and state are kept per browser, and a narrower window
  narrows it. It cannot be put on the bar or moved to the other side.
- **A widget in a window is a copy** taken when it was opened, with the range and
  interval of that moment. Moving or removing it on the dashboard does not reach
  the window, a sort chosen in the window is not saved, and like every window it
  does not survive a reload (D14). The window offers to move its contents into a
  workspace tab, and the tab follows the same snapshot semantics (D155).

Spec: [Dashboards](../decisions/2026-09-13-dashboards-design.md)

## D126. The metrics store is a TimescaleDB that belongs to the installation

Samples live in a TimescaleDB of their own, not in the application database.
Chunking, retention, compression and continuous aggregates are the extension's.

- **Not a connection.** One installation setting holds the address, with the
  credentials encrypted under the connector key (D4). No catalog, console, share
  or list of connections reaches it. A store owned as a superuser's connector
  would give that superuser every person's metrics (D34) and would break every
  dashboard when that connector or account went.
- **Set up on first entry by a superuser**, one of two ways: start the
  `timescaledb` template, whose create job writes the store setting instead of a
  connector, publishes no port and does not count against D86's ceiling; or
  connect an existing database, accepted when the check succeeds and the
  extension is installed or installable (D120). Anybody else is told an
  administrator has not set Dashboards up.
- **Its schema is not Alembic's.** Numbered migrations in the metrics module, a
  version table in the store, applied on connect and on start of the metrics
  process under an advisory lock. Continuous aggregates are created outside a
  transaction.
- **Retention is a policy, and a long range is read from rollups.** Raw points
  are kept 7 days and compressed after one; continuous aggregates hold a sum, a
  count, a minimum and a maximum per series over 5 minutes (35 days) and over an
  hour (400 days); process tables and restarts are kept 14 days, and what a host
  is — one row per agent and host, replaced as the agent sends it — until its
  agent's data is purged. History answers raw `[ts, value]` when the densest
  series fits and raw samples reach the start, and `[ts, avg, min, max]`
  otherwise, from the coarsest table that holds the start and divides the width.
  `history.py` holds the tiers and a test holds them to the store's policies.
- **Chosen from measured volume.** An agent reporting 62 series every 30 s writes
  114 thousand points a day: 12 MB raw, 0.8 MB compressed. A one-minute rollup of
  such an agent has half as many rows as its samples, so there is none.
- **A refresh reaching back past raw retention deletes the rollup of that time.**
  Policy windows are hours to three days, under raw retention, and raw retention
  is shortened by a migration of its own, after the backfill.
- **Removing the store** is a superuser's command with a warning that every
  person's samples go. A store started here is removed with its volume by the job
  that removes any service; a store somebody connected keeps its database, and
  the tables the migrations made in it are dropped. The setting goes first, so
  nothing prepares the schema again in between, and every widget naming a series
  is taken off its dashboard: a new store numbers series from one again, and an
  old id would draw another host. Process tables name an agent and a host, and
  stay.
- Agents and dashboards stay in the application database with their owners.

Known deviations:

- D83 does not hold for this one service. `ManagedService.purpose` says so, and
  every person-scoped query of the services module reads connections only.
- There is one store per installation.
- **The store's service row belongs to the superuser who started it.** Deleting
  that account deletes the row; the container keeps running and serving, but shows
  among the containers no row claims, where an administrator could remove it. Such
  a store is described and removed as a connected one: its tables are dropped and
  the container stays. The backend suite deletes every service row, so a
  development store is one of these after a test run.
- **A store that stops answering is found out when somebody asks.** The status
  says `unreachable`; nothing watches it in between.
- **A purge deletes from the rollups' own tables**, found through Timescale's
  catalog, because a view cannot be deleted from and a refresh does not reach that
  far back.
- **The rollups are built on raw points, not one on another**, so they work on
  releases older than hierarchical aggregates; the hourly policy reads three days
  of raw points every hour.
- **The first start after an upgrade backfills both rollups** while holding the
  migration lock; on a large store the first request waits for it.
- **A connected store that does not answer is removed all the same**: the setting
  goes, and the answer says its tables stayed in that database.
- **Migration 4 took out everything agents had written** when the format of
  `sys_monitor_agent` was dropped (D130), connections' series kept. A widget
  naming such a series says the series does not exist, and its owner removes it:
  the store's migration cannot reach the application database.

Spec: [Dashboards](../decisions/2026-09-13-dashboards-design.md)

## D127. Metrics are collected by one process of their own

A `metrics` service from the backend image receives UDP and polls connections. It
is one process, holding the port, the keys agents sign with, what it accepted
from each agent instance and the previous reading of every connection counter.
The web process reads the store and never writes points.

- Not inside the web application, although that is one process too (D124): its
  reloads and deploys would drop datagrams and counter state, the stream would
  share the event loop with every request, and a port bound in the lifespan would
  be one more thing scaling the web process out has to answer.
- It reads the store setting from the application database and waits while there
  is none.
- It publishes `METRICS_UDP_PORT` (9999/udp) and joins `SERVICE_NETWORK`.
- The receive loop never awaits; a bounded queue drops and counts. Points are
  written in batches.
- A datagram is checked before anything is written, and each refusal counted
  apart: its frame, its key id, its signature, its body and its freshness (D130).
- **It binds the port as it starts**, before any store exists, and keeps it when
  the store changes. A published UDP port nobody listened on for minutes left
  Docker Desktop forwarding an agent's datagrams nowhere until the container was
  recreated; what arrives without a store is counted and dropped.
- **Live points come from the store, not from this process.** A subscription to
  `metrics.points` names nothing: one monitor per watching user reads, every two
  seconds, the points written since the last round for every series that user may
  read, and the screen lays them onto the raw histories it holds. Arguments on the
  subscribe frame were the alternative, and would have changed the transport every
  topic shares (D18) for a stream an agent sends a few dozen series of every half
  minute. The collector marks a series seen a moment before its batch is written,
  so a series seen without a newer point is asked again until ten seconds have
  passed.
- **Connections are polled here too**, and only here: every connection whose owner
  switched reporting on and which is itself switched on, on the interval the owner
  chose (15 s to 5 min), with the owner's stored credentials and no pool, at most
  four at once and ten seconds each. A connection that cannot be read backs off
  the way health does (D19). A counter becomes a rate per second over the time
  between two polls, so its meaning does not change with the interval; the first
  poll after a start draws no rate.

Known deviations of the live points:

- **Points of series nobody is looking at are pushed too**, bounded by what the
  person's agents report.
- **A reconnect loses the points in between** until the widget reads its history
  again: on its interval, or on a reload when the interval is Off.
- **A bucketed history takes no live points**: a sample is not an average over a
  width. It is read again on the dashboard's interval.
- **The topic has a store handle of its own**, a second small pool in the web
  process, because topics are built before the lifespan builds anything else.

Known deviations:

- **Agent keys are held unsealed** in the process for the life of a store: a
  signature is checked with the key itself.
- **What was accepted is remembered in memory**, so a datagram sent again within
  ten minutes of being sent before the process started is written twice.
- **The process re-resolves every series every fifteen seconds.** A purge in the
  web process deletes series rows the process still holds ids of; points written
  under such an id in that window are lost. Re-resolving is an upsert per series
  per interval.
- **A batch that fails to write is dropped**, and counted in the log line the
  process writes every minute.

Spec: [Dashboards](../decisions/2026-09-13-dashboards-design.md)

## D128. A series belongs to a typed source, and access follows its owner

A source is an agent plus the host its datagram named, or a connection. The
identity of a series is `(source, metric, field, label)`. No host name is
invented for a connection: its series carry an empty host, and a screen names
them after the connection.

- **Whether a connection reports is its own capability**, `SupportsMetrics`, read
  off the driver like every other (D2, D13), with the layouts it declares.
  PostgreSQL and Redis implement it; the file source does not, and switching it on
  answers 501.
- **Switching reporting on is the owner's decision alone**: it is this server
  polling their database. Anybody the connection is shared with sees whether it
  reports and reads its series.
- **Reporting is a row of the metrics module**, not a field of the connector: the
  connector knows nothing of dashboards.
- An agent's series are its owner's; a connection's series follow D33; a superuser
  is not special (D34).
- The agent key is issued by the server, stored hashed for lookup and encrypted
  for checking signatures and showing to the owner, and rotatable. It signs every
  datagram and never travels; a datagram names it by the first sixteen characters
  of its hash.
- The Sources window gives a Compose file for `alaramus/dataplayer-monitor-agent`
  with the server's address and the key, the host's `/proc`, `/sys` and `/`
  mounted read-only, its process and network namespaces and the Docker socket
  read-only. The host name is the host's own unless one is typed.

Known deviations:

- **Deleting an agent keeps its samples** until retention removes them; purging is
  a separate command. Its series stay in the store, readable by nobody, because
  nobody owns the agent any more. The same holds for a deleted connection.
- **A connection's series stay readable after its reporting is switched off**, and
  after the connection itself is: they are history, not a source.
- **A grant taken away is noticed at the next read**, the way D33's is; points
  already on screen stay there until then.

Spec: [Dashboards](../decisions/2026-09-13-dashboards-design.md)

## D129. A dashboard is a stored layout of typed widgets, read through one access check

A dashboard has an owner, a name, options and widgets. A widget is a
discriminated union by type, identified by uuid, naming series ids rather than
names. Limits: 12 columns, 20 widgets, 200 series per history request, titles of
120 characters, ranges from 60 s to one year.

- Every read of points — history and live — asks one question: may this user read
  these series, directly or through this dashboard.
- Saving keeps what the dashboard already held and refuses a widget adding a
  series or a process table its saver cannot read directly.
- A save names the version it was read at; a second tab saving in between is
  refused with 409, and the screen reads the dashboard again rather than
  overwriting it.
- Widget types today: `timeseries`, one chart per (metric, unit) of the ticked
  series; `stat`, a tile for a state such as uptime; and `processes`, the newest
  process table of one host of one agent within the last hour, which reads the
  agent rather than a series and so is checked against the agent's owner. There is
  no widget type to choose.
- **A ready-made layout is recipes, resolved on the server.** A recipe names a
  metric and fields, never series ids, which differ on every install; the server
  fills it from one host's catalog and leaves out what that host does not report.
  The gaps are closed on the screen by the grid arithmetic every move uses, so the
  layout is not compacted in two places. Layouts are declared per kind of source:
  agents have *Linux host*, and a connection's type declares its own through
  `SupportsMetrics`.
- **A dashboard may carry a colour**, `#RRGGBB` as a connection's tab colour is,
  chosen by whoever may change its name and saved with the rest. The rail washes a
  dashboard in it and fills the open one, wide and narrow, and the name at the head
  of the dashboard is filled with it; one without a colour is marked open in blue.
- **A dashboard is shared by a grant**, a row per person, on D33's scale: `read`
  sees it, `write` changes what is on it, its name and options; ownership is a
  column, and grants, deleting and sharing are the owner's. No standing answers
  404 and too little 403, as a connection's do. The listing sends the caller's
  standing and, for a shared dashboard, who shared it, so the screen hides what
  the server would refuse.
- **A grant lets its holder read the series on that dashboard and nothing else**:
  not the agents or connections they came from, not the other series of those
  hosts. There is no grant on an agent, so this is how one person's agent metrics
  are shown to another, and the Share window says it in words.
- **Reading through a dashboard is lent by the people who may fill it.** A series
  on it is read through it while its owner or one of its editors can still read
  that series directly. A connection grant taken from the owner, or an editor
  lowered to `read`, takes those series from everybody reading through them at
  their next read.
- The names a shared dashboard's widgets are drawn with come from a catalog of
  that dashboard alone, merged under what the person reads directly.

Known deviations:

- **The link is the dashboard's address, not a share record.** D58 holds: it
  carries no right. D59–D61 do not: there is no token, no log of who opened it, no
  screen naming what it is to somebody without access, and no request for access
  through it; such a reader is told it does not exist or was not shared with them.
  Links and requests belong to one feature (D61) whose records name a connection,
  and a second copy of that machinery for dashboards is what the shares module
  being made to take either subject should replace.
- **Live points learn a new grant, or a lost one, within ten seconds**: who may
  read what is asked again at that interval rather than every round.
- **A viewer's choice of range and interval is not kept** past the dashboard being
  closed.

Spec: [Dashboards](../decisions/2026-09-13-dashboards-design.md)

## D130. What an agent sends is DPMA/1, checked before it is read, and a restart is a new agent process

Agents are `dataplayer-monitor-agent`, and the contract is its `PROTOCOL.md`: a
UDP datagram `DPMA/1 <kid> <signature>\n<body>`, standing alone under 1400 bytes,
whose body names the agent process, the host and its boot, a sequence number and
the moment it measured. `protocol.py` is the receiving half.

- **Checked in order before anything is written:** a DPMA/1 frame; a key id some
  agent holds; an HMAC-SHA256 over the body's bytes as received, compared in
  constant time and tried with every key the id names; a body that is the
  protocol; a time no more than ten minutes old or two ahead; a sequence number
  not yet accepted for that agent instance, remembered 1024 below the highest.
- **A body is refused whole** when one sample or row breaks the protocol. The
  agent checks each sample before it packs it; one that still arrives is a defect
  to see, not data to salvage.
- **Samples are written as they come.** Units, rates and labels are the agent's:
  rates are computed between its own readings on a monotonic clock, so the process
  keeps no counter state for agents. A process table sent in parts is the rows of
  every part at one moment; a `host` body is what the host is.
- **A restart is a new `agent.instance`**, at its `agent.started`, caused by the
  host when `host.boot` changed with it and by the agent otherwise. An instance
  that started earlier than the one known is an older process still sending, or a
  second agent under the same host name, and is not a restart. The newest instance
  of each host is kept in the store, so the process starting again does not take
  every agent for restarted.
- **Three restarts of one host within fifteen minutes are an attention item**
  (D115) for the agent's owner, counted by the server. It cannot be waved away and
  goes once the host stops restarting.

Rejected: keeping `sys_monitor_agent`'s format beside this one — two interpreters
and a store holding numbers that mean different things under similar names;
checking a signature against the stored hash — the hash would become the secret,
and it is stored in the clear.

Known deviations:

- **An agent reporting a host name another agent of the same key reports** is one
  host: its series mix, and only the later process counts for restarts.
- **Only agents are watched.** A database restarting behind a connection is not an
  item.

Spec: [Monitor agent protocol](../decisions/2026-09-14-monitor-agent-protocol-design.md)
