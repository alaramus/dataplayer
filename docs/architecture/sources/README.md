# Data sources

What the five existing source types do, where their code sits, and which
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
| [mysql.md](mysql.md) | change how a MySQL or MariaDB server is reached, what its catalog shows, or how its values and pages are read |
| [ssh.md](ssh.md) | change how an SSH connection signs in, what server key it trusts, or where SSH keys and passphrases are kept |

## Five source types

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
nothing runs `KEYS`.

**SSH** — a server's folders over SFTP, from the folder the connection names or
the user's home: text files read a page at a time and Markdown as a document,
and five actions — a new folder, upload, download of one file, rename and
delete. Nothing runs a command on the server. It signs in with a password or
one of its owner's SSH keys, and only to the server whose key a person
confirmed when the connection was made (D145, D146).

**MySQL** — MySQL and MariaDB through one type that reads which server it is
(D228): databases as schemas, their tables and views with the server's row
estimates (D229), a relation's columns, keys, checks and indexes, its summary
and the server's own DDL, and rows paged, sorted and filtered on the server
with every value as exact text (D230, D231). Read only for now.

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
│                       content.py (SHOW CREATE), summary.py, adapter.py
├── redis/              session.py (reaching the server, and reducing its
│                       errors), keyspace.py (the databases, the tree, and
│                       what a key is), fetch.py (a key read as rows),
│                       update.py (one element of one written back),
│                       row_handle.py (which element, and what it held),
│                       actions.py (six ways to write one, three after),
│                       url.py (the address, both ways), samples.py (the
│                       demonstration key space), options.py (a union by
│                       auth_method), adapter.py (facade),
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
└── ssh/                see ssh.md
```
