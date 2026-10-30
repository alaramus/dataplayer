# Data sources

What the seven existing source types do, where their code sits, and which
file holds which decision.

| File | Open it to |
| --- | --- |
| [contract.md](contract.md) | add or change a source type, a capability, a node kind or the rule about untrusted input |
| [catalog.md](catalog.md) | change what a catalog shows of a node, how it is searched, or a key space |
| [connecting.md](connecting.md) | change how a connection is described, composed or parsed, or anything pooled or cached between requests |
| [timescale.md](timescale.md) | implement the designed Timescale feature package, runtime discovery and extension-aware operation restrictions |
| [operations.md](operations.md) | add a source action too long for one request, or change how its targets are planned and recorded |
| [relations.md](relations.md) | read a relation or change the rows in it |
| [transfer.md](transfer.md) | copy rows between sources, load a file into a relation, or export every row |
| [declared.md](declared.md) | draw a reference between two columns no source calls related |
| [ddl.md](ddl.md) | change a column, an index, a constraint, or rename a node |
| [content.md](content.md) | open a node as something other than a page of rows |
| [actions.md](actions.md) | add an action or change what a form applies to |
| [downloads.md](downloads.md) | add a download, change what one asks first, or add a report |
| [mysql.md](mysql.md) | change how a MySQL or MariaDB server is reached, what its catalog shows, how its values and pages are read, or its reports and search |
| [sqlite.md](sqlite.md) | change how a SQLite file is opened and guarded, what its catalog shows, what is read from a table's text, how its values and pages are read, or how its tables are copied and the file backed up |
| [clickhouse.md](clickhouse.md) | change how a ClickHouse server is reached over HTTP, what its catalog shows, how its values and pages are read and changed, how its structure is changed and a table designed, its reports, search and catalog actions, or its console |
| [mongodb.md](mongodb.md) | change how a MongoDB server is reached, what its catalog shows, how a collection becomes columns, or how its documents are read |
| [ssh.md](ssh.md) | change how an SSH connection signs in, what server key it trusts, what its System reports show, or where SSH keys and passphrases are kept |

## Eight source types

**PostgreSQL** — schemas and relations, safe schema create/rename/drop and
relation moves, bounded relation DDL, server-side paging and sorting, streaming
whole-relation export, six reports it publishes about itself, a connection
string composed by the driver and parsed back from a pasted one, two ways of
connecting (`user_password` and `no_auth`), and connections that outlive a
request in a pool. Relations the server owns are read but never changed.

**File** — the personal directory every user owns. The catalog is directories
and files, and every leaf declares its ordered representations: delimited data
opens as a table, JSON and JSONL as structured content, Markdown as a rendered
document, and plain files as text. Supported files may also be projected into a
table by an explicit request. Delimited files expose atomic row and header
changes while keeping every column text. A Parquet file and each sheet of a
workbook are datasets: they state their own columns, so they are read as rows
and described like a relation, and a workbook is walked into rather than opened.
A zip is walked into the same way. Every node describes itself — its size, its
times, what it can be opened as and what its format states — and the tree is
searched by name from any folder. Five actions: create a folder, upload,
download, rename and delete. Download returns one file unchanged or archives a
directory or selection. Rows are looked up by equality and by nothing else, and
never sorted, because a file has no index. No connection string.

**Redis** — every database on the server as a grouping, and inside the one
that is open, a key space shown as a tree of the colons its names already
carry: the top lists the first segment of every key, and opening one shows the
next. The database in the connection says where the catalog opens, not where
it stays. A key says its type, its size and how long it has left, and a click
opens it in a tab as rows — a hash as fields and values, a list as positions
and values, a sorted set as members and scores, a string as one value. Nine
actions: a key of each of the six types Redis has, written where the catalog
is standing and with an optional expiry, then delete, set an expiry and take
one off. An address is composed and parsed the way PostgreSQL's is. No sorting
and no filtering, because Redis has no index over values, and no query
console, because Redis has commands rather than statements. Everything scans;
nothing runs `KEYS`. A System section leads the catalog with read-only Server
and Settings reports: a fixed selection from `INFO` and a safe allowlist of
`CONFIG GET` values (D265).

**SSH** — a server's folders over SFTP, from the folder the connection names or
the user's home: text files read a page at a time and Markdown as a document,
and five actions — a new folder, upload, download of one file, rename and
delete. Nothing runs a command on the server. It signs in with a password or
one of its owner's SSH keys, and only to the server whose key a person
confirmed when the connection was made (D145, D146).

The System section leads the catalog with a Connection report of saved options
and negotiated protocol details, plus a Filesystem report when the server's
SFTP implementation provides capacity statistics. These reports make no
remote shell calls (D266).

