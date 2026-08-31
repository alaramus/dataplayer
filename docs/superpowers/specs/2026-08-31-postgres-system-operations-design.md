# What the old PostgreSQL adapter does beyond the table rounds

Date: 2026-08-31. Settles roadmap item 1.5's discovery bullet, and D54.

Sources read: `dbwebtool/webdb/data_adapter/postgre/` (all sixteen modules),
`dbwebtool/webdb/data_adapter/timescale/`,
`dbwebtool/webdb/core/supported_actions.py`,
`myquasar/src/myapp/views/ViewCatalog/menu/`,
`myquasar/src/myapp/components/DataSource/Timescale/` and
`myquasar/src/myapp/components/MasterViewer/TimescaleView/`.

The item asked for an inventory of extensions, processes, tablespaces, backups
and TimescaleDB, and for each one to be classified as a source-specific catalog
node kind, a declared action, or something deliberately left out. The inventory
is below. The classification has a fourth answer the plan did not anticipate,
and it is the largest group.

## The fourth answer: already covered

Every read-only list in the old application's "System's objects" menu is a
`SELECT` against one relation in `pg_catalog` or `information_schema`, wrapped
in a bespoke `extra_action` because the old fetch could only read a table the
catalog had listed, and the old catalog hid system schemas.

DataPlayer's catalog does not hide them. `_list_schemas` excludes only
`pg_toast%` and `pg_temp%`; `_list_relations` accepts `relkind IN ('r','p','v','m')`.
Checked against the running server, all eight relations behind those menu items
are listed by that query today, and a view among them fetches with paging,
sorting, filtering, charts, page download and streaming export — none of which
the old bespoke fetches had.

| Old action | Relation it reads | Status |
| --- | --- | --- |
| `get_system_processes` | `pg_catalog.pg_stat_activity` | already readable |
| `get_pg_roles` | `pg_catalog.pg_roles` | already readable |
| `get_pg_routines` | `information_schema.routines` | already readable |
| `pg_available_extensions` | `pg_catalog.pg_available_extensions` | already readable |
| `get_extensions_names` | `pg_catalog.pg_extension` | already readable |
| `connector_info` | `pg_catalog.pg_settings` plus a computed `changeable` column | readable; the explanation column is lost |
| `get_acid_settings` | `pg_settings` filtered to seventeen names | readable; the filter is lost |
| `tablespaces_info` | `pg_tablespace` joined to `pg_roles` and `pg_class`, with `pg_tablespace_size` and an object count | readable; size and count are lost |
| `get_partitions_child` | `pg_inherits` joined twice to `pg_class` | readable as `pg_inherits`; the join is lost |
| replication (`postgres_replicator.py`) | `pg_publication`, `pg_replication_slots` | already readable; was never wired to a menu |

So seven of these need nothing at all, and three are a query rather than a
relation. Porting the seven as node kinds would add a second way to read one
relation, which is the thing D2a exists to prevent. What is genuinely missing
for all ten is a **name**: a reader has to already know that "processes" means
`pg_stat_activity`. That is a discoverability problem, not a capability, and it
is queued below as its own small slice rather than as ten.

## What the inventory turned up instead: a write nobody refused

Six of those relations — `pg_tablespace`, `pg_extension`, `pg_publication` and
their neighbours — are stored as real tables, so `relkind = 'r'`. Fetch asked
only "is this a table?" before deciding a relation could be edited. It could,
and PostgreSQL performs the write for a superuser, which is how this tool
usually connects:

    BEGIN;
    UPDATE pg_catalog.pg_tablespace SET spcname = 'x' WHERE spcname = 'pg_default';
    -- UPDATE 1

D54 settles it, and is written up in
[adapters.md](../../architecture/adapters.md). The rule is not new — creating a
table in `pg_catalog` has been refused since D45 with the words `"pg_catalog"
belongs to the server` — it was simply stated in one place out of four. It is
now one predicate, `is_system_schema`, read by the catalog, by fetch and by the
relation model.

## The inventory, classified

### Declared actions, queued

| Old operation | What it does | Shape it takes here |
| --- | --- | --- |
| `extension_handler` | `CREATE`/`DROP EXTENSION`, name interpolated into the statement | two actions on the connector root; the name comes from `pg_available_extensions`, never from the client's text |
| `cancel`, `terminate` | `pg_cancel_backend(pid)`, `pg_terminate_backend(pid)` | blocked: see "the contract gap" below |
| `create_schema`, `drop_schema`, `rename_schema` | schema DDL; the old templates quote the identifier as a string literal and cannot ever have worked | actions on a schema node and on the root, beside D45 and D46 |
| `move_table_to_schema` | `ALTER TABLE … SET SCHEMA` | an action on a relation, issuing a `NodeReplacement` as D32's rename does |
| `create_database_user` | `CREATE USER x WITH PASSWORD '…'`, password interpolated | left out: a password through a statement is D2c's exact prohibition, and roles are a server-administration surface, not a data surface |
| `get_use_code`, `python_description`, `django_description`, `sqlalchemy_description` | generate ORM model source from a relation | left out: code generation for four frameworks, none of it about reading data |
| `generate_ddl`, `generate_cascade_ddl` | reconstruct `CREATE TABLE` text | a candidate content representation on a relation under D47, not an action — the answer is a document, not a change |

### Deliberately left out, with the reason

