# Kafka

A Kafka cluster. You see its topics and consumer groups, read a topic's
messages as rows, and see how far each group lags behind. How connections work
in general is on the [Connections](connections.md) page.

## What you can see

- The cluster's topics, its consumer groups, and Kafka's own topics apart
- A topic's messages as rows, newest first, from any time or offset
- The fields of JSON messages, each in a column of its own
- Each partition of a topic: its leader, replicas and offsets
- The settings made on a topic
- Where each consumer group stands in each partition, and its lag
- The cluster's reports: brokers, settings, partitions needing attention
- Lag, messages per second and the cluster's health on a dashboard
- Topics and groups found by name
- A topic's messages downloaded as a file
- Kafka's own tools, set up for the connection, in a terminal

## What you can change

- Messages sent, one by one or pasted as rows
- New topics, with their partitions and settings
- Topics deleted, their settings changed, partitions added
- A topic's messages deleted, all of them or those before a time
- A consumer group's positions moved to the start, the end or a time
- Consumer groups deleted
- Anything Kafka's tools can change, typed into the terminal

## Connecting

The **Connection** page of the window asks for:

- **Brokers**: `host:port` of one or more brokers, separated by commas. One is
  enough: it tells DataPlayer where the rest are;
- **TLS**: an encrypted connection, with the brokers' certificates checked;
- **CA certificate**: the authority that signed them, as PEM, when it is not
  one the system already trusts;
- **Authentication**: **None**, or a user and password with **SASL PLAIN**,
  **SASL SCRAM-SHA-256** or **SASL SCRAM-SHA-512**.

DataPlayer connects to the addresses the brokers announce about themselves, so
they must be reachable from the DataPlayer server under those names. An SSH
tunnel is not supported.

## The catalog

- **Topics**, **Consumer groups** and **Internal topics** — Kafka's own, such
  as `__consumer_offsets`, whose names start with an underscore.
- A topic says how many partitions it has and how many messages they span. The
  number is an upper bound: compacted topics have gaps.
- A group says whether it is stable, rebalancing or has no consumers, and how
  many consumers it has.
- A level shows its first thousand by name.

## A topic's messages

- One row per message: its partition, offset, time, key, value and headers.
- When the values are JSON objects, each field is a column too, named
  `value.` and the field. The fields come from the newest two hundred messages.
- A key or a value that is not text is shown in hex.
- Newest first, across all partitions. Sort by **timestamp** to start from the
  oldest; no other column sorts.
- Filter by **partition**, **offset** or **timestamp** to choose where reading
  starts and stops: Kafka finds that place itself, however long the topic is.
- Filters on the key, the value, the headers and the fields look through the
  messages read, up to a hundred thousand for one page.
- A page reaches at most ten thousand messages from the end. To look further
  back, filter by time or by partition and offset.
- Reading a topic does not join a consumer group and moves nobody's position.

## Sending messages

- **+** over a topic's rows adds a message. Fill what you need: everything
  may stay empty.
- **partition** empty lets Kafka choose by key; **timestamp** empty is now.
- **key** and **value** are text; `0x` followed by hex digits is sent as those
  bytes.
- Leave **value** empty and fill the `value.` fields to send a JSON object
  of them.
- **headers** is a JSON object of text, such as `{"source": "manual"}`.
- Rows pasted into a topic are sent as messages. If one value cannot be read,
  nothing is sent and the cell is named.
- Kafka's own topics take no messages from here.

## A consumer group

- One row per partition the group reads: the topic, the partition, the
  position the group committed, the end of the partition, and the lag between
  them, with the consumer reading it. The rows refresh every ten seconds.

## The details panel

Select a topic or a group and choose **Details** in the catalog's menu.

- A topic: its number of messages, one line per partition with its leader,
  replicas, in-sync replicas and offsets, and the settings made on the topic.
- A group: its state, consumers, total lag, coordinator broker, assignor and
  topics.

## Kafka's tools

**Terminal** on a Kafka connection opens Kafka's own command-line tools, the
ones its documentation uses, already pointed at the connection: its brokers,
its TLS and its user. Type a tool without `--bootstrap-server`:

- `kafka-topics.sh --list` — the topics
- `kafka-console-consumer.sh --topic NAME --from-beginning` — read a topic;
  Ctrl+C stops it
- `kafka-consumer-groups.sh --describe --all-groups` — every group's lag

Give `--bootstrap-server` yourself to point a tool at another cluster. The
terminal runs in a container on the DataPlayer server, so it needs that server
to be allowed to start containers, and the brokers must be reachable from
there.

