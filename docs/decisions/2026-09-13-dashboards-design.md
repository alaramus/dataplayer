# Dashboards: metric collection, storage and display

Date: 2026-09-13.
Status: DB1–DB6 implemented. Slices below.

Decisions: D125 through D130, in [dashboards](../architecture/dashboards.md).

## Outcome

A person opens Dashboards from the bar at the foot of the screen. The
workspace of connections, catalogs and work is replaced by one card that holds
dashboards: a list of them, a tree of what reports metrics, and a grid of
widgets drawing those metrics over a chosen time range.

Metrics come from two kinds of source: an external agent a person registered,
sending UDP packets about a host, and — from DB4 — a connection that reports
about itself. Samples are stored in a TimescaleDB that belongs to the
installation. A superuser sets that store up the first time Dashboards is
opened, either by starting TimescaleDB on this server or by pointing the
application at an existing one.

## Evidence

Legacy sources read as workflow evidence:

- `dbwebtool/webdb/dashboard/` — especially `README.md`, which documents the
  whole subsystem across both repositories, plus `ingest.py`, `flatten.py`,
  `deltas.py`, `processes.py`, `rollup.py`, `retention.py`, `agents.py`,
  `story.py` and `access.py`.
- `dbwebtool/webdb/data_adapter/postgre/monitoring_logic.py` — how a connector
  reported about itself.
- `myquasar/src/myapp/views/Dashboards/` and `stores/dashboardStore.ts` —
  `DashboardView.vue`, `DashboardGrid.vue`, `gridLayout.ts`,
  `widgetSpecs.ts`, `seriesFormat.ts`, `statSeries.ts`, `presets/`, `demo/`.
- `dbwebtool/.deploy/dockers/monitor_agent/docker-compose.yml` — the agent
  used for development, run on 2026-09-13.

What the agent run showed:

- With `iftop` among its actions, `sys_monitor_agent` 1.14.0 exits with
  SIGSEGV (`exitCode=139`) about every 33 seconds. Inside an idle container
  `iftop -t -s 11` prints `Listening on eth0` and never finishes, so
  `iftop-result.txt` is never written, and the agent crashes when its `iftop`
  action runs. Each restart sends one set of samples. The legacy README records
  the same crash.
- Without `iftop` the agent ran four cycles of 31 seconds with no restart, and
  its values moved (`uptime` 1837 → 1930, `eth0` transfer 130 → 247 → 373).
- `host` in a packet is the container id. Recreating the container changed it
  from `b641829ceeb6` to `4be3defe44c3`, which is a new host and new series.
- `net.read` and `net.transfer` only grow.
- Packet shapes seen: `cpu` as a mapping with positional arrays
  (`cpu`, `loadavg`) and a scalar `uptime`; `disk`, `df`, `net` as lists of
  objects; `memory` as a list of single-key objects; `ps`, `python`, `tcp` as
  `ps`/`ss` output with the header echoed as the first row; numbers as strings
  (`"3%"`).

What the current application showed:

- The backend is one process (D124, settled the same day after the image was
  found starting four workers); `compose.override.yml` runs `fastapi dev`, one
  process that restarts on every saved file.
- `app/services/templates.py` already holds a `timescaledb` template
  (`timescale/timescaledb:2.30.0-pg18`). `CreateService` ends with "saving the
  connection".
- The socket's subscribe frame carries a topic name and nothing else
  (`app/realtime/messages.py`); the topic registry matches names exactly.
- D35 left several chart widgets over one source to "a dashboard layout".
- D67 pauses a grid's timer while its tab is not on screen.

## What is ported and what is not

Ported as behaviour, rewritten as code:

- Packet interpretation: numbers sent as text, a trailing `%`, non-finite
  values refused, header rows recognised by values echoing keys, label fields
  matched case-insensitively (`name`, `mounted`, `Mounted_on`, `Filesystem`),
  a trailing colon stripped from an interface, single-key objects taking an
  empty label, positional arrays named (`total`, `cpu0`…; `1m`, `5m`, `15m`),
  millisecond timestamps normalised.