**MySQL** — MySQL and MariaDB through one type that reads which server it is
(D228): databases as schemas, their tables and views with the server's row
estimates (D229), a relation's columns, keys, checks and indexes, its summary
and the server's own DDL, and rows paged, sorted and filtered on the server
with every value as exact text (D230, D231). An SQL console read by sqlglot's
MySQL dialect, where a structure change runs alone and is never rehearsed,
because MySQL commits it at once (D232, D233). Rows are edited, inserted and
deleted in the grid against a digest of what was shown, and keys are followed
both ways (D234). Columns, indexes and constraints are changed in the
definition the server printed (D235). A designed table is planned as one
`CREATE TABLE`, and a table made from rows is dropped if its rows are refused
(D236). Eight reports about the server sit in a System section, and the
processes can be cancelled or terminated; the catalog is searched by name and
by column, and every matching row is exported (D237). Databases are created
and dropped, relations renamed, moved and dropped, and a CSV file loaded,
with previews read from `information_schema` (D238). Tables are copied with
their structure between MySQL and MariaDB connections (D239), a database is
backed up by its own family's dump program (D240), and the server's counters
feed dashboards (D241). A row of a table with no key is named by its values
(D242), and an account is made from the Users report (D243).

**SQLite** — a database file of the owner's storage, opened per call by the
standard library with everything that reaches past the file refused (D247):
one schema, `main`, with its tables, views and virtual tables and the
estimates `ANALYZE` left (D248), a relation's columns, keys, checks and
indexes from the pragmas and the table's own text (D249), its summary and the
file's own DDL, and rows paged, sorted and filtered with every value shown by
its storage class (D250), in the order of the primary key or the rowid
(D251). An SQL console whose statements are classed by SQLite's first keyword
(D252), and which, since SQLite's structure changes are transactional, runs,
holds and rehearses them as PostgreSQL's does, with foreign keys enforced
(D253). Rows are edited, inserted and deleted in the grid, named by their
primary key or rowid and checked against a digest of what was shown, and keys
are followed both ways (D254). Columns, indexes and constraints are changed
by SQLite's ALTER TABLE or by rebuilding the table from its own text, edited
(D255). A designed table is planned as statements run in one transaction, its
identity the rowid (D256). The file's pragmas are reports in a System section,
the catalog is searched by name and column, and every matching row is
exported (D257). Relations are renamed and dropped — a drop rehearsed first —
and a CSV file loaded (D258).

**ClickHouse** — a server reached over its HTTP interface with the
application's own client, every value one of the server's parameters and every
read `readonly=2` (D267): databases as schemas, their tables, views and
materialized views with the counts MergeTree keeps, a relation's columns, keys,
skipping indexes and checks, its summary and the server's own DDL, and rows
paged, sorted and filtered on the server with every number as the server wrote
it and every moment in UTC (D268). No key is unique, so a page is ordered by
the sorting key and then the whole row (D269). An SQL console read by sqlglot's
ClickHouse dialect with the server's own `{name:Type}` parameters (D270), in
Read and Auto-commit only, where a change runs alone because ClickHouse keeps it
at once (D271). Rows are edited, inserted and deleted in the grid, a row named by its
whole row and rows alike changed together (D272). Columns and skipping indexes of
MergeTree tables are changed, a conversion counted before the mutation that
would break the table (D273). A designed table is one CREATE TABLE of a MergeTree, its primary key
the sorting key (D274). Eight reports about the server sit in a System section, a query can
be cancelled and a stuck mutation stopped; the catalog is searched by name and
by column, and every matching row is exported (D275). Databases are created and dropped,
relations renamed, moved and dropped with previews from the system tables, and
a CSV file loaded (D276).

**MongoDB** — one server through pymongo's asynchronous client, spoken to
directly (D283): databases as schemas, their collections as tables named as
collections and their views, a collection's definition as JSON, and its
documents as rows whose columns are the fields its validator declares and its
documents at both ends hold, every value as text and nested ones as relaxed
Extended JSON (D284), paged, sorted and filtered by a query document built
from the closed predicates (D285).

## Where the code is

