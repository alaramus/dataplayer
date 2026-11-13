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
- The broker's reports: overview, nodes, alarms, connections, channels
- Messages a second and what waits in each queue on a dashboard
- Queues, streams and exchanges found by name
- rabbitmqadmin, set up for the connection, in a terminal

## What you can change

- Messages sent to a stream, one by one or pasted as rows
- A message published to an exchange or a queue
- New queues, streams and exchanges, and deleting them
- Bindings made and removed
- A queue purged, or its messages looked at once with Peek
- Anything rabbitmqadmin can change, typed into the terminal

## Connecting

The **Connection** page of the window asks for:

- **Host** and **AMQP port**: where the broker takes AMQP, 5672 by default,
  5671 with TLS;
- **Management address**: where its management API answers. Empty means
  `http://` the host and port 15672, or `https://` with TLS. RabbitMQ answers
  there only with its management plugin on; the official `-management` images
  have it;
- **User** and **Password**: one RabbitMQ user for both;
- **Address for the browser**: where **Open management** in the catalog's menu
  takes you, when your browser reaches the management page at another address
  than DataPlayer does; empty for the management address;
- **Virtual host**: empty for every virtual host the user may see, or one
  name, such as `/`;
- **TLS** and **CA certificate**: an encrypted connection, and the authority
  that signed the broker's certificate when the system does not trust it.

A connection string `amqp://user:password@host:5672/vhost` fills the form;
`amqps://` is TLS, and `%2F` in the path is the virtual host `/`.

The check asks the management API first and AMQP after. When only AMQP
refuses — a virtual host the user may not open, a port not reachable — the
connection is still saved and says why: the catalog works, a stream's messages
do not.

An **SSH tunnel** carries AMQP and the management API both; the host
and the management address are then as the SSH server sees them. Through a
tunnel, connect without TLS, and fill in the **Address for the browser** for
**Open management**. The terminal does not go through a tunnel yet.

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

## Sending messages to a stream

- **+** over a stream's rows adds a message. Fill what you need: everything
  may stay empty. It goes through the default exchange, with the stream's
  name as its routing key.
- **body** is text; `0x` followed by hex digits is sent as those bytes. Leave
  it empty and fill the `body.` fields to send a JSON object of them.
- **headers** is a JSON object, such as `{"source": "manual"}`;
  **properties** is a JSON object of what AMQP names: `message_id`,
  `correlation_id`, `reply_to`, `priority`, `expiration`, `type`, `app_id`,
  `delivery_mode`.
- **timestamp** empty sends none.
- Rows pasted into a stream are sent as messages. If one value cannot be read,
  nothing is sent and the cell is named.
- The new row shows no offset until the page is read again: the stream gives
  it one.

## Changing queues, streams and exchanges

Tick a queue, a stream or an exchange, or none on its level, and open the
catalog's menu:

- **New queue**, **New stream**, **New exchange** — on their own levels. A
  queue is classic or quorum; a stream keeps messages for an age such as `7D`
  and up to a size; arguments are one `name=value` per line, such as
  `x-max-length=10000`.
- **Publish** — a message to an exchange with a routing key, or to a queue.
  A message the exchange routes to no queue is lost, and the window says so.
- **Bind** — from an exchange to the ticked queue, or from the ticked exchange
  to a queue or exchange, with a routing key. **Unbind** chooses one of the
  ticked node's bindings.
- **Purge** — every ready message of a queue goes; messages consumers have
  taken and not yet acknowledged stay with them.
- **Delete** — the window says how many messages and bindings go. RabbitMQ's
  own exchanges are not deleted.

## Peek

A queue's messages are not shown when it is opened: reading them takes them.
**Peek** takes up to a hundred and puts them back at once, and opens what it
read in a tab.

- Each message comes back marked **redelivered**. A quorum queue counts the
  look towards its delivery limit, after which a message is dead-lettered or
  dropped, and a consumer may get the messages out of their order. The window
  asks before it looks.
- The tab is the look as it was taken. Paging through it does not read the
  queue again; for a new look, Peek again.
- A look is kept while DataPlayer runs and for a while after it is last
  opened.

## The Broker section

At the top of the catalog, **Broker** holds what the broker says about itself:

- **Overview** — the release, how many connections, channels, queues,
  exchanges and consumers, messages ready and unacknowledged, and messages a
  second in and out;
- **Nodes** — each node's memory and its limit, free disk and its floor, file
  descriptors and uptime;
- **Alarms** — a node short of memory or disk. While one is raised RabbitMQ
  blocks every publisher; the report is empty when all is well;