- Tables that are not measurements: `ps` stored as process snapshots, `tcp`
  summarised as a count per state plus `total`, `iftop` rate lines as series
  plus a peer count, `python` refused. An empty table writes zero.
- Growing counters stored as increments, computed once on the server.
- Units per `(metric, field)`, values stored as reported, scaled for display in
  the browser.
- History at a density the caller asks for: raw points `[ts, value]`,
  aggregated `[ts, avg, min, max]`, the value at index 1 either way.
- Widget identity by uuid, never by position.
- Grid arithmetic of the legacy `gridLayout.ts`: 12 columns, non-floating,
  a moved widget pushes what it lands on down and everything falls up.
- Splitting a selection into widgets: a state-like series (uptime) becomes a
  tile, the rest one chart per `(metric, unit)`, series of one metric from
  several hosts on one chart.
- Curves drawn `smooth` with `smoothMonotone: 'x'`, so a line never leaves the
  range of the samples it joins.
- A widget expanded to fill the grid is view state, not saved.
- A stored layout that cannot be read opens empty and says so.

Not ported:

- `local_services_<id>` host names and the `story` switch with an appkey bound
  to a connector. A connection reports as itself (D128).
- The rollup and retention workers. TimescaleDB does both (D126).
- An appkey chosen by the user. The server issues it (D128).
- An administrator seeing every agent and every dashboard. D34 holds.
- Demo mode as a branch in the client. Development runs the real agent from a
  Compose profile; synthetic seeding is left until it is missed.
- Modal dialogs. Forms open in floating windows (D14).
- Presets written in the client. A source declares its own (DB3, DB4).

## D125. Dashboards are a space of their own

The foot of the screen gains a two-state switch, **Data | Dashboards**, before
the library of queries. The way back is where the way there was.

Choosing Dashboards replaces the whole workspace — connections, catalogs and
work — with one dashboards card. Nothing in the data workspace is closed or
unmounted: its layout, its panels and their state stay as they are. A console
holding an open transaction (D66), a grid on page 40, a half-written query are
all still there on the way back.

Rules:

- **Hidden is not on screen.** D67's pause rule reads "the tab is not on
  screen"; a panel of the hidden space is not on screen. Otherwise every kept
  grid with an interval would go on polling behind the dashboards.
- **Opening something into the data workspace brings it back.** The library of
  queries, a shared link, a notification that opens a connection: each switches
  to Data first. The same rule D12 applies to a column put aside on the bar.
- **Floating windows and the taskbar belong to both spaces.** A connection
  window or a detached panel stays where it was.
- **The chosen space is remembered per browser**, like the layout.

The card:

```
┌──────────────┬───────────────────────────────────────────────────┐
│ DASHBOARDS   │ Production hosts ▾   15 min ▾  ⟳ 15 s   + Add  ⋯ │
│ • Production │ ┌────────────── CPU ─────────┐ ┌─ Uptime ─┐       │
│   Staging    │ │                            │ │ 21 d 4 h │       │
│ + New        │ └────────────────────────────┘ └──────────┘       │
│              │ ┌─ Memory ──────────┐ ┌─ Network ─────────┐       │
│ SOURCES      │ │                   │ │                   │       │
│ ▸ web-01     │ └───────────────────┘ └───────────────────┘       │
│ ▸ db-01      │                                                   │
│ Agents…      │                                                   │
└──────────────┴───────────────────────────────────────────────────┘
```

- The left rail holds the dashboards of the person and the tree of sources:
  agent → host → metric → series, and from DB4 connections → metric → series.
- Adding goes through a floating window with the same tree: ticked series
  become widgets by the splitting rule above; from DB3 a source's declared
  preset is offered beside the ticks.
