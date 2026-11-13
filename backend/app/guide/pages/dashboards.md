# Dashboards

A dashboard draws metrics over time: charts and tiles on a grid. Metrics come
from agents you run on your machines and from connections that report about
themselves. Dashboards are in the **Dashboards** space of the switch at the top
of the left rail.

## Before the first dashboard

Metrics are kept in a store of their own, a TimescaleDB database. An
administrator sets it up once for the whole installation: the Dashboards space
offers them to start one here or to connect an existing one. Until then,
everybody else is told that an administrator sets it up.

**The metrics store**, in the head of the rail, is the administrator's: where
the store is, how much it takes, how long it keeps what, and removing it. Raw
samples are kept for a week; averages over five minutes and over an hour are
kept for longer.

## Where metrics come from

**Sources**, in the head of the rail, opens a window with two views.

- **Agents**: an agent is a small program that reports the machine it runs
  on, such as its processors, its memory and its processes. Type an
  **Agent name** and **Register**: the window shows the agent's key and a
  Docker Compose file that starts it with that key on the machine to watch.
  **Hosts** lists what your agents report, with the system, the hardware, how
  long each has been up and when it was last heard. **Issue a new key** cuts
  off the old one; removing an agent drops whatever it sends from then on.
- **Connections**: a PostgreSQL, MySQL or Redis connection can report its own
  counters. Its owner switches **Reports** on and chooses **How often**, from
  every 15 seconds to every 5 minutes. Anybody the connection is shared with
  can draw what it reports.

What an agent sends appears on open charts within a couple of seconds.

## Making a dashboard

1. **New dashboard** in the head of the rail. It is named for you; rename it
   from its head.
2. **Add widgets** opens the sources as a tree. Tick the series to draw and
   **Add**. Selecting a host or a connection offers its ready-made layouts —
   **Linux host**, **PostgreSQL database**, **MySQL server**, **Redis
   server** — and **Add layout** places one under what the dashboard already
   holds.
3. Move a widget by its header, resize it by its corner, double-click its title
   to rename it. A host's `processes` makes a table of its processes, sorted by
   CPU, memory or PID.

A dashboard is saved a moment after each change. **Range** chooses how far back
to draw, from the last 5 minutes to the last 30 days, and **Refresh every**
how often to read again.

A widget can fill the dashboard (**Fill the dashboard with this widget**), or
be opened in a window that stays when you switch back to Data.

## Sharing a dashboard

**Share this dashboard** gives a person access: **Can view** or **Can edit**.
They find it under **Shared with you** in the rail. Whoever is given access sees
every series on the dashboard, your agents' hosts included, and nothing else of
yours. Somebody who may only view can choose another range for themselves;
nothing they do is saved.

The window also has the dashboard's link. It opens the dashboard for anybody
who was given access, and for nobody else.

## Limits

- Deleting a dashboard removes its widgets; the metrics stay.
- A host that keeps restarting is listed under **Needs you** in the activity
  bell.
