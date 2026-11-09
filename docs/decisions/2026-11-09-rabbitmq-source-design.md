# A RabbitMQ source

Decisions D325, D326 and D327. The first slice of a RabbitMQ source type: a
connection to a broker, its virtual hosts, queues, streams and exchanges in the
catalog, a stream's messages as rows and a queue's and an exchange's bindings as
rows. The later slices are listed at the end; each gets its own spec and
commit, on the branch `rabbitmq-adapter`.

RabbitMQ is the second queue after Kafka (D304), and a different one. An
exchange keeps nothing: it routes a message to the queues bound to it at that
moment, and drops it when none is. A queue keeps a message until a consumer
takes and acknowledges it, then forgets it — so it can hold millions while
nobody reads, but it has no history and cannot be read without being drained. A
stream, a queue type since 3.9, is a log like a Kafka topic: kept for its
retention and read from any position by any number of readers.

So what the catalog shows of a queue is its state — how many messages wait,
how many are taken and not yet acknowledged, who consumes, how fast — and only
a stream is opened for its messages. RabbitMQ's main use here is pipelines,
which come after these slices with a spec of their own.

## What the user chose

Asked before the work began, all as recommended:

- A queue's messages are not opened by a click. Looking at them is an action,
  Peek, with a warning (slice 3): RabbitMQ can only hand a message out and take
  it back, which marks it redelivered and, in a quorum queue, counts towards
  the delivery limit after which it is dead-lettered or dropped.
- The management plugin is required. The catalog, the counts and the reports
  come from its HTTP API; AMQP alone can only send and receive.
- A console: `rabbitmqadmin` in a terminal, a slice of its own (slice 2).

## The clients and the connection (D325)

Two protocols, each for what it does:

- the management HTTP API, through httpx, for everything that is looked at:
  virtual hosts, queues, exchanges, bindings, consumers, counts and rates,
  the overview and the nodes. One client per connection, kept as ClickHouse's
  is;
- AMQP 0-9-1, through aio-pika, for what moves messages: reading a stream,
  and in the later slices sending, peeking and a pipeline's reading. A
  connection per operation, opened, used and closed inside one call, as Kafka
  has a client per operation. A connection kept open would need a lifetime in
  the resource store and holds a socket and a heartbeat for nobody.

Weighed and rejected:

- pika — synchronous; aio-pika is asynchronous, as the backend is, and needs no
  thread pool;
- RabbitMQ's AMQP 1.0 Python client — young, and built on a synchronous Qpid
  Proton binding;
- the stream protocol (port 5552, `rstream`) — a second port and plugin a
  broker may not expose, and like Kafka it is told the nodes' advertised
  addresses rather than the one dialled. AMQP 0-9-1 reads a stream from an
  offset, which is all the first slices need.

The connection names a host, the AMQP port (5672, 5671 with TLS), the
management address (by default `http://<host>:15672`, `https` with TLS), a
user and password used for both, an optional virtual host, and for TLS a CA
certificate. An empty virtual host means every virtual host the user may see.
A client certificate, OAuth 2 and a list of cluster nodes to fall back to are
not in the first version; one node of a cluster serves the whole cluster's
state and routes to every queue.

Testing a connection asks both: `GET /api/whoami` and an AMQP open of the
connection's virtual host (or `/`). When the management API answers and AMQP
does not, the connection is saved with that said: the catalog works, and
anything that moves messages refuses with the AMQP reason. When the management
API does not answer, the test fails and says the plugin is needed.

No SSH tunnel in the first version (D282): a tunnel carries one port, and this
source needs two. It may come later as two forwards through one SSH session.

Errors are reduced to a kind and a safe message (D21): an HTTP 401 or 403, an
AMQP `ACCESS_REFUSED` or `NOT_FOUND` and a closed channel become a refusal or a
missing node; the URL with its credentials and the driver's text never reach
the caller.

## Virtual hosts, queues, streams and exchanges in the catalog (D326)

When the connection names no virtual host and the user sees more than one, the
top holds one level per virtual host; otherwise the top is that virtual host's
contents. A virtual host holds three levels: Queues, Streams and Exchanges.
Streams are apart from queues because only they are opened for messages.

