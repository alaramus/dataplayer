# Cassandra

An Apache Cassandra or ScyllaDB cluster, reached over CQL. You browse its
keyspaces, read tables and materialized views a page at a time, see how a
table's key is built and read the server's own DDL for it. Both products are
one type of connection: the catalog of types shows a card for each, and the
connection says which one it reached.
How connections work in general is on the [Connections](connections.md) page.

## What you can see

- Keyspaces, tables and materialized views
- Rows a page at a time, filtered on the server, values exactly as stored
- A table's partition key, clustering columns and secondary indexes
- A relation's DDL, as the server writes it
- Cassandra's virtual tables, such as `system_views`
- The results of CQL you write, in the console or in cqlsh

## What you can change

- Table data: edit cells, paste blocks, insert and delete rows
- Columns and secondary indexes of a table
- Data and structure, through CQL in the console, one change at a time

## Connecting

The **Connection** page of the window asks for:

- **Host** and **Port** of the native protocol, 9042 unless the server says
  otherwise;
- **TLS**, with the server's certificate checked against the host;
- **Authentication**: a user and a password, or none for a server that checks
  none. A new Cassandra or ScyllaDB is often `cassandra` with the password
  `cassandra`;
- **Keyspace**: where the catalog opens. It may be left empty;
- **Consistency**: how many replicas answer a read and acknowledge a write.
  `LOCAL_ONE` unless you choose another.

A connection string such as `cassandra://ann@db.example.com:9042/shop` pasted
into **URL** fills these fields; `scylla://` is read too, `?ssl=true` turns on
TLS and `?consistency=LOCAL_QUORUM` picks the level.

Every statement goes to the node you name, also when the cluster has others:
the addresses the nodes give for themselves are often not reachable from here
— behind Docker, a NAT or an SSH tunnel — and the node you named is. That node
asks the others for what it does not hold.

Cassandra 4.0 and ScyllaDB 5.4 and later are supported. An older server is
refused when the connection is checked, with its version named.

## The catalog

- The first level is keyspaces. The one the connection names comes first;
  `system` and the `system_…` keyspaces belong to the server and are marked as
  such, and so is ScyllaDB's `audit`.
- Inside a keyspace are its tables and materialized views. ScyllaDB keeps a
  secondary index in a hidden view; that view is not listed, and the index is
  shown on its table.
- A table's columns say which belong to the partition key and which are
  clustering columns, in which order, and which are static.

## Rows

- Rows arrive in the server's own order, a page at a time. No column can be
  sorted: CQL orders rows only inside one partition named in full.
- A filter on any column works. One on a column outside the key makes the
  server read the whole table to find the rows, which on a big table can run
  out of time.
- Filters compare with equal, greater, less, at least, at most and one of a
  list. ScyllaDB adds starts with and contains for text; `%` and `_` cannot be
  looked for, because its `LIKE` has no escape. Lists, sets, maps, tuples,
  user-defined types, blobs, durations and counters are not filtered.
- Numbers arrive exactly as stored, to the last digit of a `varint` or a
  `decimal`. A timestamp is shown in UTC. Lists, sets, maps, tuples and
  user-defined types are shown as JSON; a map whose keys are not text as a list
  of pairs. A blob is shown as `0x` and hexadecimal.
- Jumping far ahead reads the rows in between, up to a hundred thousand.
  Beyond that, page forward from a page you have read.
- The last page may promise more and turn out empty: the server says whether
  more might follow before it has looked.

## CQL console

**New query** under **Queries** on the left rail starts one on the
connection, and **Open as a query** above a table starts one on that table.
It works as the PostgreSQL console does — reads, changes, completion — with
these differences:

- The language is CQL. The keyspace chosen above the editor is the one
  unqualified names are in; a `USE` changes it for the rest of that run only.
- There is no transaction. **Read** runs statements that only read:
  `SELECT`, `DESCRIBE` and `LIST`. **Auto-commit** runs anything, but a
  statement that changes rows or structure runs on its own, because Cassandra
  keeps it at once and cannot take it back. Changes that must land together go
  in one `BEGIN BATCH … APPLY BATCH`, which counts as one statement.
- Parameters are CQL's own, `:name`. The server says what type each is, and
  the value is read as that type; a list, a set, a map, a tuple or a
  user-defined type is written as JSON. **SQL null** sends null.
- `CONSISTENCY`, `TRACING`, `COPY`, `SOURCE`, `PAGING` and the other commands
  of cqlsh are not CQL, and are refused here; run them in cqlsh.
- **Stop** stops waiting for the answer. The server cannot be told to stop a
  statement, so it finishes it anyway.

## cqlsh

**Terminal** on a connection opens cqlsh, signed in as the connection is, in
the keyspace it names. It is Cassandra's own cqlsh for ScyllaDB too; both
speak CQL. It runs in a container on this server, so the host must be one that
server can reach, and a connection through an SSH tunnel has no terminal yet.

## Changing rows

- Cells are edited, blocks pasted, rows inserted and deleted in a table.
  Materialized views, virtual tables and the server's own keyspaces are read
  only, and so is a table of counters: a counter only takes an addition, which
  the console can write.
- A row is found by its primary key. The columns of the key are not edited —
  they decide where the row is kept — and a new row needs a value for each.
- A row somebody changed after you read the page is refused rather than
  overwritten. Read the page again and repeat the change. A change made in the
  same instant as yours is not caught: Cassandra has no transaction to hold the
  row.
- Lists, sets, maps, tuples and user-defined types are written as the JSON
  they are shown as. A duration is not edited.
- A static column holds one value for the whole partition, so editing it on
  one row changes it on every row of that partition.
- Adding one row refuses a key that is already there. Rows pasted or loaded as
  a block replace a row with the same key, which is how Cassandra writes.
- A paste is checked whole before anything is written: one value its column
  cannot hold, and nothing changes.

## Changing the structure

- A table's columns are added and dropped. A column of the primary key is not
  dropped; the server also refuses to drop one an index or a materialized view
  reads, and says which.
- Only a column of the primary key can be renamed: Cassandra renames nothing
  else. Cassandra has no defaults, no column outside the key that must have a
  value, and no change of a column's type, so none is offered.
- A secondary index is made on one column and dropped. Cassandra 5 offers the
  storage-attached index (SAI) and the legacy one, ScyllaDB its global index.
  None is unique.
- Materialized views, virtual tables and the server's own keyspaces are not
  changed.
