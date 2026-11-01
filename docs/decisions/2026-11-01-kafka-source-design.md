# A Kafka source

Decisions D304, D305 and D306. The first slice of a Kafka source type: a
connection to a cluster, its topics and consumer groups in the catalog, a
topic's messages as rows and a group's position as rows. The later slices are
listed at the end; each gets its own spec and commit, on the branch
`kafka-adapter`.

Kafka is the first source that is a log rather than a store: what is in a
topic is never changed in place, only appended to and, past its retention,
dropped from the front. A message is named by its partition and offset, and
every reader keeps its own position.

## Why Kafka, and not RabbitMQ or ZeroMQ

The source type is the queue a user brings, so it has to be something that can
be connected to and looked at:

- ZeroMQ — rejected: a socket library with no server, no topics and nothing
  kept; there is nothing for a connection to name.
- RabbitMQ — not first: a queue hands a message to one consumer and forgets
  it, so a queue cannot be read without being drained, and reading is what the
  catalog, the grid, search and export are built on. It may come later as a
  second source of the same family.
- Kafka — chosen: a topic keeps its messages for its retention and can be read
  from any position as often as wanted, without disturbing anybody reading it.
  That is a relation of rows the grid already shows.

Kafka's place in pipelines — a topic written by one link and read by several,
each into its own target — is not in these slices. It rests on a topic being a
source like any other first, and gets its own spec.

## What the user chose

Asked before the work began:

- Opening a topic: its newest messages first, across partitions; from the
  start, from a time or from an offset in a partition as choices beside it.
- Writing in the first version: sending a message; making and deleting a
  topic, changing its settings and adding partitions; moving a consumer
  group's positions; deleting the records before an offset.
- The console: Kafka's own command-line tools in a terminal (D286), set up for
  the connection.
- Avro and Protobuf through a Schema Registry: a slice of its own, after the
  main ones. Until then a value is text, JSON or bytes.

## The client and the connection (D304)

Two clients were weighed:

- aiokafka, asynchronous and in pure Python — rejected: its admin client covers
  less of what the writes and reports need, and it brings no Schema Registry
  client, which the later slice needs;
- confluent-kafka, on librdkafka — chosen: the fullest admin API, every SASL
  mechanism, the Schema Registry client in the same package, and wheels for
  Python 3.14 on Windows and Linux. It is synchronous, which the thread pool
  answers, as for kazoo.

A client per operation, as ZooKeeper has a session per operation: an admin
client or a consumer is made, asked and closed inside one call in the thread
pool. A client kept open would need a lifetime in the resource store and keeps
librdkafka's threads and broker connections alive for nobody.

The connection names bootstrap servers (`host:port`, comma-separated), a
security protocol (plaintext, TLS, SASL, SASL over TLS), a SASL mechanism of
PLAIN, SCRAM-SHA-256 or SCRAM-SHA-512 with a user and password, and for TLS a
CA certificate and optionally a client certificate and key. Kerberos and
OAuth are not in the first version.

No SSH tunnel (D282): a client is told by the first broker where every broker
is, and connects there — the brokers' advertised addresses, not the tunnel's
end. Carrying that through a tunnel means rewriting broker addresses inside
the client, which confluent-kafka does not offer.

## Topics and groups in the catalog (D305)

The top holds three levels: Topics, Consumer groups, and Internal topics —
`__consumer_offsets` and the like, which a person rarely means to open and
which would otherwise sit among their own.

A topic is a kind of its own, `topic`, carrying its number of partitions and
messages. It is opened for its messages (D306) and its summary shows its
partitions — leader, replicas, in-sync replicas, first and end offset — and
the settings that differ from the broker's default.

A consumer group is a kind of its own, `consumer_group`, carrying its state and
number of members. It is opened as rows of where it stands: topic, partition,
committed offset, end offset, lag, and the member that holds the partition.
The lag is the number people come to Kafka screens for.

## A topic's messages as rows (D306)

The columns are fixed first — partition, offset, timestamp, key, value,
headers — then, when the newest two hundred messages' values are JSON objects,
their top-level fields in the order met, as a MongoDB collection's fields are
found (D284). A key and a value are text when they are UTF-8, and `0x…` hex
otherwise; headers are a JSON object. A message's row handle is
`partition:offset`; a row is never edited, because Kafka cannot change one.

Reading never joins a group and never commits: partitions are assigned to the
consumer directly. A person looking at a topic must not appear as a consumer of
it, nor move anybody's position.

The order is by timestamp, newest first, merged across partitions; ascending
is the start of the topic. A page with offset N reads at most N plus the page
from the end of each partition, merges and cuts — so the depth a page may
reach has a ceiling, ten thousand messages, past which the page refuses and
says to narrow by time or partition. The filters that steer where reading
starts are served by Kafka itself: a timestamp from a moment is
`offsets_for_times`, a partition and an offset in it start there. Filters on
the key, the value and its fields are applied to what was read, inside a
ceiling of messages scanned that the page says it reached.

A message also opens as a document, its value as a JSON tree when it is JSON.

## The slices

1. This spec: the connection, the catalog, messages and a group's position as
   rows, the summaries. Test server `apache/kafka` 4.1 in KRaft mode in
   docker compose, with two listeners: one for the host and one for the
   backend container, since each must be told an address it can reach.
2. Kafka's tools in a terminal: the `apache/kafka` image with the connection's
   settings written to a client properties file at start, the password passed
   through the environment.
3. Writes: sending a message as a new row; making, deleting and changing a
   topic and adding partitions; moving a group's positions (to the start, the
   end, a time or an offset, only while the group has no members, with a
   preview of the lag each partition will have); deleting records before an
   offset, with a preview of what goes.
4. Reports, metrics, search and export: brokers and the cluster's settings as
   reports; lag per group and messages per second per topic as metrics; topic
   and group names kept for search; a topic's window exported.
5. A Kafka started here: a service template, a lab of topics with JSON
   messages and a group behind, the guide in every language.
6. Following a topic: new messages appear on an open page as they arrive
   (D303).
7. Schema Registry: Avro, Protobuf and JSON Schema values decoded into
   columns.