```
backend/app/adapters/
├── protocol.py         every capability protocol, AdapterError, NodeNotFound
├── registry.py         type registry, AdapterContext, Category, Capability,
│                       capabilities_of
├── routes.py           GET /adapter-types
├── options.py          the one seam over an options schema, model or union:
│                       json_schema / validate / variants / secret_field_names
├── layout.py           where a field goes in the window that edits it
├── catalog.py          CatalogNode: a union discriminated by kind; NodeKind
├── cells.py            the canonical text of one value, shared by every source
├── fetch.py            FetchRequest, FetchResult, closed set of predicates
├── export.py           ExportRequest and bounded ExportBatch
├── update.py           row handles, edits and their refusals
├── references.py       following a foreign key, and its two answers
├── relation.py         relation, column, constraint and index models
├── relation_changes.py creating and dropping a relation
├── column_changes.py   add, drop, rename, default, nullability, type
├── indexes.py          index create and drop
├── constraints.py      unique and foreign key
├── content.py          ordered node representations and bounded content results
├── summary.py          what a node is: its facts, and what its format states
├── search.py           finding a node by name: the request, a match, the answer
├── jsontext.py         the JSON and JSONL content shapes
├── dataset.py          what only a file format knows about the dataset in it
├── delimited.py        the delimiter rule, shared by the file source and D45
├── actions.py          Action, ActionSet, SupportsActions, ActionType,
│                       DeclaresActions, transports, refusals
├── resources.py        ResourceStore: what outlives a request; Pooling
├── credentials.py      a signing key handed to a driver, a pinned server key
├── cache.py            bounded read cache, coalescing, connector invalidation
├── words.py            vocabulary titles worded in the language of the request
├── compose.py          a statement from fixed text and quoted names, for
│                       drivers without psycopg's sql module
├── postgres/           session.py and pool.py (reaching the server), catalog.py,
│                       fetch.py, export.py, update.py, references.py,
│                       relation.py + columns.py + constraints.py + indexes.py
│                       (describing), relation_changes.py, column_type(s).py,
│                       index_methods.py, counting.py (the bounded count),
│                       row_handle.py, content.py, system_reports.py,
│                       actions.py, roles.py, backup.py, samples.py +
│                       sample_data/ (the demonstration schema),
│                       options.py (a union by auth_method),
│                       adapter.py (facade)
├── mysql/              session.py and pool.py (reaching the server, the
│                       profile), sql.py (composing a statement), ids.py,
│                       inspection.py (information_schema, once), catalog.py,
│                       relation.py, fetch.py, types.py (values as text),
│                       content.py (SHOW CREATE), summary.py, statements.py
│                       (classing SQL), query.py (runs, transactions, KILL
│                       QUERY), explain.py, metadata.py, rows.py (handles,
│                       values written back), update.py, references.py,
│                       definitions.py + columns.py + keys.py (structure),
│                       vocabulary.py (types, index kinds), design.py
│                       (the designer), relation_changes.py, actions.py,
│                       reports.py + row_commands.py (System), search.py,
│                       export.py, table_copy.py, backup.py, metrics.py,
│                       users.py (New user), samples.py + sample_data/
│                       (the lab a started server opens on),
│                       adapter.py
├── sqlite/             session.py (opening the file, guarded, in a thread),
│                       definition.py (reading a CREATE TABLE), inspection.py
│                       (pragmas and text, once), catalog.py, ids.py, sql.py,
│                       relation.py, fetch.py, types.py (values by class),
│                       content.py, summary.py, features.py, options.py,
│                       statements.py (classing SQL), query.py (runs,
│                       transactions, rehearsals), explain.py, metadata.py,
│                       rows.py (handles, values written back), update.py,
│                       references.py, restructure.py (the rebuild),
│                       columns.py + keys.py (structure), vocabulary.py,
│                       design.py (the designer), relation_changes.py,
│                       actions.py, reports.py (System), search.py,
│                       export.py, table_copy.py, backup.py, samples.py +
│                       sample_data/ (the lab, a file),
│                       adapter.py
├── clickhouse/         session.py (the HTTP interface, its errors, addresses)
│                       and pool.py (a kept client), sql.py (names and
│                       parameters), inspection.py (system.tables, once),
│                       catalog.py, relation.py, fetch.py, types.py (types
│                       read from their text, values as written), content.py
│                       (SHOW CREATE), summary.py, features.py, statements.py
│                       (classing SQL), query.py (runs, KILL QUERY),
│                       explain.py, metadata.py, rows.py (a row by its
│                       values, written back), update.py, columns.py +
│                       indexes.py (structure), vocabulary.py, design.py
│                       (the designer), relation_changes.py, actions.py,
│                       reports.py + row_commands.py (System), search.py,
│                       export.py, adapter.py
├── mongodb/            session.py (pymongo's client, its errors, addresses),
│                       values.py (BSON as text, fields from documents),
│                       inspection.py (a collection, its sample), catalog.py,
│                       relation.py, fetch.py, content.py (the definition),
│                       summary.py, adapter.py
├── database_ids.py     a database and a relation as one node id (D229)
├── row_handles.py      a handle of values and a digest of the row (D234, D272)
├── redis/              session.py (reaching the server, and reducing its
│                       errors), keyspace.py (the databases, the tree, and
│                       what a key is), fetch.py (a key read as rows),
│                       update.py (one element of one written back),
│                       row_handle.py (which element, and what it held),
│                       actions.py (six ways to write one, three after),
│                       url.py (the address, both ways), samples.py (the
│                       demonstration key space), options.py (a union by
│                       auth_method), reports.py (System), adapter.py (facade),
├── explorer/           a tree of files wherever it is kept (explorer.md):
│                       storage.py (the contract a source brings),
│                       explorer.py (facade), catalog.py, formats.py,
│                       members.py (a node inside a file), readers.py,
│                       records.py, fetch.py, update.py, content.py,
│                       binary.py, media.py, parquet.py, workbook.py,
│                       archive.py, packing.py, download.py, relation.py,
│                       new_relation.py, query.py, summary.py, search.py,
│                       actions.py
├── file/               storage.py (the local disk: root and containment),
│                       options.py, adapter.py (the explorer over it)
└── ssh/                see ssh.md; reports.py (System, over SSH and SFTP only)
```
