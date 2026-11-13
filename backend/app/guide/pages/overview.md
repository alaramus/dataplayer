# DataPlayer at a glance

DataPlayer connects the sources you work with — databases, file storage,
queues, servers over SSH and others — and lets you read and change them in one
place. This page says where things are; each part has a page of its own.

## The four spaces

The switch at the top of the left rail chooses what fills the screen:

- **Data**: your connections, their catalogs and the tables, files and queries
  opened from them. See [The workspace](workspace.md) and
  [Connections](connections.md).
- **Pipelines**: connections laid out on a canvas, with links that copy rows
  and files from one to another, by hand or on a schedule. See
  [Pipelines](pipelines.md).
- **Dashboards**: metrics reported by agents and by your connections, drawn
  over time. See [Dashboards](dashboards.md).
- **AI**: conversations with the agent, which reads and changes your data
  through the same connections. See [The AI agent](assistant.md).

Switching spaces keeps what was open: coming back to Data finds the same tabs.

## Around the edges

- **The header** holds the search field, which finds connections, tables,
  files, saved queries, pipelines, dashboards, chats and pages of this guide.
  Ctrl+K (⌘K on a Mac) puts the cursor in it. See [Search](search.md).
- **The user menu**, at the top right, opens **Preferences**, **Admin** for an
  administrator, and **Sign out**. See [Preferences and your account](preferences.md).
- **The rails** on both sides hold tools as icons: the space switch and
  **Quick chat** at the top left; **Services**, **Terminals**, **Queries** and
  **Search index** at the bottom left; saving and opening tab groups at the top
  right. A tool can be dragged to another place on its rail or to another rail.
- **The panel at the foot** opens for **Services**, **Terminals**, **Queries**,
  **Search index** and, for an administrator, **Logs**. See
  [Services and terminals](services.md).
- **The activity bell**, at the bottom right, opens **Activity**: what needs
  your answer, what is running, and what happened recently.

## Where to read about

- a kind of source — its own page: [PostgreSQL](source-postgres.md),
  [MySQL and MariaDB](source-mysql.md), [SQLite](source-sqlite.md),
  [ClickHouse](source-clickhouse.md), [Cassandra and ScyllaDB](source-cassandra.md),
  [MongoDB](source-mongodb.md), [Redis](source-redis.md),
  [ZooKeeper](source-zookeeper.md), [Kafka](source-kafka.md),
  [RabbitMQ](source-rabbitmq.md), [Binance](source-binance.md),
  [Files](source-file.md) and [SSH](source-ssh.md). Reading rows, editing
  them, changing structure, the SQL console and reports are described there,
  for that source;
- adding, sharing and setting up a connection — [Connections](connections.md);
- columns, tabs, windows and tab groups — [The workspace](workspace.md);
- moving data on a schedule — [Pipelines](pipelines.md);
- metrics and charts over time — [Dashboards](dashboards.md);
- the agent, quick chat and connecting an outside AI agent —
  [The AI agent](assistant.md);
- servers started here, terminals and backups —
  [Services and terminals](services.md).
