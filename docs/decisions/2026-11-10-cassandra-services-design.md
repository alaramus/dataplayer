# Cassandra and ScyllaDB started here, their lab, metrics and copies

Decisions D351–D354, the sixth slice of the Cassandra source
([A Cassandra and ScyllaDB source](2026-11-10-cassandra-source-design.md)).

## A node started here (D351)

Each card offers a server of its own (D264): `cassandra` and `scylladb`
templates, the user `cassandra` and a password made up per service, both
becoming a `cassandra` connection.

**Cassandra** has no setting for a password check and makes its first
superuser with the password `cassandra`. Its template's command switches the
check on in `cassandra.yaml`, starts the server through the image's own
entrypoint in the background, and, once CQL answers, changes that superuser's
password to the service's. The new password reaches cqlsh through a
credentials file written with mode 600, never an argument; a quote in a chosen
one is doubled for CQL. On a later start the new password signs in at once and
nothing is changed. If the server dies, the command ends, so the service is
seen to fail rather than wait.

Memory decided the rest. Every service is held to `SERVICE_MEMORY_MB`, 1024
by default (D86). Measured on a 24-core machine, Cassandra 5 with a 384 MB
heap took 1.1 GB, because the JVM starts one G1 thread per core and Cassandra
sizes its caches from the heap; the kernel killed it without a word. With two
parallel and one concurrent G1 thread, two compiler threads, no pre-touched
heap, a 64 MB direct-memory and 48 MB code-cache ceiling, and Cassandra's file
and networking caches at 32 and 16 MB, the same node holds about 800 MB.

**ScyllaDB** makes no first superuser by itself since 2025 and takes one only
as `--auth-superuser-name` and `--auth-superuser-salted-password`, a SHA-512
crypt hash; its image's entrypoint runs the server whatever command it is
given, so no script can set the password later. A template could only write
constants and slots, so a new kind of value was added: `SaltedHash`, a
credential as its SHA-512 crypt with a new random salt, after a fixed prefix.
Python 3.13 removed its `crypt` module; the scheme is short and fixed
(Drepper's "Unix crypt using SHA-256 and SHA-512"), so it is written in
`app.core.sha512_crypt` and checked against the scheme's own test vector. The
image hands its arguments to the server through a shell, so each `$` of the
hash is written `\$`. Seastar subtracts its own reserve from the container's
limit, so ScyllaDB is asked for 450 MB of the 1024.

A ScyllaDB node without a password was the alternative — its port is published
on the loopback only — and was rejected: other containers on the service
network reach it too.

## The lab (D352)

`demo_lab`: organizations, people by organization with a static column, a
user-defined type, a list and a secondary index; tasks by project, newest
first, with a decimal and a duration, and a materialized view by status; twenty
thousand page views over thirty days, one partition a day; a counter table of
views per path. CQL has no `INSERT … SELECT` and no row generator, so the rows
are made in Python from a fixed seed and written with prepared statements,
through one connection held for the whole run. On ScyllaDB the keyspace is kept
out of tablets, because a view and an index want the classic layout there.

## Metrics (D353)

What CQL answers on the node asked: the number of clients, and the partitions
and bytes `system.size_estimates` gives for the connection's keyspace, or for
every keyspace not the server's own. Cassandra adds its thread pools from
`system_views.thread_pools`: native requests, reads, writes and compactions as
rates, and the work pending and active. ScyllaDB keeps those in its Prometheus
endpoint on a port of its own, which this source does not reach. One preset,
**Cassandra node**.

## Copying tables (D354)

Between Cassandra connections, of either product, as the other databases copy
(D182). The source describes a table from `system_schema`: column types as CQL
prints them, a static column, the key as `PRIMARY KEY ((…), …)`, a clustering
order that is not ascending, the comment, its secondary indexes and the
user-defined types it uses, those they use first. The destination makes a type
it lacks, the table, the rows, and only then the indexes, so each is built once.
Every fragment is checked against a narrow pattern before it is composed.

Rows cross as JSON lines of the cells as the grid shows them and are read back
by their column's type, as a pasted block is (D345). A duration is now read
back too, so it is also edited in the grid. A counter table is refused: a
counter takes no `INSERT`. A materialized view over a copied table is named as
left behind.

## Backups

Not offered. cqlsh's `COPY` writes collections and user-defined types in its
own format and restoring a schema means replaying `DESCRIBE` output in order;
a backup that may not restore is worse than none. Recorded as a deviation, to
be its own decision.
