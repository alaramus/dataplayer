# Kafka's reports, metrics, search and export

Decision D310. The fourth slice of the Kafka source, and a change to the third:
deleting a consumer group, which the user asked for after D309 left it out.

## Deleting a group

Delete group joins Move positions on a consumer group: several at once, the
preview naming each partition's position and lag, refused while the group has
consumers — Kafka refuses that too, and saying so before the request is
clearer than its error. The consumers that come later start by their own
`auto.offset.reset`, which the question says.

## Reports

A Cluster section at the top, beside the three levels, as ZooKeeper's Server
section is (D301). Its reports are the admin client's answers read as
setting-and-value rows, the shape every source's reports have, so the grid,
its download and chart need nothing new:

- **Cluster** — its id, the controller, and counts: brokers, topics,
  partitions, partitions short of replicas, partitions without a leader;
- **Brokers** — one row per broker, its address and rack, the controller
  marked;
- **Broker settings** — the controller's settings that differ from Kafka's
  defaults, secret ones hidden;
- **Partitions needing attention** — every partition short of in-sync replicas
  or without a leader, with what it has. Empty on a healthy cluster, which is
  the answer people open it for.

## Metrics

What monitoring a Kafka cluster first asks: how far each group lags, and how
fast each topic grows. One poll is the metadata, the end offsets of every
partition and each group's positions:

- `lag` by group — messages behind, summed;
- `messages` by topic — the end offsets summed, as a counter, so its rate is
  messages per second;
- `cluster` — brokers, partitions, partitions short of replicas, offline.

The first hundred topics and groups by name are polled; a cluster with more is
measured in part, which the preset's description says.

## Search and kept names

Kafka has no index over names, but it has no tree either: every topic and
group is two requests. So searching names is cheap, as a MongoDB's is, and
the kept list is every topic and group, each scoped to its level.

## Export

A topic's export is the page's read with its filters and order, to the same
depth ceiling a page has — ten thousand messages from the chosen end of each
partition — streamed in batches. Kafka has no cursor that could go further
without reading every message from the start; a person who needs the whole
log has the console's consumer. A group's positions and a report export
whole.
