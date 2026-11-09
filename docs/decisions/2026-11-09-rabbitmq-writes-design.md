# Writing to RabbitMQ: messages, queues, exchanges, bindings and a look inside a queue

Decisions D329 and D330. The third slice of the RabbitMQ source: sending
messages, making and deleting what the catalog shows, binding and purging,
and Peek — the one way a queue's own messages are shown (D326).

## Sending a message (D329)

A stream's page is its messages, so a message sent to a stream is a new row of
that page, as a topic's is (D308): the grid's **+**, a paste, and a pipeline's
Add rows write into it. It goes through the default exchange with the stream's
name as its routing key. The columns it is sent with are timestamp, content
type, headers, properties and body, and the body's fields; the offset, the
exchange and the routing key are the stream's to say. A body written `0x…` is
those bytes; an empty body with fields filled is a JSON object of them; headers
and properties are JSON objects, the properties limited to what AMQP names
(message id, correlation id, reply-to, priority, expiration, type, app id,
delivery mode). A block is read whole before anything is sent, so one cell
that will not read rejects it with the cell named; then it is published on a
channel with publisher confirms and every message waited for. No
transaction: a block that fails half way has sent its first half, as Kafka's
does.

A queue's and an exchange's page is their bindings, not messages, so a message
for them is the **Publish** action: an exchange with a routing key, a queue
through the default exchange by its name. Its form is a routing key (for an
exchange), a body, a content type and headers. A message an exchange routes
to no queue is lost; the publish is made mandatory, and an unroutable one is
said rather than counted as sent.

## Making, deleting, binding, purging (D330)

Every change goes through the management API, as the catalog's reads do
(D325): a `PUT` declares, a `DELETE` removes, and the broker's own refusal is
said in this repository's words.

- **New queue** on the Queues level: a name, classic or quorum, durable (a
  quorum queue always is), and arguments, one `name=value` per line, a value
  read as JSON when it is one (`x-max-length=1000` is a number).
- **New stream** on the Streams level: a name, a maximum age (`7D`, `12h`) and
  a maximum size in bytes, each optional, and other arguments.
- **New exchange** on the Exchanges level: a name, a type, durable, internal.
- **Delete** a queue, stream or exchange; the preview says how many messages go,
  who consumes, and how many bindings go with it. `amq.*` and the default
  exchange are not deleted.
- **Bind** on an exchange (to a queue or exchange, chosen from the virtual
  host's) or on a queue (from an exchange, chosen); a routing key and
  arguments. **Unbind** chooses one of the node's own bindings.
- **Purge** a queue: the preview says how many ready messages go; taken and
  unacknowledged ones stay with their consumers. A stream is not purged.

A name is checked against RabbitMQ's own limit — up to 255 bytes of UTF-8,
not starting with `amq.` — and the broker refuses a name it already has with
other settings, which is said as such.

## Peek (D330)

The management API's `get` with `ack_requeue_true` takes up to N messages and
puts them back. That is a delivery: each comes back marked redelivered, a
quorum queue counts it towards its delivery limit, and a consumer may see the
messages out of their order. So Peek is an action with a warning in its form
and its confirmation, never a representation a click opens, and a look is
taken once:

- The messages read are kept by the server as a snapshot, in the resource
  store, for the connection — up to twenty snapshots, until the store lets
  them go — and the action's result names the snapshot as a node to open.
  Paging, sorting or refreshing it reads the snapshot, never the queue.
- `ActionResult` gains `open_node_id`: a node the client opens as soon as the
  action is done. `created_node_id` stays what it was — something made, for
  the client to offer — and is not overloaded with a node that is only a
  record of a look.
- A snapshot is a `report` node, `peek:<v>/<queue>/<n>`, named after the queue
  and the time; its rows are position, redelivered, exchange, routing key,
  content type, headers, properties, body and the body's fields. Once the
  store has let it go it is a missing node, and the way back is to peek again.
- At most a hundred messages at a time; a stream is refused, since its own
  page reads without taking.

## The slices that remain

Reports, metrics, search and export (4) and the service template with its lab
(5), as the source spec lists them; then RabbitMQ in pipelines.
