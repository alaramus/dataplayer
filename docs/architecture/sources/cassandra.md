# Cassandra and ScyllaDB

What a Cassandra source is, how it reaches Apache Cassandra and ScyllaDB, what
its catalog shows, and how its values and pages cross to the grid. The contract
every source type follows is in [contract.md](contract.md); reading a relation
in general is in [relations.md](relations.md). Read this before changing the
`cassandra` adapter.

Decisions here: D340, D341, D342, D343, D344, D345, D346.

## D340. One type for Cassandra and ScyllaDB, through the address given

One source type, `cassandra`, speaks CQL to both products through
`scylla-driver`, whose module is `cassandra`; the catalog of types shows a card
for each, Apache Cassandra and ScyllaDB (D264). The server says which it is:
ScyllaDB answers `system.versions`, Cassandra refuses it, and ScyllaDB's own
version is read there because its `release_version` is a compatibility 3.0.8.

The driver keeps its connections on a loop of its own in a thread. A statement
is sent with `execute_async` and waited for on the application's loop through
the driver's callbacks; `Cluster.connect`, `prepare` and `shutdown` block and
run in a thread. A connector keeps one cluster in the resource store, keyed by
everything that makes two clusters different, the address dialled included,
and connected on first use outside the store's lock. A value is bound to a
prepared statement, typed by its column; a statement that binds nothing runs
as it is. A refused statement is a ValueError with the server's sentence; any
other failure is reduced by the driver's exception class, never by its text.

Every node is the address in the form: an address translator maps every
address the driver reads from `system.local` and `system.peers` to the one
dialled, one node coordinates every statement, and ScyllaDB's shard-aware port
is not used. Behind published ports, a NAT or an SSH tunnel (D282) those
addresses do not answer. The driver's own copy of the schema and the token map
is switched off; the catalog reads `system_schema`.

Options are host, port (9042), TLS with the certificate verified against the
host in the form — through a tunnel too, — a user and password or none, an
optional keyspace where the catalog opens, and a consistency level from a
closed list (`LOCAL_ONE` unless chosen). `cassandra://`, `scylla://` and
`cql://` addresses are parsed. Cassandra 4.0 and ScyllaDB 5.4 are the floor.

Known deviations:

- A read goes to the node named, not to a replica of its partition.
- ScyllaDB is not reached through its shard-aware port.
- A self-signed certificate cannot be trusted; TLS is verified or off.
- A connection of ScyllaDB shows Cassandra's picture in lists, as MariaDB's
  shows MySQL's: a connection keeps its type, not the card it was made from.

Spec: [A Cassandra and ScyllaDB source](../../decisions/2026-11-10-cassandra-source-design.md)

## D341. Keyspaces are schemas, named as keyspaces

The catalog is keyspaces as schemas with the term `keyspace`, then their tables
and materialized views from `system_schema`, every name bound. Node ids are
MySQL's (`app.adapters.database_ids`). `system` and every `system_…` keyspace
belong to the server, and so does ScyllaDB's `audit`; they are listed last.
Cassandra's virtual keyspaces (`system_views`) come from
`system_virtual_schema` and are read like any other. ScyllaDB keeps a secondary
index in a view named `<index>_index`; that view is not listed, and the index
is shown on its table.

A relation's model: the partition key and then the clustering columns are the
primary key, each column saying which it is and a clustering column its order;
a static column says so; a secondary index is an index; there is no foreign
key, unique key or check, and no row estimate. The DDL is the server's own
`DESCRIBE`.

Spec: [A Cassandra and ScyllaDB source](../../decisions/2026-11-10-cassandra-source-design.md)

## D342. Pages go on from a paging state; filters use ALLOW FILTERING

A value crosses as text: numbers as their digits (a float by `repr`, NaN and
infinity as words), a timestamp as an instant in UTC with its offset, a date
as `YYYY-MM-DD`, a time with nanoseconds, a duration in CQL's units, a blob as
`0x` and hexadecimal, a uuid and an inet as their text; a list, a set, a
vector, a tuple and a user-defined type as compact JSON, a map as an object or,
when its keys are not text, as a list of pairs.

The grid asks by offset and CQL has none. The cluster a connector keeps
remembers the paging state each served page ended at, per statement, bound
values and page size; an offset goes on from the nearest state before it and
reads and throws away the rows between, at most 100,000. A page is gathered
until it has its rows or the read ends, because a filtered page comes back
short. A table that answers whole whatever the page size — a virtual one — is
read whole and cut. No column sorts: CQL orders only inside one partition.

