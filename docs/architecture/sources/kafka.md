# Kafka

What a Kafka source is, how it reaches a cluster, what its catalog shows of
topics and consumer groups, and how a topic's messages and a group's positions
are read as rows. The contract every source type follows is in
[contract.md](contract.md). Read this before changing the `kafka` adapter.

Decisions here: D304, D305, D306.

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

Spec: [A Kafka source](../../decisions/2026-11-01-kafka-source-design.md)
