# A Cassandra and ScyllaDB source

Decisions D340–D342. The first slice of a source type that speaks CQL to Apache
Cassandra and to ScyllaDB. This slice reads: a connection, its catalog, a
relation's model, its summary and DDL, and its rows. The rest follows in its own
slices, listed at the end, each in its own commit.

## One type, two cards, one driver (D340)

ScyllaDB speaks Cassandra's native protocol and CQL, and its Python driver,
`scylla-driver`, is a fork of DataStax's `cassandra-driver` that installs the
same `cassandra` module and talks to both servers. The two cannot be installed
side by side. Choices weighed:

- two source types, one per product — rejected: every statement, every type
  and every catalog table is the same, and a person who moves a keyspace from
  one to the other would have to remake the connection;
- `cassandra-driver` — rejected: it speaks to ScyllaDB too, but without the
  ScyllaDB extensions, and its fork does everything it does;
- `acsylla`, an asynchronous binding of the C++ driver — rejected: no wheel for
  Python 3.14 or for Windows, where the tests run;
- `scylla-driver` under one type `cassandra` with two catalog cards (D264),
  Apache Cassandra and ScyllaDB, each with its own picture and service
  template — chosen, the way MySQL and MariaDB are one type (D228).

The server says which it is: ScyllaDB has `system.versions`, Cassandra does
not, and ScyllaDB reports `release_version` 3.0.8 for compatibility, so its own
version is read from `system.versions`.

The driver is synchronous at heart: a `Cluster` keeps its connections on an
event loop of its own in a thread, and `execute_async` answers a
`ResponseFuture` with callbacks. A callback hands the result to the
application's loop with `call_soon_threadsafe`, so a statement never holds a
thread while it waits. `Cluster.connect` and `shutdown` block and run in a
thread. A connector keeps one connected cluster in the resource store, keyed
by everything that makes two clusters different, the address actually dialled
included; a draft connects for the one request and shuts down after it.

**Only the address given.** After the first connection the driver reads every
node's own address from `system.local` and `system.peers` and connects there.
Behind Docker's port publishing, a NAT, a load balancer or an SSH tunnel (D282)
those addresses cannot be reached, and the source fails with "Unable to connect
to any servers" while the address in the form answers. An address translator
maps every node to the address dialled, and ScyllaDB's shard-aware port is not
used, because it is a second port nobody published. Every statement is
therefore coordinated by the one node named; the cost is that a read is not
sent to the replica that owns its partition, which a data tool reading pages
does not notice. Recorded as a deviation.

Options: host, port (9042), TLS with the certificate verified, a user and a
password or none, an optional keyspace that says where the catalog opens, and
a consistency level for reads and writes (`LOCAL_ONE` unless chosen; one of the
driver's levels, never a client's text). `cassandra://` and `scylla://`
addresses are parsed.

Cassandra 4.0 and ScyllaDB 5.4 are the floor: both describe a schema on the
server (`DESCRIBE`), which the DDL view uses. An older one is refused by the
check with its version named.

## Keyspaces, tables and views (D341)

A keyspace is a schema to the catalog, named as a keyspace; its children are
its tables and materialized views, read from `system_schema` with bound
values. Node ids are MySQL's (`app.adapters.database_ids`). The server's own
keyspaces (`system`, `system_*`) are listed last and marked as the system's.
Virtual tables (`system_views`, `system_virtual_schema`) are read like any
other table.

The relation model:

- the partition key and the clustering columns, in their order, are the
  primary key constraint; a clustering column's order is stated;
- a secondary index (`system_schema.indexes`) is an index, its kind and
  options as its definition;
- a static column and a counter are said in the column's type text;
- there is no foreign key and no check.

Row estimates are not given: `system.size_estimates` counts partitions, not
rows, and only per token range of the node asked.

The DDL is the server's own `DESCRIBE`, so it is exactly what the server would
recreate the table from, its options included.

## Values and pages (D342)

Every value crosses as text the grid shows and a later slice can write back:

- an integer, a `decimal` and a `varint` as their digits; a `float` and a
  `double` by `repr`, NaN and infinity as words;
- a `timestamp` as an instant in UTC with its offset, `+00:00`, the spelling
  every other source's instant has (`app.adapters.cells`; the driver gives a
  naive UTC datetime), a `date` as `YYYY-MM-DD`, a `time` as `hh:mm:ss.fffffffff`, a
  `duration` in CQL's own `1mo2d3h` form;
- a `uuid` and `timeuuid` as their text, an `inet` as its address, a `blob`
  as `0x` and hexadecimal, as CQL writes a blob literal;
- a list, a set, a map, a tuple, a user-defined type and a vector as compact
  JSON (a map with keys that are not text as an array of pairs).

A page cannot be addressed by offset: CQL has no `OFFSET`, only the paging
state of the page before. The grid asks by offset, so the source keeps the
paging state that ends every page it has served, per relation, filter set and
page size, in the connector's resource store, and serves an offset by going on
from the nearest state at or before it. A jump past every kept state reads the
rows between and throws them away, at most 100,000, and says so beyond that.
Rows come in token order, which is the server's order; no column is sortable,
because CQL orders only inside one partition named in full.

Filters, chosen by the user (2026-11-10): a filter on any column is allowed,
sent with `ALLOW FILTERING`, and the page says that a filter outside the key
reads the whole table. Operators are the ones both servers accept with
`ALLOW FILTERING` on a regular column: equal, greater, less, at least, at most
and `IN`, each value bound and typed by the column. ScyllaDB adds `LIKE`,
offered as starts with and contains on a text column; Cassandra refuses `LIKE`
without an index and so does not offer it. Not equal, empty and not empty are
refused by both servers and not offered. A collection, a tuple, a UDT and a
blob are not filterable.

## Found while building it

- TLS needs no refusal through an SSH tunnel, unlike ClickHouse's: the driver
  checks the certificate against the host in the form while it dials the
  tunnel's end.
- ScyllaDB since 2025 makes no first superuser by itself; its test server names
  one on the command line. It keeps a new keyspace in tablets and refuses
  `SimpleStrategy` there; the tests' keyspace turns tablets off, because a
  materialized view and a secondary index want the classic layout.
- ScyllaDB keeps a secondary index in a materialized view named
  `<index>_index`, listed in `system_schema.views`; the catalog leaves it out.
- ScyllaDB makes a keyspace `audit` of its own.
- A Cassandra virtual table ignores the page size and answers whole; such a
  read is cut out of the whole answer.
- A table's name is letters, digits and underscores even when quoted; only a
  column's may be anything.

## Slices

1. Read only — this document: D340–D342.
2. CQL in the query console, results into the grid; `cqlsh` in a terminal.
3. Row edits by primary key: update, insert, delete; counters read only.
4. Structure: columns, secondary indexes, the table designer, a new table
   from rows, renaming a key column.
5. Reports (cluster, settings, clients, roles, sizes), search over names and
   columns, export of every row, catalog actions (new keyspace, truncate,
   drop).
6. Copying tables in and out, backup and restore, metrics, service templates
   for both products, the lab, the guide page in every language.

Test servers: `docker compose up -d cassandra` (127.0.0.1:9043) and
`docker compose up -d scylla` (127.0.0.1:9044), user and password `cassandra`.
One at a time on a machine short of memory; the tests of the one that does not
answer are skipped.
