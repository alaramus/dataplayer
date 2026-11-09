# RabbitMQ

A RabbitMQ broker. You see its virtual hosts, queues, streams and exchanges,
how many messages wait and who takes them, and read a stream's messages as
rows. How connections work in general is on the [Connections](connections.md)
page.

## What you can see

- Virtual hosts, and in each its queues, streams and exchanges
- How many messages wait in a queue, and how many are taken but not confirmed
- Who consumes from a queue, and messages in and out per second
- What is bound to what: a queue's exchanges, an exchange's queues
- A stream's messages as rows, newest first, from an offset or a moment
- The fields of JSON messages, each in a column of its own
- A stream's messages or the bindings downloaded as a file

## What you can change

- Nothing yet: this version only reads

## Connecting

The **Connection** page of the window asks for:

- **Host** and **AMQP port**: where the broker takes AMQP, 5672 by default,
  5671 with TLS;
- **Management address**: where its management API answers. Empty means
  `http://` the host and port 15672, or `https://` with TLS. RabbitMQ answers
  there only with its management plugin on; the official `-management` images
  have it;
- **User** and **Password**: one RabbitMQ user for both;
- **Virtual host**: empty for every virtual host the user may see, or one
  name, such as `/`;
- **TLS** and **CA certificate**: an encrypted connection, and the authority
  that signed the broker's certificate when the system does not trust it.

A connection string `amqp://user:password@host:5672/vhost` fills the form;
`amqps://` is TLS, and `%2F` in the path is the virtual host `/`.

The check asks the management API first and AMQP after. When only AMQP
refuses — a virtual host the user may not open, a port not reachable — the
connection is still saved and says why: the catalog works, a stream's messages
do not. An SSH tunnel is not supported.

## The catalog

- With several virtual hosts, the top lists them; with one, or with one named
  in the connection, the top is its **Queues**, **Streams** and **Exchanges**.
- A queue says its type (classic or quorum), how many messages wait, how many
  are taken and not yet confirmed, and how many consumers it has.
- A stream says how many messages it keeps and who reads it.
- An exchange says its type: direct, topic, fanout or headers. Your exchanges
  come first, then the ones RabbitMQ makes in every virtual host; the default
  exchange, which has no name, is **(default)**.
- The counts are RabbitMQ's own, measured every few seconds, so a number may
  lag a moment behind.
- A level shows its first five hundred by name.

## A queue and an exchange

A queue keeps a message until a consumer takes it, then forgets it, so its
messages are not shown: reading them would take them away.

- A queue opens as its bindings: the exchange that routes to it, the routing
  key and the arguments. Every queue is bound to the default exchange by its
  own name.
- An exchange opens as where it routes: the queue or exchange, the routing key
  and the arguments.

## A stream's messages

A stream keeps its messages for its retention, like a log, and anybody may read
it from any place without taking anything.

- One row per message: its offset, its time, the exchange and routing key it
  came by, its content type, headers, other properties and body.
- When the bodies are JSON objects, each field is a column too, named `body.`
  and the field. The fields come from the newest two hundred messages.
- A body that is not text is shown in hex.
- Newest first. Sort by **offset** to start from the oldest; no other column
  sorts.
- **timestamp** is the time the sender put on the message, empty when it put
  none. Filtering it "from" a moment starts reading where the stream itself
  received that moment, to the nearest chunk of messages.
- Filter by **offset** to choose where reading starts and stops.
- Filters on the other columns look through the messages read, up to a
  hundred thousand for one page.
- A page reaches at most ten thousand messages from the end. To look further
  back, filter by offset or time.
- Reading a stream takes nothing from it and moves nobody's place.

## The details panel

Select a queue, a stream or an exchange and choose **Details** in the
catalog's menu.

- A queue: its type, state, messages waiting and unconfirmed, messages in and
  out per second, its node and policy, each consumer with its channel and
  prefetch, and the arguments it was made with.
- A stream: its messages, segments, messages in per second, when its oldest
  kept message arrived, its leader and members, its consumers and arguments.
- An exchange: its type, whether it survives a restart, is deleted when unused
  or is internal, and its messages in and out per second.

## Downloads

**Download** on a stream saves the messages its page would show, with its
filters and order, up to ten thousand. A queue or an exchange downloads its
bindings.
