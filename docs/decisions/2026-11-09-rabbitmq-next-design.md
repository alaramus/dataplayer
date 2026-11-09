# RabbitMQ: an exchange read by a link, a queue's body fields, an SSH tunnel

Decisions D337–D339. The stage after RabbitMQ in pipelines (D335, D336),
closing three gaps that stage left: a link that reads a queue shares its
messages with every other consumer, a queue's rows come without the fields of
the body, and RabbitMQ was the one network database without a tunnel (D327).
Not implemented yet; the session that implements it moves each statement into
[rabbitmq.md](../architecture/sources/rabbitmq.md), registers the numbers in
AGENTS.md and corrects this spec where the code proves it wrong.

## An exchange read on through the link's own queue (D337)

A queue hands each message to one consumer, so a link reading a queue that a
worker also reads gets some of its messages (D335). Kafka gives every reader
all of a topic through a group of its own; RabbitMQ's way is a queue of its
own bound to the exchange. So an **exchange** becomes a node a link reads on
(`SupportsReadingOn.reads_on` answers yes for `exchange:<v>/<n>`), and the
link reads through a queue it owns:

- **Its name is the link's reader**, `dataplayer-link-<link id>`, the name a
  Kafka group already gets (`reader_of`). A pipeline copied gives its links new
  ids, so two pipelines never share a queue; the implementation checks that
  the copy does.
- **Declared at the start of every step**, not when the pipeline is saved:
  saving never touches a broker. A classic durable queue with
  `x-expires` of seven days, so the queue of a deleted link or an abandoned
  pipeline goes by itself, and `x-max-length` of 1 000 000 with
  `drop-head`, so a pipeline nobody runs does not fill the broker's disk.
  A queue already there with other arguments is a refusal that names it,
  never a redeclare.
- **Bound with the link's binding key**, a new optional field of `Link`
  (`binding_key`, at most 255 characters) asked in the link's form only when
  the source is an exchange. Its default follows the exchange's type: `#` for
  a topic, none needed for a fanout, an empty key for a direct exchange (a
  person usually types one), and for a headers exchange a binding with no
  headers and `x-match: all`, which takes every message. Each step binds the
  current key and unbinds any other binding from that exchange to that queue,
  so changing the key needs nothing more than a run. Links are part of the
  pipeline's stored document; if that ever becomes a table, the field is a new
  Alembic revision, never an edit of the baseline.
- **Read as a queue is (D335)**: the line is the ready count when the step
  starts, a block taken unacknowledged and acknowledged by `mark_read` once
  written, at least once. Earliest and latest mean nothing here either: the
  link sees what the exchange routed after its first step declared the queue.
  The first step therefore reads nothing, and says so in its message.
- **Deleting the link does not delete the queue** at once: the pipeline is
  saved without talking to the broker, and the queue expires. Rejected: a
  delete on save, which would make saving a pipeline fail when a broker is
  down, and would race a run in flight.
- **The queue is visible** in the catalog as any queue is; its name says whose
  it is. Hiding it would hide messages piling up.
- **Permissions**: the account needs configure and read on the queue and read
  on the exchange; a refusal from the broker says which.

A queue keeps being read as before, sharing with its other consumers; the
form for a queue says so in one line and suggests reading its exchange.

## A queue's rows carry the fields of the body (D338)

A stream's fields are found in the messages on its page; a queue's cannot be,
because looking takes them (D330). So the fields come from the other end, as
writing finds them (D336): when a link reading on from a queue or an exchange
writes into a table that exists, the source end is asked its moving columns
with the target's columns as `given`, and answers the message's own columns
and, for every target column that is not one of them, a column of that name
whose value is the top-level field of that name in a JSON body.

- Pairing by name then pairs `price` with the body's `price`, as writing does;
  a Binance trade sent through RabbitMQ comes back to the same columns without
  a line drawn by hand.
- A number, a boolean or a string is its value; an object or an array is its
  JSON text; a field missing, or a body that is not a JSON object, is null —
  the row is still written, and its `body` column, when paired, holds the
  message as it came.
- Only top-level fields; a nested one is reached by pairing `body` and taking
  it apart in the database.
- Into a **new table** (D313) nothing is known of the target, so the table
  gets the message's own columns as today. Rejected: shaping the table from
  the first block, which would decide the columns of every later run from
  whatever arrived first.
- A stream keeps the fields it finds on its page; it is not changed.

The change in the generic code is one argument: `since.py`'s
`_source_columns` passes the target's columns instead of `None` when the
target table exists.

## RabbitMQ through an SSH tunnel (D339)

RabbitMQ declares `ssh_tunnel` (D282). Two addresses go through it, each a
forwarder of its own as D282 gives them, with nothing new in the tunnels
module:

- **AMQP**: `reach(tunnels, ssh_tunnel, host, port)` before every connection
  aio-pika makes, the operation's and a reading link's held channel alike.
- **The management API**: the host and port of `management()` reached the
  same way before every client httpx makes; the path stays. The default
  `http://<host>:15672` names the host as the SSH server sees it, like every
  other address of the connection.
- **TLS through a tunnel is refused**, for AMQP and for an `https` management
  address, with ClickHouse's sentence: a certificate names the server, not a
  port on this loopback, and the tunnel encrypts already.
- **Open management (D334)** needs the Address for the browser through a
  tunnel: the management address names a host the person's browser does not
  see. Without it the action is greyed with that reason.
- **The console (D328)** does not go through a tunnel yet, with the sentence
  every other console uses: its container cannot reach a port on this
  process's loopback.
- Reports, metrics, search, previews, Peek and pipelines go through the
  session and need nothing of their own. The connection string names the host
  as the SSH server sees it; deleting an SSH connection RabbitMQ goes through
  is refused as for any database, which the implementation checks covers this
  source type.

The development setup proves it: a test reaches the compose `rabbitmq` from
the test `sshd` by its service name, AMQP and management both, skipped when
either server is down.

## Slices

1. D339, the tunnel: smallest, and independent of the other two.
2. D338, body fields for a queue.
3. D337, an exchange read through the link's queue, which reuses D338's
   columns.

Each slice is a commit with its tests, translations in the seven catalogs and
the user's guide in every language where a sentence changes.
