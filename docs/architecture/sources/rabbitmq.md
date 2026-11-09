# RabbitMQ

What a RabbitMQ source is, how it reaches a broker through its two doors, what
its catalog shows of virtual hosts, queues, streams and exchanges, and how a
stream's messages and the bindings are read as rows, and `rabbitmqadmin` in a
terminal (D328, run as D286 says in [terminals.md](../terminals.md)), how
messages are sent (D329) and queues, streams, exchanges and bindings changed,
with a look inside a queue (D330), and the broker's reports, metrics and
search (D331), and a RabbitMQ started here with its lab (D332). The contract every source
type follows is in [contract.md](contract.md); the other queue is in
[kafka.md](kafka.md). Read this before changing the `rabbitmq` adapter.

Decisions here: D325, D326, D327, D328, D329, D330, D331, D332.

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
- **A new row shows no offset** until the page is read again: AMQP does not
  tell a publisher where a stream put its message.

Spec: [A RabbitMQ source](../../decisions/2026-11-09-rabbitmq-source-design.md)

## D328. The console is rabbitmqadmin 2, its node written into a file from the environment

The terminal is bash in the `rabbitmq:<release>-management` image of the test
server's release, whose `rabbitmqadmin` 2 is a client of the same management
API the catalog reads, with its own bash completion. `rabbitmqctl` and
`rabbitmq-diagnostics` are not offered: they speak Erlang distribution, which
needs the node's cookie and a port a broker does not expose to clients.

The connection is one `[default]` node of a TOML file the server composes —
the management address, user, password, the connection's virtual host or `/`,
`tls` for an `https` address and the CA bundle — every value a TOML basic
string with its quote, backslash and control characters escaped. It reaches
the container in a variable, is written with `printf '%s'` under `umask 077`,
and the variable is unset before the prompt, as Kafka's settings are (D307);
`RABBITMQADMIN_CONFIG_FILE_PATH` names the file, so a command uses the
connection unless it names another node or address.

Known deviations:

- **Commands print wide tables**: `rabbitmqadmin` lists every column, and
  `--table-style borderless` is the narrowest of its styles.

Spec: [The RabbitMQ console](../../decisions/2026-11-09-rabbitmq-console-design.md)

## D329. A message is a new row of a stream, or the Publish action anywhere else

A stream's page takes new rows: the grid's **+**, a paste and a pipeline's Add
rows publish into it through the default exchange, the stream's name as the
routing key. The columns sent are timestamp, content type, headers, properties
and body, and the body's fields; offset, exchange and routing key are the
stream's. A body written `0x…` is those bytes, an empty body with fields is a
JSON object of them, headers and properties are JSON objects and properties
are limited to what AMQP names. A block is read whole before anything is sent,
so one unreadable cell rejects it with the cell named, then it is published on
a channel with publisher confirms, each message waited for; no transaction.
The text-to-bytes and field readers are Kafka's, shared in
`app/adapters/message_cells.py`.

A queue's and an exchange's page is their bindings, so a message for them is
the **Publish** action: an exchange with a routing key, a queue through the
default exchange. It is published mandatory, and one routed to no queue is
refused as lost rather than counted as sent.

Spec: [Writing to RabbitMQ](../../decisions/2026-11-09-rabbitmq-writes-design.md)

## D330. Queues, streams, exchanges and bindings change through the API; Peek keeps what it read

New queue, New stream and New exchange are offered on their levels; Delete,
Bind and Unbind on a queue, stream or exchange; Publish, Purge and Peek on a
queue. Every change is a `PUT`, `POST` or `DELETE` to the management API, and a
400 is reduced by its reason's kind: a name taken with other settings, a
stream asked what only a queue does, or a plain refusal. A name is at most 255
bytes and never `amq.`; arguments are `name=value` lines, a value read as JSON
when it is JSON. The broker's own exchanges are not deleted, and the default
exchange takes only Publish. A preview counts a queue's messages over AMQP (a
passive declare), not from the management API's sample, which lags by seconds.