| Old operation | Why not |
| --- | --- |
| `create_backup`, `restore_backup` | a long job over every table, writing a zip into personal storage, with a progress bar and cancellation. Phase 4 introduces owned asynchronous jobs; building a second job model inside an adapter first is how the old application ended up with several. D44 already streams one relation out. |
| `monitor_system_stats`, `monitor_system_processes`, `include_story` | a polling loop that differences successive samples and stores them as statistics, and needs `pg_sys_cpu_usage_info()` from an extension that is not installed by default. This is Phase 7's realtime metric widgets. |
| `upload_datasource`, `upload_dashboard`, `grafana_stream_symbols` | Grafana is another system with its own credentials. Phase 6. |
| `dbdiagram`, `similar_tables`, `drawing_nodes`, `science` | diagram and similarity features over a whole database; each is its own slice and none belongs to 1.5. |
| `include_test_data` | a development fixture. `prestart` already owns that job here. |
| `transfer_table`, `copy`, `past`, `transfer_between_connectors` | done: D43 moves rows between any two sources, which is more than these did. |
| `download`, `stream_table` | done: D28 and D44. |
| replication publications and slots | `postgres_replicator.py` composes statements and is called from nowhere. Dead in the original; not ported. |

### TimescaleDB: one capability family, not part of Phase 1

The old application has a separate `TIMESCALE` source type extending the
PostgreSQL adapter, plus a `timescaledb` entry in the extension registry, plus
TimescaleDB branches inside the PostgreSQL adapter itself (`show_chunks`,
`hypertable_info`, `list_of_detached_chunks`, `approximal_row_count_ts`,
`GET_ALL_TS_TABLE_NAMES`). The frontend declares thirty-odd hypertable
operations: `to_hypertable`, compress and uncompress, ten chunk effects
(compress, uncompress, drop, drop by time, detach, attach, split, merge,
reorder, move), tablespace attach/detach/create/drop, and the retention,
compression, reorder, recompression and continuous-aggregate policies.

It is out of Phase 1, and the reason is a contract one rather than a size one.
TimescaleDB is not a source type: it is an extension of a PostgreSQL server,
present or absent per connection. Making it a source type — which is what the
old application did — means a second adapter that must be kept level with the
first forever, and it is D2b's rejected inheritance chain in a new place.
Doing it properly needs three things this project does not have yet:

- **capability discovery per connection**, not per source type: the same
  adapter class answering different questions depending on what `pg_extension`
  holds;
- **a node kind for a chunk**, since a chunk is a member of a hypertable in the
  sense D51 gave `dataset` — it has rows but is not addressed as a table;
- **owned asynchronous jobs**, because compressing a hypertable is not a
  request-scoped operation.

The first is the interesting one, and it is also what `extension_handler` and
the "list of available extensions" screen would want. It is recorded here as
the one prerequisite that unlocks the family, rather than as thirty queued
operations.

## The contract gap: an action on a row

`cancel` and `terminate` take a `pid` read from a row of `pg_stat_activity`.
Every action in this application applies to a *catalog node* — `applies_to` is
a set of `NodeKind`, `acts_on` is `node` or `children`. There is no way to
declare an action over the rows a reader ticked in the grid.

That is a real gap and it is not specific to PostgreSQL: killing a query,
revoking a session, cancelling a job and retrying a message are all the same
shape. It is left out of 1.5 on purpose, because inventing it for one command
would fix the shape around that command. "List of processes" without "cancel
this query" is half a feature, and half a feature is the honest state.

## Queued, in order

1. ~~**Named system relations.**~~ Done; the answer is below.
2. **Extension create and drop**, as two connector-root actions.
3. **Schema create, drop and rename**, and moving a relation between schemas.
4. **DDL as a content representation** of a relation.
5. **Row-scoped actions**, the contract gap above, whenever a second use for it
   appears.
6. **Per-connection capability discovery**, and TimescaleDB after it.

Items 1 to 4 close Phase 1. Items 5 and 6 are deliberate later capabilities,
which is what the phase's exit condition asks for.


## The deferred question, answered: a report is a statement

Item 1 above asked whether a source-defined query must be fetchable, and left
the shape open because the answer decides it. It must. Two of the three that
are a query rather than a relation are worth having precisely for the column
that no relation holds — the size and object count beside a tablespace, and a
sentence saying what changing a setting takes — and a reader cannot be asked to
write the join that produces them.

So the mechanism is one registry of statements, and the shortcut and the
computed answer use the same one. That is a correction to the caution written
above, that naming the seven plain relations would be "a second way to read one
relation". It would be, if each were a second implementation. It is not: a
registry entry is a `SELECT` and a title, every entry is read by the same
builder, and a curated shortcut to rows a reader could also reach the long way
is what a shortcut is. The alternative — six reports the reader cannot find and
two they can — was worse for no gain in code.

D55 states the contract, and
[adapters.md](../../architecture/adapters.md) carries the reasoning. The parts
worth restating here, because they are where the design could have gone wrong:

- **Columns are described, not declared.** The registry could have listed each
  report's columns beside its statement. The two would have drifted the first
  time a statement changed, and a wrong `ColumnType` is not a cosmetic error —
  `encode_cell` uses it. The statement is run with `LIMIT 0` instead, and
  psycopg's cursor description plus one `pg_type` lookup builds exactly the
  `ColumnType` a relation's columns are built from.
- **The report becomes the `FROM` of the existing builder**, so filters, sort,
  paging, the limit ceiling and identifier validation are the same code. The
  only new thing `PreparedRead` carries is what to select from.
- **The section's id is `pg_dataplayer`.** PostgreSQL refuses to create a schema
  whose name starts with `pg_`, so this cannot collide with a schema a user
  makes. The guarantee is the server's, not a convention.

Six reports are registered: processes, settings, tablespaces, roles, routines
and extensions. Extensions is one where the old application had two, because
`pg_available_extensions` already states the installed version.

What this does not do, deliberately: a report has no row estimate, offers no
foreign key to follow, and answers no relation model. Each is written up as a
known deviation beside D55 rather than left to be discovered.
