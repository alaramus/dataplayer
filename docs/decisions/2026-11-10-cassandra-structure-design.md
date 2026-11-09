# Changing a Cassandra table's structure

Decision D346, the fourth slice of the Cassandra source
([A Cassandra and ScyllaDB source](2026-11-10-cassandra-source-design.md)).

## Columns and secondary indexes (D346)

What CQL's `ALTER TABLE` can do is narrower than SQL's, and the model says so
rather than offering what the server refuses:

- **add** a column of a type from a closed list — the scalars, and a list, a
  set and a map of text;
- **drop** a column outside the primary key; the server refuses one an index
  or a materialized view reads, and its sentence is passed on;
- **rename** a column of the primary key, and only such a column — Cassandra
  and ScyllaDB rename nothing else. A regular column is refused with that
  reason before anything is sent;
- no default, no `NOT NULL` and no change of type: Cassandra has no defaults,
  no column outside the key requires a value, and 4.0 removed `ALTER … TYPE`.

A secondary index is made on one column and dropped by name, its name made up
from the table's and the column's. The methods are the products' own:
Cassandra 5 offers the storage-attached index (`sai`) and the legacy one,
Cassandra 4 the legacy one; ScyllaDB its global index. A collection is indexed on its
values. Nothing is unique.

A materialized view, a virtual table and the server's own keyspaces change
nothing.

The table designer, which makes a table rather than changing one, comes with
the catalog's actions, through whose `create_table` it creates.
