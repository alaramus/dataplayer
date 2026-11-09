# RabbitMQ's reports, metrics and search

Decision D331. The fourth slice of the RabbitMQ source: what the broker says
about itself, what a dashboard draws of it, and finding queues, streams and
exchanges by name. Export came with the first slice (D327): a stream to its
page's depth, a queue's or an exchange's bindings whole.

## A Broker section of reports

At the top of the catalog, before the virtual hosts or the three levels, a
Broker section holds reports, as Kafka's Cluster section does (D310). Each is
one management API answer read into setting-and-value rows, so the grid, its
download and its chart need nothing new:

- **Overview** — the release, Erlang's, the cluster's name and the node
  answering; how many connections, channels, queues, exchanges and consumers;
  messages ready and unacknowledged; messages in and out a second. Refreshed
  every ten seconds.
- **Nodes** — each node: running or not, memory used of its limit, disk free
  above its limit, file descriptors, uptime.
- **Alarms** — a node over its memory or under its disk limit, which blocks
  every publisher; empty when all is well. Refreshed every ten seconds.
- **Connections** — each client: user, virtual host, its product and version
  when it says them, its channels and state. Refreshed every ten seconds.
- **Channels** — each channel: user, virtual host, consumers, prefetch and
  messages taken but not acknowledged.
- **Policies** — each policy: the virtual host, the pattern, what it applies
  to, its priority and what it sets.

A list past five hundred is cut there, the API's page, and the cut is said in
its last row.

## Metrics

One poll is the overview and the first hundred queues by name:

- `broker`: connections, channels, consumers and queues, and how many nodes
  are in a memory or disk alarm;
- `messages`: messages published, delivered and redelivered, as counters, so
  a dashboard draws them a second; messages ready and unacknowledged in all;
- `queue`: each queue's ready and unacknowledged messages, labelled by
  `vhost/name`, and a stream's messages.

The preset **RabbitMQ broker** draws messages a second, ready messages by
queue, unacknowledged by queue, connections and alarms. No message content
is ever a metric.

## Search

Queues, streams and exchanges are found by name, in the virtual host the
connection names or in every one, each scoped to its level as Kafka's topics
are (D213). The API lists them across virtual hosts five hundred to a page;
a search reads up to twenty pages and says so when it stops. Names are kept
for the search over everything the same way. Names are cheap: a few requests
whatever the broker holds; nothing else of RabbitMQ is searched.