Peek is the management API's `get` with `ack_requeue_true`, at most a hundred
messages, offered only as an action with a warning in its confirmation:
looking is a delivery, marking messages redelivered and counting towards a
quorum queue's delivery limit. What it read is kept as a snapshot in the
resource store, twenty a connection, and the result's `open_node_id` names it;
the catalog opens it at once. A snapshot is a `report` node,
`peek:<v>/<queue>/<n>`, under its queue in `path_to` and listed nowhere; its
rows are position, redelivered, exchange, routing key, timestamp, content type,
headers, properties, body and the body's fields, and paging it never reads the
queue. A draft has no store, so it does not peek.

Known deviations:

- **A snapshot outlives nothing**: the resource store lets it go when the
  process ends or the connection's entries go idle, and the tab then says the
  node is missing.
- **Publish takes no properties** beyond content type and headers; a stream's
  new row does.

Spec: [Writing to RabbitMQ](../../decisions/2026-11-09-rabbitmq-writes-design.md)

## D331. A Broker section of reports, metrics from the overview and queues, names searched

The top of the catalog starts with a Broker section, before the virtual hosts
or the three levels, as Kafka's Cluster section does (D310). Its reports are
management API answers read into setting-and-value rows: Overview (release,
counts, messages ready and unacknowledged, rates), Nodes (memory, disk, file
descriptors, uptime), Alarms (a node over its memory or under its disk limit,
which blocks every publisher; empty when all is well), Connections, Channels
and Policies. Overview, Alarms and Connections refresh every ten seconds; a
paged list past five hundred says it was cut. Report ids are `broker` and
`report:<key>`, outside the virtual hosts' ids.

A metrics poll reads the overview, the nodes and the first hundred queues by
name: `broker` (connections, channels, consumers, queues, nodes in alarm),
`messages` (published, delivered and redelivered as counters; ready and
unacknowledged in all) and `queue` (each queue's ready and unacknowledged, a
stream's messages), labelled by name, `vhost/name` outside the root virtual
host. The preset **RabbitMQ broker** draws them. No message content is a
metric.

Search reads queue and exchange names from the API, across the virtual hosts
the connection sees, five hundred a page up to twenty pages, and keeps the
best-classed matches; each is scoped to its level, with the virtual host
first in its path when the top lists them. The same names are kept for the
search over everything (D213). Names are the cheap field; nothing else is
searched.

Known deviations:

- **A connection's channels and state arrive with a later sample** than the
  connection itself: the Connections report may show it a few seconds before
  it shows what it holds.

Spec: [RabbitMQ's reports, metrics and search](../../decisions/2026-11-09-rabbitmq-reports-design.md)

## D332. A RabbitMQ started here places AMQP and is managed by its name; it has a lab

The `rabbitmq` service template runs `rabbitmq:4.3.7-management` with the user
`dataplayer` and a password the server makes up unless the requester names
one, as `RABBITMQ_DEFAULT_USER` and `RABBITMQ_DEFAULT_PASS`; there is no
unprotected shape. `RABBITMQ_NODENAME` is fixed to `rabbit@localhost`, since
RabbitMQ keeps its data under the node's name and would otherwise take the
container's hostname, new with every container.

The template's one port is AMQP's, 5672: published on the loopback for the
owner's tools and given to the connection as its host and port. The
management API is not published. The application reaches a service by its
container name on the service network, where every port answers, and the
connection leaves its management address empty, so it is
`http://<container>:15672` (D325); readiness waits for that API too.

Asked for sample data, the adapter fills the connection's virtual host — `/`
for a service — with a topic exchange `lab.orders`, a classic queue
`lab.billing` on `orders.#` dead-lettering to the fanout `lab.dead-letter` and
its queue `lab.dead`, a quorum queue `lab.shipping` on `orders.paid`, a headers
exchange `lab.alerts` with `lab.alerts.critical` bound on `x-match=all,
level=critical`, and a stream `lab.trades` of three hundred JSON trades and a
few bodies that are bytes. Nothing consumes, so the counts stay as left.

Known deviations:

- **The management API is reached from inside DataPlayer only**: a tool on the
  owner's machine reaches AMQP alone, as Kafka's published port reaches the
  first broker only (D311).
- **No copy to another connection and no backup**: RabbitMQ's own way is its
  definitions export and shovels, which `rabbitmqadmin` in the terminal offers
  (D328); messages are not something a backup here would carry.

Spec: [A RabbitMQ started here, and its lab](../../decisions/2026-11-09-rabbitmq-service-design.md)