A filter on any column is sent with `ALLOW FILTERING` (the user's choice,
2026-11-10). Both servers accept equal, greater, less, at least, at most and
`IN` there; ScyllaDB adds `LIKE`, offered as starts with and contains on text,
with `%` and `_` refused in the value because it has no escape. A collection, a
tuple, a user-defined type, a blob, a duration and a counter are not filtered.

Known deviations:

- `has_more` follows the paging state, which can promise one more page that
  turns out empty.
- A filter outside the key reads the whole table on the server.

Spec: [A Cassandra and ScyllaDB source](../../decisions/2026-11-10-cassandra-source-design.md)

## D343. CQL in the query console, a change at a time

The console runs CQL. A tokenizer of CQL's rules splits a script — strings,
quoted names, `$$` bodies and comments hold semicolons, and a batch from
`BEGIN BATCH` to `APPLY BATCH` is one statement — and the first words class
each statement: `SELECT`, `DESCRIBE`, `LIST` read; `INSERT`, `UPDATE`, `DELETE`
and a batch change rows; `CREATE`, `ALTER`, `DROP`, `TRUNCATE`, `GRANT`,
`REVOKE` change structure; `USE` is the session's. cqlsh's own commands are
refused with a sentence naming cqlsh.

There is no transaction. Read runs only reads; Auto-commit runs a change
alone, as ClickHouse does (D271), and the refusal names `BATCH`; there is no
Manual mode. A run has a driver session of its own, opened on the keyspace
chosen above the editor, so `USE` changes that run alone. `:name` markers are
the parameters: the statement is prepared, the server says each marker's type,
and the value is read as that type — JSON for a collection, a tuple or a
user-defined type — and bound. Stop lets the answer go; the server finishes
the statement. Completion reads `system_schema`.

Known deviations:

- A cancelled statement goes on running on the server.
- A run of reads and a change together is refused rather than run up to the
  change.

Spec: [CQL in the console, cqlsh in a terminal](../../decisions/2026-11-10-cassandra-console-design.md)

## D344. cqlsh in a terminal, signed in from a file

A connection's terminal is cqlsh in a container of `cassandra:5.0`, for
ScyllaDB too, whose image starts its server whatever it is given. The node is
in `CQLSH_HOST` and `CQLSH_PORT`; the user and the password are written into
cqlsh's credentials file inside the container, mode 600, from a variable unset
before cqlsh starts. A `%` in the user is doubled for ConfigParser, and a line
break in either is refused. Not through an SSH tunnel.

Spec: [CQL in the console, cqlsh in a terminal](../../decisions/2026-11-10-cassandra-console-design.md)

## D345. A row is its primary key, read again before it changes

A row's handle is its primary key as the page showed it and a digest of the
row (`app.adapters.row_handles`). A change reads the row again by the key and
goes on only when it digests the same, then writes a plain `UPDATE`, `INSERT`
or `DELETE` by the key; no lightweight transaction. Key columns are never
edited and an insert needs all of them; a duration is not written; a
collection, a tuple and a user-defined type are written as their JSON, shaped
by the types the server gives for the prepared statement. A counter table, a
materialized view, a virtual table and the server's own keyspaces are read
only. A paste is read whole as its columns' types and every row is checked
before any is written. One inserted row refuses a key that is there; a block
replaces rows with the same key.

Known deviations:

- A change made between the read and the write is not seen; a row deleted in
  that moment comes back with the changed cells only.
- A block of rows overwrites rows that share a key instead of refusing them.

Spec: [Changing a Cassandra table's rows](../../decisions/2026-11-10-cassandra-rows-design.md)

## D346. Columns added, dropped and, in the key, renamed; one-column indexes

A table's model offers what CQL's `ALTER TABLE` does: add a column of a type
from a closed list (CQL's scalars, and a list, a set and a map of text), drop
one outside the primary key, rename one of the primary key — Cassandra renames
nothing else, and a regular column is refused before anything is sent. There
is no default, no `NOT NULL` outside the key and no change of type. A
secondary index covers one column, is never unique, and is named from the
table and the column; its methods are the server's: SAI and legacy on
Cassandra 5, legacy on Cassandra 4, the global index on ScyllaDB. A refusal
the server gives, such as a column a view reads, is passed on in its words. A
view, a virtual table and the server's own keyspaces change nothing.

Spec: [Changing a Cassandra table's structure](../../decisions/2026-11-10-cassandra-structure-design.md)
