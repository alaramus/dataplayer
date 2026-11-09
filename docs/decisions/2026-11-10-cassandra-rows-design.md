# Changing a Cassandra table's rows

Decision D345, the third slice of the Cassandra source
([A Cassandra and ScyllaDB source](2026-11-10-cassandra-source-design.md)).

## A row is its primary key (D345)

Unlike ClickHouse (D272), a Cassandra table has a key that tells rows apart:
the partition key and the clustering columns together name one row. A row's
handle is those values as the page showed them and a digest of the whole row,
the handle MySQL uses (D234, `app.adapters.row_handles`).

A change reads the row again by its key and goes on only when it digests the
same, then writes with a plain `UPDATE`, `INSERT` or `DELETE` by the key.
Three ways to close the gap between the read and the write were weighed:

- a lightweight transaction, `UPDATE … IF col = old` — rejected: a Paxos round
  per change, and ScyllaDB refuses one on a keyspace kept in tablets unless
  the cluster is set up for it, so the same edit would work on one server and
  not on another;
- writing with `USING TIMESTAMP` of the read — rejected: it makes a write that
  loses to a newer one silently, which is a conflict nobody is told about;
- reading again and comparing — chosen, the way MySQL and ClickHouse do, with
  the same stated gap: a change made by somebody else between the two is not
  seen.

What may be changed:

- a column of the key is never changed: it decides where the row is kept, and
  Cassandra has no way to move a row; an insert needs every column of it;
- a `duration` is not written, because its text is not read back as one;
- a list, a set, a map, a tuple and a user-defined type are written as the JSON
  they are shown as, a map with keys that are not text as pairs;
- a static column is written like any other, and the change is the whole
  partition's, as Cassandra keeps it;
- a counter table is not changed here: a counter only takes an addition, which
  is a statement for the console;
- a materialized view, a virtual table and a table of the server's own
  keyspaces are read only.

Every value of a paste is read as its column's type before anything is
written, so a paste lands whole or not at all. Every row of a paste is checked
before any is written.

An insert of one row refuses a key that is already there, because a person
adding a row does not mean to overwrite one; it is checked by reading, with the
same gap. Rows inserted as a block — a paste, a file, a transfer — replace a
row with the same key, which is what Cassandra's `INSERT` does and what loading
expects; reading every key first would double the work for a check that cannot
be kept anyway.

Known deviations: a change between the read and the write is not seen; a row
deleted in that moment comes back with the changed cells only, which is how
Cassandra's `UPDATE` writes.