## Changing topics and groups

Tick a topic on the **Topics** level and open the catalog's menu:

- **New topic** — a name, the number of partitions, a replication factor
  (empty for the broker's default) and settings, one `name=value` per line.
- **Delete topic** — the window says how many messages go and which groups
  read the topic.
- **Change settings** — opens with the topic's own settings; take a line away
  to return that setting to the broker's default.
- **Add partitions** — partitions can only be added, never taken away. A key
  may land on another partition from then on.
- **Delete messages** — all of them, or those before a time. This cannot be
  undone.

Tick a group on the **Consumer groups** level for **Move positions**: to the
start, the end or a time, for all its topics or one. A group's positions move
only while none of its consumers is running. The window shows each partition
before and after. **Delete group** removes a group and its positions, also
only while nobody reads in it.

## The Cluster section

At the top of the catalog, **Cluster** holds what the cluster says about
itself: **Cluster** (its id, the controller, and how many brokers, topics and
partitions), **Brokers**, **Broker settings** (the ones that differ from
Kafka's defaults) and **Partitions needing attention** (empty when all is
well). The first and the last refresh every ten seconds.

## Dashboards, search and downloads

- The **Kafka cluster** dashboard draws each group's lag, each topic's
  messages per second and the partitions needing attention, for the first
  hundred topics and groups by name.
- The search in the header finds topics and groups by name.
- **Download** on a topic saves the messages its page would show, with its
  filters and order, up to ten thousand from the end of each partition. A
  group downloads every position.

## A topic in a pipeline

A topic can sit in the middle of a pipeline: one link writes into it, and
others carry what arrives into tables.

- **Add rows** into a topic sends the rows as messages.
- **Add new messages to a table** reads only what arrived since that link's
  last run. It is the one way out of a topic in a pipeline: reading the whole
  topic again at every run would add the same rows again.
- Each such link reads as a consumer group of its own, named
  `dataplayer-link-` and the link's id, shown in the link's panel. Its lag is
  on the **Consumer groups** level, so you see how far the link is behind.
- **First run reads** chooses where the first run starts: from the beginning
  of the topic, or only messages that come after it. Once the group keeps a
  position, the choice changes nothing; to read again, move the group's
  positions.
- Each block of rows is written first and its position kept after. If a run
  fails between the two, the next run writes that block again: a message is
  never missed, and rarely arrives twice.
- **Add new messages to a new table**, drawn to a schema rather than a table,
  makes the table on its first run — name, columns and types chosen in its
  window — and adds to it after. If the table has the topic's partition and
  offset among its columns, it is made with a key on them where the database
  allows it (PostgreSQL, MySQL, MariaDB, SQLite), and a message written twice
  is kept once. A table removed later is not made again: move the group's
  positions to the start to read everything into a new one.
- **Keep the latest per key**, drawn to a Redis database or folder, keeps
  each message key's newest value as a key of its own, with a time to live
  if you choose one; see the Redis page.
- **Follow**, ticked in a link's panel, and **Follow** in the pipeline's head
  carry what arrives within seconds rather than at the next run. The pipeline
  looks every few seconds, keeps following after the server restarts, and Run
  and the schedule leave a followed link out meanwhile. A link that fails is
  tried again a little later while the others carry on.
- Messages Kafka deleted before the link read them are counted in the run's
  result.
- Kafka forgets a group's positions after a week without them being written,
  so a link that runs less often starts again as **First run reads** says.

## A Kafka of your own

**Services** can start a Kafka broker on this machine, if this server may run
containers. It asks for no password — a broker answers anybody who reaches it —
and is reached only from this machine. Its connection is made for you.

Ask for sample data to get a lab:

- `lab.orders` — three hundred JSON orders over one day in three partitions,
  keyed by customer;
- `lab.prices` — the latest price per symbol, a compacted topic;
- `lab.events` — text lines with headers;
- `lab.sensor` — readings stored as bytes, shown in hex;
- the group `lab-billing`, part way through `lab.orders`, so its lag shows.

A broker tells its clients where it is, and this one says the address it has
inside DataPlayer. The catalog, the terminal and pipelines reach it there; a
tool on your own computer reaches it only through the terminal.

## What Kafka does not have here yet

Copying topics to another connection and backups are not offered. Kafka's way
of copying is MirrorMaker, a service that keeps running, and its backup is the
brokers' log files; sending every message again would promise neither.
