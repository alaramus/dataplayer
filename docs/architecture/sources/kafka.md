# Kafka

What a Kafka source is, how it reaches a cluster, what its catalog shows of
topics and consumer groups, and how a topic's messages and a group's positions
are read as rows, how messages are sent and topics and groups changed
(D308, D309), the cluster's reports, metrics, search and export (D310), and
Kafka's own tools in a terminal (D307, run as D286
says in [terminals.md](../terminals.md)). The contract every source type follows is in
[contract.md](contract.md). Read this before changing the `kafka` adapter.

Decisions here: D304, D305, D306, D307, D308, D309, D310.

## D304. A Kafka source speaks to a cluster through confluent-kafka, a client per operation

The adapter uses confluent-kafka, the Python client on librdkafka. It is
synchronous and runs librdkafka's threads of its own, so one operation — make
the clients, ask, close them — is one call into the thread pool. No client is
kept between operations: a kept one holds a connection to every broker for
nobody. confluent-kafka is imported by `app.adapters.kafka` and nothing else,
which an import-linter contract holds.

Options are the brokers (`host:port`, comma-separated; the first that answers
tells the client of the rest), TLS with an optional CA certificate as PEM, and
one of four ways in: none, SASL PLAIN, SCRAM-SHA-256 or SCRAM-SHA-512 with a
user and password. The check describes the cluster.

A failure is reduced by librdkafka's error codes, never by its text, and the
errors librdkafka reported through its callback while the operation ran are
read first: a refused password or certificate is said there, while the request
that failed only times out. An admin client says nothing until it is polled,
so it is polled before the reduction. librdkafka's own log lines name brokers
and repeat once per retry; they go to the server's log at debug.

Known deviations:

- **No SSH tunnel** (D282): a client connects to the addresses the brokers
  advertise, not to the tunnel's end, and rewriting them inside the client is
  not something confluent-kafka offers.
- **No Kerberos, OAuth or client certificate** in the first version.
- **The broker's release is not shown**: Kafka's protocol does not say it.
- **A broker that does not answer costs the five-second limit**, since
  librdkafka retries until then rather than failing at the first refusal.

Spec: [A Kafka source](../../decisions/2026-11-01-kafka-source-design.md)

## D305. Topics, consumer groups and internal topics are three levels; each opens as rows

The top is three directories: Topics, Consumer groups, and Internal topics —
a name that starts with an underscore, as `__consumer_offsets` and `_schemas`
do. A level lists its first thousand by name. Node ids are `topic:<name>`, a
name in Kafka's own characters, and `group:<id>`.

- **A topic** is a `topic` node with its partitions and the offsets they span,
  end less start: an upper bound rather than a count, since compaction and
  transaction markers leave gaps. Its summary is each partition's leader,
  replicas, in-sync replicas and offsets, and the settings made on the topic
  itself; a value the broker keeps secret is said to be hidden.
- **A group** is a `consumer_group` node with its state — stable, no
  consumers, rebalancing, gone or unknown — and its members. It opens as a
  row per partition it has a position in or a member holds: topic, partition,
  committed offset, end offset, lag and the member, client and host reading
  it, in topic and partition order, refreshed every ten seconds. Its summary
  sums the lag and names its coordinator, assignor and topics. A group nobody
  made is described by Kafka as dead with nothing in it, and answers 404.
- **The cluster's whole metadata is read** even for one topic: asking for a
  topic by name creates it on a broker that creates topics it is asked about,
  which is Kafka's default. A topic that is not there is a 404 and stays not
  there.

Spec: [A Kafka source](../../decisions/2026-11-01-kafka-source-design.md)

## D306. A topic's messages are rows, newest first, read by assigned partitions