- Agents are managed in a floating window opened from the rail.
- A widget's own settings are edited on the widget: rename in place, the
  process table's sort and row count from its header.

Rejected:

- A route of its own (`/dashboards`). Leaving the workspace route unmounts the
  panels, and with them the state this decision exists to keep.
- A panel kind in the work column. The user wants the columns gone, and a
  dashboard needs the width.

## D126. The metrics store is a TimescaleDB that belongs to the installation

Samples are not stored in the application's database. Telemetry is constant
writes and constant expiry and is never joined with application rows; it gets
a database of its own, and that database is TimescaleDB so that chunking,
retention, compression and continuous aggregates are the extension's, not
code of this repository.

It is not a connection. D83 makes a started service an ordinary connector of
the person who started it. For the store that would:

- let the superuser read and change every person's metrics through the catalog
  and the console, against D34;
- break every dashboard of every person when one connector or one account is
  deleted.

So the store is a setting of the installation: one row in the application
database holding the address in configuration and the credentials encrypted
under the connector key (D4). It appears in no list of connections, is reachable
by no catalog, console or share, and its password is shown to nobody.

### Setting it up

The first time anybody opens Dashboards with no store configured:

- **A superuser** sees the card say the store is not set up, with two ways:
  - **Start TimescaleDB on this server.** The existing `timescaledb` template
    and the existing create job. Its last step writes the store setting instead
    of a connector, and its password never has a second home. It publishes no
    port: the application reaches it by container name on `SERVICE_NETWORK`.
    It does not count against the superuser's ceiling of services (D86). Greyed
    out, with D82's reason, where services are off or no runtime answers.
  - **Connect an existing TimescaleDB.** The PostgreSQL options form and its
    connection-string parsing (D15). Accepted only when the check succeeds and
    the database reports the extension installed or installable by that role
    (D120); refused with the reason otherwise.
- **Anybody else** sees that an administrator has not set Dashboards up yet.

Progress of a start is a job in the footer (D95). When the store answers, its
schema is applied and the card opens.

### Schema

- Not Alembic, which owns the application database. An ordered list of
  numbered migrations in the metrics module and a version table in the store,
  applied when the store is connected and when the metrics process starts,
  idempotent and serialised by an advisory lock.
- A continuous aggregate cannot be created inside a transaction block; those
  steps run outside one.
- Tables: series (id, source, metric, field, label, unit, first and last seen),
  points (hypertable on time: series id, ts, value), process snapshots
  (hypertable), and the store's own version table. Agents and dashboards live
  in the application database, where their owners are.

### Retention and density

- Until DB5: raw points kept 30 days, process snapshots 14 days, by retention
  policies. History is bucketed on read with `time_bucket` to the requested
  number of points.
- DB5 adds continuous aggregates at 1 min, 5 min and 1 h, compression, and
  shorter raw retention, chosen from measured volume. The read API does not
  change: it already answers with a bucket size.
- Corrected in DB5, from the measurement: an agent reporting 62 series every
  30 s writes 114 thousand points a day, 12 MB raw and 0.8 MB compressed. A
  one-minute aggregate of it has half as many rows as its samples, so there is
  none; raw points are kept 7 days, five-minute aggregates 35 days, hourly ones
  400 days.

### When the store is gone

- Unreachable: the card says so; agents and dashboards are still listed.
- Removed by the superuser: an explicit command with a warning that every
  person's metrics go with it. Not offered before DB5.

Known deviations, to be recorded:

- D83 does not hold for this service.
- Only one store per installation.

## D127. Metrics are collected by one process of their own

A `metrics` service in Compose, from the backend image with another command.
It is the only thing that receives UDP, and from DB4 the only thing that polls
connections for metrics. The web process reads the store and never writes
points. The metrics process is one process as well: it holds the port and the
previous sample of every counter.

Why not inside the web application, although it is one process (D124):

