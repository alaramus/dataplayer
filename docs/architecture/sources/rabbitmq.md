# RabbitMQ

What a RabbitMQ source is, how it reaches a broker through its two doors, what
its catalog shows of virtual hosts, queues, streams and exchanges, and how a
stream's messages and the bindings are read as rows. The contract every source
type follows is in [contract.md](contract.md); the other queue is in
[kafka.md](kafka.md). Read this before changing the `rabbitmq` adapter.

Decisions here: D325, D326, D327.

## D325. A RabbitMQ source looks through the management API and moves messages over AMQP

Two clients, each for what it does. The management HTTP API, through httpx,
answers everything looked at: virtual hosts, queues, exchanges, bindings,
consumers, counts and rates. AMQP 0-9-1, through aio-pika, moves messages:
reading a stream now, sending and a pipeline's reading later. Both open per
operation and close after it; a kept AMQP connection would hold a socket and a
heartbeat for nobody. aio-pika, aiormq and pamqp are imported by
`app.adapters.rabbitmq` and nothing else, which an import-linter contract holds.

Options are a host, the AMQP port (5672, 5671 with TLS), the management
address (empty is `http://<host>:15672`, `https` with TLS), one user and
password for both doors, a virtual host (empty is every one the user may see),
TLS and a CA certificate as PEM. A connection string is
`amqp://user:password@host:port/vhost`, `amqps://` for TLS, the path the
virtual host percent-encoded.

The management plugin is required. The check asks `GET /api/whoami` first: no
answer there fails the check and says the plugin is needed. AMQP is opened
after; when only it refuses, the check passes with that said, so the catalog
works and what moves messages refuses with the AMQP reason.

A failure is reduced by the HTTP status or aiormq's exception class, never by
text: 401 and `ACCESS_REFUSED` are the connection refused, 403 is not allowed,
a closed connection at `open` is a virtual host refused, `NOT_FOUND` on a
named node is a missing node. aiormq's own error lines name the address and
are silenced; the reduction logs once.

Known deviations:

- **No SSH tunnel** (D282): a tunnel carries one port, and this source needs
  two. Two forwards through one SSH session may come later.
- **No client certificate, OAuth 2 or list of cluster nodes** in the first
  version; one node serves the whole cluster's state.
- **The management API's client is not kept** between requests, though the
  spec said it would be, as ClickHouse's is: a catalog asks a few times a
  minute, and a client in the resource store is a lifetime to manage for a
  handshake saved.

Spec: [A RabbitMQ source](../../decisions/2026-11-09-rabbitmq-source-design.md)

## D326. Virtual hosts, then queues, streams and exchanges; a queue and an exchange open as bindings

With several virtual hosts the top lists them; with one, or one named in the
connection, the top is its three levels: Queues, Streams and Exchanges. A node
of a virtual host other than the one the connection names is missing. Node ids
carry the virtual host and the name percent-encoded, joined by `/`:
`vhost:<v>`, `queues:<v>`, `queue:<v>/<n>`, `stream:<v>/<n>`,
`exchange:<v>/<n>`. A name is any text RabbitMQ allows, so it is checked
against the broker's own answer, never against a pattern. A level lists its
first five hundred by name, the largest page the API serves.

- **A queue** is an `amqp_queue` node with its type in RabbitMQ's word
  (classic, quorum, a plugin's), its state, messages ready and unacknowledged,
  and its consumers. It is not opened for its messages: a queue hands one out
  and forgets it. It opens as rows of its bindings — exchange, routing key,
  arguments — the default exchange's implicit one by its name included.
- **A stream** is an `amqp_stream` node with its messages and consumers,
  opened for its messages (D327).
- **An exchange** is an `exchange` node with its type and whether it is
  durable or internal. The user's come first, then the default exchange, shown
  as `(default)`, and the `amq.*` ones, marked as the system's. It opens as
  rows of where it routes: destination, its type, routing key, arguments. The
  API lists the default exchange's bindings under `amq.default`.

A summary is what the management API last measured: counts, rates in and out,
the node or leader and members, the policy, each consumer with its channel,
prefetch and whether it acknowledges, and the arguments the node was declared
with. RabbitMQ samples every five seconds by default, so a count may lag.
A missing queue's bindings are answered by the API with none rather than a
404, so the node is asked for first.

Spec: [A RabbitMQ source](../../decisions/2026-11-09-rabbitmq-source-design.md)

## D327. A stream's messages are rows, newest first, read from an offset

The columns are offset, timestamp, exchange, routing key, content type,
headers, the other properties as a JSON object, and the body; then, when the
newest two hundred bodies are JSON objects, their top-level fields as
`body.<field>`, as a topic's are (D306). A body is text when it is UTF-8 and
`0x…` hex otherwise. The timestamp is the publisher's own property, empty when
none was set. A row's handle is its offset; nothing is edited.

A read is a consumer on a channel with a prefetch, started at
`x-stream-offset` and cancelled once it has what it came for, a pause in
delivery being the stream's end. A stream consumer's acknowledgement only
grants credit, so reading takes nothing and stores no position. The node is
checked to be a stream through the management API before any consumer
starts: the same consumer on a classic or quorum queue would take its messages
for good.

Order is by offset, newest first; ascending is the start of the stream. AMQP
does not say where a stream ends, so the end is learned by reading from
`last`, the start of its last chunk. A page reaches ten thousand messages from
its end at most. Offset bounds are where reading starts and stops; a moment
`from` is served by the stream as `x-stream-offset` given a time; every other
filter is applied to what was read, within a hundred thousand messages a page.
Export writes what the page would show, to its depth.

Known deviations:

- **A moment is the stream's arrival time, to a chunk**, while the timestamp
  column is the publisher's: only `gte` and `gt` are offered on it, since an
  upper bound would need every message's own time.
- **Learning the end costs a read** of the last chunk on every page.
- **A message does not open as a document** yet, as a topic's does not.

Spec: [A RabbitMQ source](../../decisions/2026-11-09-rabbitmq-source-design.md)
