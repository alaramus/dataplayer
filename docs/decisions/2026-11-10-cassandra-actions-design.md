# Cassandra's designer, catalog actions, reports, search and export

Decisions D347–D350, the fifth slice of the Cassandra source
([A Cassandra and ScyllaDB source](2026-11-10-cassandra-source-design.md)).

## The table designer (D347)

The designer's table becomes one `CREATE TABLE` and a `CREATE INDEX` per
secondary index, composed again from the definition when it runs and refused
when the reviewed plan's fingerprint differs, as every designer is (D117).

CQL's key has two parts the generic designer has not got. They ride on the one
engine this source offers, "Table", as a ClickHouse engine carries its
parameters (D274): its one parameter, **Partition key**, names the leading
columns of the primary key that form the partition. Left empty, the partition
key is the first column of the primary key, which is what `PRIMARY KEY (a, b)`
means in CQL. A partition that is not the leading columns is a problem beside
the engine. The rest of the primary key are the clustering columns. The
designer's storage page used to appear only when there was more than one
engine to choose; it now also appears when the one engine asks for columns.

The types are CQL's scalars, each also as a list; a duration and a list cannot
be in the key. A primary key is required. A unique key, a foreign key, a check,
a default, a computed column, a collation, `NOT NULL` outside the key, an
unlogged table and a partition by range, list or hash are problems beside the
object that asks for them. A table's and an index's name are letters, digits
and underscores, as the server demands; a column's may be anything. A comment
goes on the table.

A table made from a page's rows is not offered: such a table needs a key the
rows do not carry, and a key made up for it would be a column nobody asked
for.

## Catalog actions (D348)

- **New keyspace** at the top, replicated by `NetworkTopologyStrategy` in the
  node's own data centre, one to nine replicas. `SimpleStrategy` was rejected:
  ScyllaDB refuses it for a keyspace kept in tablets, and the other works on
  every server. The same keyspace, one replica, is what a copy or a load makes
  when it is asked for a new grouping.
- **Drop keyspace**, previewed with what it holds and refused unless the
  cascade is ticked when it holds anything.
- **Truncate** a table, asked as a question, not a deletion of the table.
- **Drop** tables and views, several at once. The server refuses to drop a
  table a materialized view reads, so the views over a table are named in the
  preview and dropped first.
- **Create table**, the designer.

No rename and no move: CQL renames neither a table nor a keyspace. The
server's own keyspaces offer nothing.

## Reports (D349)

A **Cluster** section after the keyspaces: nodes (`system.local` and
`system.peers`), clients, table sizes (`system.size_estimates`, summed per
table), settings and roles. CQL joins and groups nothing and these tables are
small, so a report reads its statements whole and shapes its rows here. The
products keep some of it in different places — Cassandra's clients and
settings in the virtual `system_views`, ScyllaDB's in `system.clients` and
`system.config`, and its roles in `system.roles` since 2025 rather than
`system_auth.roles` — and a report reads the one its server has. A report is
neither filtered nor sorted; it is read whole and cut into pages, and its
statement view shows what it reads.

## Search and export (D350)

CQL finds no part of a text without an index. `system_schema` is small, so a
search reads the names whole, under a ceiling of fifty thousand, and the shared
word rule classes and keeps the best, as SQLite's search does; columns are
found by name and relations by their comment the same way. Nothing typed
reaches a statement. ScyllaDB's hidden index views are left out here as in
the catalog.

Export is the page's own statement read on from paging state to paging state
in batches; a report is downloaded a page at a time.