- `fastapi dev` restarts on every save, and a production deploy restarts the
  web process; each restart loses the packets in flight and the counter state.
  Collection should not stop because a screen was redeployed.
- Parsing and batching a steady stream of packets would share one event loop
  with every request the application serves.
- D124 makes scaling the web process out a design change still to be made.
  Collection that already lives apart is not one more thing that design has to
  answer; a UDP port bound in the lifespan would be.

How it runs:

- It reads the store setting from the application database and waits while
  there is none, then connects. No store address in `.env`.
- It publishes `9999/udp` (`METRICS_UDP_PORT`) and joins `SERVICE_NETWORK` to
  reach a started store by name.
- The receive loop never awaits: packets go into a bounded queue and drops are
  counted. Writes are batched (200 points or 1 s).
- An appkey that no agent holds is dropped before anything is written, and
  counted.
- Counter state is in memory; the first packet after a restart yields no
  increment.

Live display (DB3) does not need a channel between processes. A topic in the
web process reads points newer than what it last sent for the series being
watched, every 2 s. The agent sends every 30 s, so a push channel would buy
nothing visible. The subscribe frame carries only a topic name today; how a
subscription names what it watches is settled in DB3.

## D128. A series belongs to a typed source, and access follows its owner

A source is one of:

- `agent`: an agent row in the application database (owner, name, issued key)
  plus the host name the packet carried. One key may report several hosts.
- `connector` (DB4): a connection id. No host name is invented for it.

The identity of a series is `(source, metric, field, label)`.

Who may read a series:

- an agent's series: the agent's owner;
- a connection's series: whoever D33 grants read on that connection;
- a series on a dashboard somebody may read: see D129.

A superuser is not special here (D34).

The agent key:

- **Issued by the server**, not typed. The UDP channel carries no other proof,
  so the key is the credential that lets a packet be written, and a key like
  `TESTKEYFORNOW` is guessable.
- Stored as a hash for lookup on every packet and encrypted for showing to its
  owner, who needs it again to configure an agent. Rotating issues a new key;
  packets under the old one are dropped from then on.
- The agents window shows the key, when this agent was last heard from, and a
  Compose snippet with the server's UDP address, the key, a fixed `hostname`
  and actions without `iftop`.

Deleting an agent keeps its samples until retention removes them, unless the
owner purges them explicitly.

## D129. A dashboard is a stored layout of typed widgets, read through one access check

In the application database: owner, name, options (range, auto-refresh), and
widgets. A widget is a discriminated union by type — `timeseries`, `stat`,
`processes` (DB3) — each with a uuid, a title, a grid position and the fields
its type needs. A saved widget names series ids, not names: names come from the
catalog, so a renamed host is shown by its new name.

Limits kept from legacy: 12 columns, 20 widgets per dashboard, 200 series per
history request, a title of 120 characters, a range between 60 s and one year.
The server clamps a layout and refuses a widget type or a series it does not
know.

Every read of points goes through one question: may this user read these
series, through this dashboard or directly. The history route and the live
topic both ask it; saving a dashboard refuses a widget naming a series the
saver cannot read.

Sharing (DB6):

- A grant on a dashboard, at the ordered levels of D33: read, or edit.
- A grant on a dashboard lets its holder read exactly the series on it. There
  is no grant on an agent, so this is the only way to show one person's agent
  metrics to another, and the share window says it in words.
- Editing a shared dashboard adds only series the editor can read directly.
- A link to a dashboard follows D58–D61.

Until DB6 the check answers "owner" and nothing else. The funnel exists from
DB1 so that DB6 adds rows, not a second path.

Corrected in DB6:

- Levels are D33's `read` and `write`, the part of that scale a dashboard has.
- Reading through a dashboard is lent by its owner and editors: a series on it
  is read through it while one of them can still read it directly, so taking a
  connection away from the owner takes it from everybody reading through them.
