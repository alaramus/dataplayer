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
- Kafka's own tools, set up for the connection, in a terminal

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
