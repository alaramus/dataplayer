# Data sources

What the two existing source types do, where their code sits, and which file
holds which decision.

| File | Open it to |
| --- | --- |
| [contract.md](contract.md) | add or change a source type, a capability, a node kind or the rule about untrusted input |
| [connecting.md](connecting.md) | change how a connection is described, composed or parsed, or anything pooled or cached between requests |
| [relations.md](relations.md) | read a relation or change the rows in it |
| [ddl.md](ddl.md) | change a column, an index, a constraint, or rename a node |
| [content.md](content.md) | open a node as something other than a page of rows |
| [actions.md](actions.md) | add an action, change what a form applies to, or add a report |

## Two source types

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
directory or selection. No sorting and no filtering, because a file has no
index. No connection string.

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
├── cache.py            bounded read cache, coalescing, connector invalidation
├── postgres/           session.py and pool.py (reaching the server), catalog.py,
│                       fetch.py, export.py, update.py, references.py,
│                       relation.py + columns.py + constraints.py + indexes.py
│                       (describing), relation_changes.py, column_type(s).py,
│                       index_methods.py, counting.py (the bounded count),
│                       row_handle.py, content.py, system_reports.py,
│                       actions.py, options.py (a union by auth_method),
│                       adapter.py (facade)
└── file/               session.py (root and containment), catalog.py,
                        formats.py, members.py (a node inside a file),
                        readers.py, records.py, fetch.py, update.py,
                        content.py, binary.py, media.py, parquet.py,
                        workbook.py, archive.py, download.py, relation.py,
                        summary.py, search.py, actions.py, options.py,
                        adapter.py (facade)
```