- A queue is a kind of its own, `amqp_queue`, carrying its type (classic or
  quorum), its state, the messages ready and unacknowledged, and its consumers.
  It is opened as rows of its bindings — the exchange, the routing key, the
  arguments — and its summary shows the counts, the rates in and out, its
  arguments and policy, its consumers with their channel and prefetch, and the
  node it lives on.
- A stream is a kind of its own, `amqp_stream`, carrying its messages and size.
  It is opened for its messages (D327); its summary shows its retention
  arguments, its segments, its consumers and its members.
- An exchange is a kind of its own, `exchange`, carrying its type (direct,
  topic, fanout, headers or a plugin's) and whether it is durable or internal.
  It is opened as rows of its bindings out — the destination, whether a queue
  or an exchange, the routing key, the arguments. The default exchange, whose
  name is empty, is shown as `(default)`; it binds every queue by its name
  implicitly, so its rows are read from the queues, not from the API, which
  lists none. The `amq.*` exchanges every virtual host is made with are listed
  after the user's own.

A name in RabbitMQ is any UTF-8 text up to 255 bytes, `/` and spaces included,
so a node id carries the virtual host and the name percent-encoded, and a name
from a client is checked against the broker's own listing before any call, as
Binance's symbols are (D317) — never against a pattern.

The counts are the management API's, refreshed by its stats interval (five
seconds by default); a summary says when they were taken.

## A stream's messages as rows (D327)

The columns are fixed first — offset, timestamp, exchange, routing key,
content type, headers, properties, body — then, when the newest two hundred
bodies are JSON objects, their top-level fields in the order met, as Kafka's
values are (D306). A body is text when it is UTF-8 and `0x…` hex otherwise;
headers and the remaining properties (message id, correlation id, reply-to,
priority, expiration, type, user id, app id) are JSON objects. The timestamp is
the message's own property, empty when the publisher set none: AMQP 0-9-1 does
not tell a reader when the stream received a message. A row's handle is its
offset; a row is never edited, because a stream cannot change one.

Reading is a consumer with a prefetch and a tag of its own, started at an offset
given in `x-stream-offset` and cancelled once the page is read. A stream
consumer's acknowledgements only grant credit: reading takes nothing from
anybody and stores no position.

The order is by offset, newest first; ascending is the start of the stream. A
page with offset N starts N plus the page before the end — the end learned by a
read from `last` — so the depth a page may reach has the same ceiling as
Kafka's, ten thousand messages, past which the page refuses and says to narrow
by time. A timestamp from a moment is served by the stream itself, as
`x-stream-offset` given a time, to the precision of a chunk; filters on the
routing key, the body and its fields are applied to what was read, inside a
ceiling of messages scanned that the page says it reached.

A message also opens as a document, its body as a JSON tree when it is JSON.

## The slices

1. This spec: the connection, the catalog, a stream's messages and the
   bindings as rows, the summaries. Test server `rabbitmq:4.3.7-management` in
   docker compose, with a published AMQP and management port for the host and
   the service name for the backend.
2. The console: `rabbitmqadmin` version 2 in a terminal (D286) — the official
   images moved to it from the Python version; which image carries it is
   checked when the slice starts — set up for the connection's management address,
   user and virtual host, the password through the environment.
3. Writes: a message published as a new row, to an exchange with a routing key
   or to a queue through the default exchange, so pasting and a pipeline's Add
   rows write into RabbitMQ; making and deleting a queue, a stream, an exchange
   and a binding; purging a queue, with a preview of how many go; Peek, with the
   warning above, the messages taken back.
4. Reports, metrics, search and export: the overview, the nodes and their
   alarms, connections and channels as reports; messages ready, unacknowledged
   and the rates per queue as metrics; names kept for search; a stream exported
   to its page's depth.
5. A RabbitMQ started here: a service template, a lab of exchanges, queues and
   a stream with JSON messages and a queue nobody consumes, the guide in every
   language.

Then RabbitMQ in pipelines, with its own spec: a queue read by a link that
acknowledges a message only once it is written (at least once), through a queue
of the link's own bound to an exchange so as to take nothing from other
consumers; a stream read on from a bookmark, as a topic is (D312); an exchange
as a link's target.
