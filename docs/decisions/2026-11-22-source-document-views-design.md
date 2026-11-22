# Kafka and RabbitMQ document views

Decision D444 extends D419–D421 for sources whose useful facts are not always
owned as JSON. A source may offer a `view` without `tree` when it has bounded
typed protocol facts but no source JSON document. When it does have a suitable
bounded JSON resource, it offers the view first, that JSON second, then keeps
its existing representations in order.

## Kafka topic

Kafka's topic metadata, offsets and configuration arrive as typed results from
the Kafka protocol. Serializing the adapter's summary into JSON would create an
artificial document and mislabel it as source data. A topic therefore declares
`[view, table]`: its card is built from the existing `KafkaTopicContents` used
by the node summary, and the messages table remains unchanged. It does not
offer a JSON tree.

The card shows each partition's leader broker, replicas, in-sync replicas,
first offset and end offset, followed by topic settings that differ from the
broker defaults. A value Kafka masks stays hidden. Messages remain rows in the
existing table representation.

## RabbitMQ resources

The Management API already answers a queue, stream or exchange as a JSON
resource. Each declares `[view, tree, table]`, with the existing bindings table
for queues and exchanges or messages table for streams last. The card maps the
same Management API answer into the adapter's existing summary types; reading
the view makes one request, and reading the tree returns the API's JSON from
one request. The returned tree is built only when the resource body fits
D295's 4 MB ceiling; a larger source document is shown as a bounded preview
with a notice.

- A queue card shows its queue type and state, total, ready and unacknowledged
  messages, consumer count and details, in/out rates, node, policy and
  arguments.
- A stream card shows its state, message and segment counts, consumers,
  incoming rate, first-message time, leader and members, policy and arguments.
- An exchange card shows its type, published and routed message counts,
  durable, auto-delete and internal flags, in/out rates and arguments.

Only facts RabbitMQ returns for that resource are shown. Missing nodes and a
queue/stream type mismatch keep the source's existing not-found behavior.
Actions retain their catalog entries and, where marked for views, appear in
the generic view head as D424 defines.

## Client and limits

The existing `DocumentView` block contract and universal `ViewPanel` cover
these cards. No Kafka- or RabbitMQ-specific frontend renderer is added. Cards
use the existing row, pair, chip and text limits; tables keep at most 500
rows, lists and pairs at most 500 items, and text at most 16 KB. The existing
message and binding table semantics, catalog links, searches, summaries and
stored tabs remain as defined by their source contracts.

The corresponding adapter documentation is in
[views.md](../architecture/sources/views.md),
[kafka.md](../architecture/sources/kafka.md) and
[rabbitmq.md](../architecture/sources/rabbitmq.md).