- What a save keeps is what the dashboard already held; only what it adds must
  be readable by the saver directly, or an editor could not save a change to a
  dashboard holding the owner's agents.
- The link is the dashboard's own address. It carries no right (D58), but it is
  not a share record: no token, open log or request for access. The shares
  module's records name a connection, and making them take a second subject is
  a change to that module of its own.

## D130. What an agent sends is interpreted in one place, and a restart is read from the data

One module turns a packet into points and process rows, with the rules listed
under "What is ported". Nothing downstream knows what `df` prints.

A restart shows in the data: `uptime` of a host goes down. The metrics process
counts restarts per agent host. From DB5, repeated restarts within a window
become an attention item (D115) naming the host and pointing at the known
`iftop` crash when the agent sends that action. The crash found on 2026-09-13
would have been reported by the application.

Corrected in DB5, from runs of the crashing agent beside a steady one: its
`uptime` kept growing (2949, 2982, 3015), because a container reads the Docker
VM's, so uptime alone misses the crash. Interface values could not stand in:
they are bytes divided by an interval of 30 or 31 seconds, so an idle one goes
down between two packets of an agent that never restarted. What does show it
is the agent's own row in its `ps` table: every table the crashing agent sent
said it had run 32 seconds, 34 seconds after the one before. That row's command
line also carries `--actions=`, so the `iftop` hint is given exactly when the
agent runs it.

Replaced on 2026-09-14 by
[the monitor agent protocol](2026-09-14-monitor-agent-protocol-design.md):
`sys_monitor_agent` gave way to `dataplayer-monitor-agent`, whose datagrams are
signed and say which process sent them, so nothing above is interpreted any
more, a restart is a new agent process, and the key never travels.

## Slices

| Slice | Contents |
| --- | --- |
| DB1 | Metrics module and store setting; first-entry setup (start or connect); store migrations; the `metrics` process with UDP ingest and packet interpretation for series and process snapshots; agents in the application database with issued keys; catalog and history routes with the access funnel; agent development profile in Compose. |
| DB2 | The Data \| Dashboards switch; the dashboards card; create, rename, delete; the source tree; adding widgets; `timeseries` and `stat`; drag and resize; range and auto-refresh; the agents window. |
| DB3 | Live points on the socket; the process table; presets declared on the server; a widget detached into a floating window (D93) and kept over the data workspace. |
| DB4 | `SupportsMetrics` on adapters, polled by the metrics process: PostgreSQL (`pg_stat_database`), Redis (`INFO`), each declaring its preset. |
| DB5 | Continuous aggregates, compression, retention from measured volume; removing the store; agent restarts as attention items. |
| DB6 | Dashboard grants, the share window and links. |

DB1 is verifiable without a screen: the development agent writes, the history
route answers. DB2 is the first slice a person sees.

## Testing

- Pure: packet interpretation against packets captured from the agent run
  (header rows, text numbers, positional arrays, tables, counters); bucket
  choice; widget splitting; grid arithmetic; the access funnel.
- Backend against a store: migrations applied twice; batches written; history
  bucketed; retention policy present; an unknown key written nowhere; an agent
  of another owner refused; a dashboard naming a foreign series refused.
  The backend CI job gains a `timescale/timescaledb:2.30.0-pg18` service for
  these tests; locally the compatibility containers serve.
- Failure paths: store not configured, store unreachable, services off, an
  existing database without the extension, a malformed packet, a full queue.
- Browser: first entry as superuser and as an ordinary user; the switch keeps a
  grid's page and does not poll it while hidden; a chart draws points the agent
  sent.

## Open questions

- How a subscription names what it watches (DB3): an argument on the subscribe
  frame, or a topic per dashboard.
- Whether the agent's `--securekey` authenticates packets. Not investigated;
  moot since the monitor agent protocol, whose datagrams are signed.
- Whether agents should be shareable on their own, apart from dashboards.
