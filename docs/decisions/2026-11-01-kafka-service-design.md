# A Kafka started here, and its lab

Decision D311. The fifth slice of the Kafka source: a service template, a lab
of topics and a group to try the source on, and the guide in every language.
Copying topics between connections and backups are not in it: Kafka's tool for
the first is MirrorMaker, a running service rather than a copy, and a Kafka
backup is its brokers' log directories; a walk that re-sent every message
would promise what neither gives.

## The template

The image the test server and the terminal run, `apache/kafka`, one broker
that is its own controller (KRaft), its log directory on the service's volume.
No credential: a broker answers anybody who reaches it, and its port is on the
loopback only (D86), as an unprotected Redis's is.

A Kafka client goes where the broker says it is, not where it first connected
(D304). The broker started here announces the address it has on the service
network, read when it starts, so the application, the terminal and the
pipelines reach it the way they reach every service (D86). A tool on this
machine that reaches the published port is sent on to that address, which only
the service network knows; Kafka's tools in the terminal are the way in from
outside the application. Announcing the published port as well was weighed and
is not possible: the runtime chooses the port after the container's settings
are written (D80), and a second listener needs a second published port.

A connector names its brokers as `host:port`, one field, so a template value
for "the address it is reached at" joins the two placement slots.

## The lab

Written out rather than generated, so two demonstrations look the same, and
shaped to exercise each part of the source:

- `lab.orders` — three partitions of JSON orders spread over a day, keyed by
  customer, so fields become columns, partitions merge by time and a time
  filter has something to cut;
- `lab.prices` — compacted, the latest price per symbol, a key that repeats;
- `lab.events` — plain text lines with headers;
- `lab.sensor` — values that are bytes, shown as hex;
- the group `lab-billing`, part way through `lab.orders`, so lag is seen in the
  catalog, its positions and the metrics.