The columns are partition, offset, timestamp, key, value and headers, then
`value.<field>` for each top-level field of the newest two hundred messages
whose values are JSON objects, in the order met; a field's category is its
JSON type, and disagreement is a string. A field met on the page but not in
the sample is added to that page and offered for nothing, as a MongoDB page's
is (D284). A key and a value are text when they are UTF-8 and `0x…` hex
otherwise, cut at 65,536 characters; headers are a JSON object. The value
column is JSON when every sampled value is. A row's handle is
`partition:offset`; nothing is editable, since Kafka changes nothing in place.

Reading assigns partitions to a consumer and never subscribes, with automatic
commits off: a page joins no group and moves nobody's position. The consumer
reads committed messages only, so an aborted transaction is not shown.

The order is by timestamp, newest first, merged across partitions; ascending
starts from the oldest. Nothing else sorts. A page with offset N reads at most
N plus the page plus one from the chosen end of each partition, merges and
cuts, so `offset + limit` has a ceiling of ten thousand, past which the page
refuses and says to narrow by time or partition.

Where reading starts and stops is asked of Kafka: a partition (`eq`, `in`),
an offset range, and a time range, which `offsets_for_times` turns into
offsets. Every other filter — on the key, the value, the headers or a field,
text compared without regard to case and a number field by its value — is
applied to what was read, in chunks of five hundred read back from the end
until enough match, within a ceiling of a hundred thousand messages for the
page. Reading stops at a partition's end without waiting, because the
consumer is told when it reaches it, and a page gives up after ten seconds.

Known deviations:

- **Newest first means by offset inside a partition.** A producer may set
  times out of order; across partitions the order is by time.
- **The scan ceiling is not said on the page**: a filtered page that reached
  it says there may be more, and nothing else.
- **A message opens in the record panel (D111)**, its value a JSON cell, not
  as a document of its own.
- **Nothing on a page is editable or deleted**: a message is sent as a new
  row (D308), and messages leave a topic by Delete messages (D309).

Spec: [A Kafka source](../../decisions/2026-11-01-kafka-source-design.md)

## D307. The console is Kafka's own tools, each set up for the connection

A Kafka connection's terminal is bash in the `apache/kafka` image of the
release the test server runs (D286). Each tool that takes both
`--bootstrap-server` and `--command-config` is wrapped by a shell function of
its own name that adds the two for this connection, unless the command names
brokers or a controller itself: `kafka-topics.sh --list` lists this
connection's topics. The list of wrapped tools is the ones whose help in that
image names both flags; the rest are as Kafka ships them.

The client settings — security protocol, SASL mechanism and its JAAS line,
a CA certificate as a PEM truststore — are the adapter's own (D304), composed
by the server, the password quoted for JAAS and escaped again for the
properties format. They reach the container through its environment, are
written with `printf '%s'` into a file only its user may read, and the
variables carrying them are unset before the prompt. A greeting above it
names three commands to start from.

Known deviations:

- **The brokers must be reachable from the service network** under the
  addresses they advertise, as for any console (D286): a connection to
  `localhost` from the backend's point of view is not the container's.
- **The password is in a file inside the container** for as long as the
  terminal is open; the container is removed when it closes.
- **The wrapped tools are a list**, read off one release; a tool a later image
  adds runs as Kafka ships it until it is added.

Spec: [The Kafka console](../../decisions/2026-11-01-kafka-console-design.md)

## D308. A message is sent as a new row of its topic

Kafka appends and never changes, so of the grid's edits only insert means
anything: a topic implements `SupportsInsert`, and a message is the grid's new
row. The same capability takes a block, so pasting rows into a topic and a
pipeline's Add rows link into one (D166, D177) send messages with no code of
their own. Kafka's own topics take none, and say why.

The columns that may be filled are partition (empty is the partitioner's,
by key), timestamp (empty is now), key, value, headers and the
`value.<field>` columns of the page. When value is empty and fields are
given, the value is a JSON object of them, each read as its column's JSON
type. A key or a value written as `0x` and an even number of hex digits is
those bytes, the form a page shows them in; anything else is its UTF-8 text.
Headers are a JSON object of text. The row that comes back is the message as
the broker stored it, its handle `partition:offset`.