- **Connections** and **Channels** — each client, its user and virtual host,
  its channels, consumers, prefetch and messages taken and not acknowledged;
- **Policies** — each policy, what it matches and what it sets.

Overview, Alarms and Connections refresh every ten seconds. A long list shows
its first five hundred and says so.

## Dashboards and search

- The **RabbitMQ broker** dashboard draws messages a second, what waits in
  each queue and what is taken and not acknowledged, connections and alarms,
  for the first hundred queues by name.
- The search in the header finds queues, streams and exchanges by name, in
  every virtual host the connection sees.

## In a pipeline

RabbitMQ can sit in the middle of a pipeline, as a Kafka topic can: one link
sends rows into it, others carry what arrives into tables.

- **Add rows** into an exchange, a queue or a stream sends each row as a
  message. Every column that is not a message's own becomes a field of a JSON
  body under its own name, so a row of a table or a Binance trade arrives as
  `{"price": …, "qty": …}`; columns of the same name pair by themselves. Into
  an exchange, pair a column with **routing_key**: a row without one goes
  wherever the exchange sends an empty key.
- **Add new messages to a table**, from a stream, reads only what arrived since
  the link's last run. The place it stopped is kept by DataPlayer, by offset.
  **Add new messages to a new table** keys the table it makes on the offset,
  so a message written twice is kept once.
- The same links from a queue take its waiting messages, as any consumer of
  it does: each block is acknowledged only once it is written. If a run fails
  in between, the block goes back to the queue and is taken again, marked
  redelivered. Other consumers of the queue share its messages with the link;
  draw the link from the queue's exchange instead for all of them.
- From an **exchange**, the link reads through a queue of its own,
  `dataplayer-link-…`, which each run makes or finds and binds by the link's
  **Binding key**: empty is `#` for a topic exchange, everything; a fanout or a
  headers exchange needs none. The queue is made at the first run, so that run
  reads nothing, and the link gets what the exchange routes from then on.
  Changing the key takes effect at the next run. The queue is in the catalog
  like any other; a link deleted leaves it, and it goes by itself after a
  week unread, keeping at most a million messages meanwhile. The connection's
  user needs configure, write and read on that queue and read on the
  exchange.
- A queue's columns are the message's own and, into a table that is there,
  a field of a JSON body for every other column of that table: a column
  `price` takes the body's `price`, empty when a message has none, so a row
  sent through RabbitMQ comes back by itself. Only top-level fields; a new
  table gets the message's own columns. **First run reads** means nothing for
  a queue: it always takes what waits.
- A pipeline switched on carries what arrives within seconds, from a stream
  or a queue, as it does from a topic.

## Downloads

**Download** on a stream saves the messages its page would show, with its
filters and order, up to ten thousand. A queue or an exchange downloads its
bindings.

## rabbitmqadmin

**Terminal** on a RabbitMQ connection opens bash with `rabbitmqadmin`,
RabbitMQ's own command-line client of the management API, already pointed at
the connection: its address, user, password and virtual host. Tab completes
its commands. Try:

- `rabbitmqadmin show overview` — the broker at a glance
- `rabbitmqadmin list queues` — every queue with its counts
- `rabbitmqadmin list exchanges` — the exchanges
- `rabbitmqadmin -V NAME list queues` — another virtual host

It can declare, delete and purge queues and exchanges, publish and get
messages and export definitions; what it changes is changed on the broker at
once. The terminal runs in a container on the DataPlayer server, so it needs
that server to be allowed to start containers, and the management address
must be reachable from there.

## A RabbitMQ of your own

**Services** can start a RabbitMQ broker on this machine, if this server may
run containers. Its user is `dataplayer` and its password is made up for you
unless you give one; its connection is made for you.

Ask for sample data to get a lab:

- `lab.orders` — a topic exchange routing `orders.new` and `orders.paid`;
- `lab.billing` — a classic queue bound to `orders.#`, sixty orders waiting,
  dead-lettering to `lab.dead-letter`;
- `lab.shipping` — a quorum queue bound to `orders.paid`, so it holds the paid
  orders only;
- `lab.dead-letter` and `lab.dead` — a fanout exchange and the queue behind it;
- `lab.alerts` and `lab.alerts.critical` — a headers exchange and a queue that
  takes only the alerts whose `level` is `critical`;
- `lab.trades` — a stream of three hundred JSON trades over one day and a few
  sensor readings stored as bytes, shown in hex.

Nothing in the lab consumes, so every count stays where it was left.

The service row shows its AMQP port and the port of its management API, with
a link to the management page. **Open management** in the connection's menu
opens the same page. DataPlayer itself reaches the broker by the container's
name, so both work from this machine.