A block is read whole first: a cell that will not read — a partition the topic
does not have, a number field that is not a number, a time that is not one —
rejects the block with every such cell named, and nothing is sent. The block
is then sent by an idempotent producer acknowledged by all in-sync replicas,
and waited for up to thirty seconds.

Known deviations:

- **A block is not all or nothing at the broker**: a broker failing midway
  leaves the messages already acknowledged. A transaction would close that,
  and needs transactions and a transactional-id permission many clusters do
  not give a person browsing them.
- **Only fields the sample found are columns to send**: an empty topic takes
  key, value and headers until its first JSON message is read.

Spec: [Writing to Kafka](../../decisions/2026-11-01-kafka-writes-design.md)

## D309. Topics and groups are changed by actions, each with a preview

On the Topics level and for a topic in it: New topic (name, partitions, a
replication factor or the broker's default, settings as `name=value` lines),
Delete topic (several at once; the preview counts the messages and names the
groups with positions in it, asking the first hundred groups), Change
settings (opened with the settings made on the topic; a line taken away
returns that setting to the broker's default, changed by Kafka's incremental
call so nothing unnamed moves; the preview lists both), Add partitions (a
larger total; the preview warns that a key's partition may change), and
Delete messages (everything, or everything before a time, per partition by
`delete_records`; the preview counts what goes in each). On the Consumer
groups level and for a group: Move positions to the start, the end or a time,
for every topic the group has positions in or for one topic, all of whose
partitions it then has; the preview shows each partition's position now and
after and the lag after, and a group with consumers is refused, as Kafka would
refuse it. Delete group, added with D310, takes several at once, names each
partition's position and lag first, and is refused the same way. Kafka's own topics take no action, nor does the top.

A name that starts with an underscore is refused for a new topic: the catalog
keeps such names apart as Kafka's own (D305).

Known deviations:

- **A secret setting is not shown in Change settings and is never returned
  to the default** by it: the broker does not say its value.

Spec: [Writing to Kafka](../../decisions/2026-11-01-kafka-writes-design.md)

## D310. The cluster reports on itself, is measured, searched by name and exported

**Reports.** A Cluster section heads the top, before the three levels, as
ZooKeeper's Server section does (D301): Cluster (its id, the controller, and
the brokers, topics and partitions counted, with those short of in-sync
replicas and those without a leader), Brokers (a row each, address and rack,
the controller marked), Broker settings (the controller's that differ from
Kafka's defaults, a secret one said to be hidden) and Partitions needing
attention (each one short of replicas or leaderless; empty on a healthy
cluster). Each is the admin client's answer read as setting-and-value rows
(`report_rows`), so the grid, download and chart need nothing new; Cluster and
Partitions needing attention refresh every ten seconds. Report ids are
`report:<key>` and the section's is `cluster`.

**Metrics** (D128). One poll reads the metadata, every polled partition's end
offset and each polled group's positions: `lag` by group (messages behind,
summed), `messages` by topic (end offsets summed, a counter, so its rate is
messages per second) and `cluster` (brokers, partitions, short, offline). The
first hundred topics and groups by name are polled, which the preset says;
Kafka's own topics are not.

**Search and kept names** (D202, D213). Every topic and group is two requests,
so a name search reads them all and is cheap; a search started on a level
stays on it. A found topic is given its message count. The kept list is every
topic and group, each scoped to its level.

**Export.** A topic exports what its page would show, with the page's filters
and order, to the page's depth: ten thousand messages from the chosen end of
each partition. A group's positions and a report export whole; positions are
not filtered or sorted.

Known deviations:

- **An export of a topic stops at the depth ceiling**: Kafka has no cursor
  that goes further without reading every message from the start.
- **A cluster with more than a hundred topics or groups is measured in part.**

Spec: [Kafka's reports, metrics, search and export](../../decisions/2026-11-01-kafka-reports-design.md)
