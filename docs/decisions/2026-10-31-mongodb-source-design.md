# A MongoDB source

Decisions D283–D285. The first slice of a MongoDB source type that is meant to
reach what the SQL sources do, in the six slices MySQL, SQLite and ClickHouse
went through, where MongoDB has a notion of the thing at all. This slice
reads: a connection, its catalog, a collection's model, its summary and
definition, and its documents. Writing documents, indexes, reports and
actions, exports, copies, backups, sample data and metrics follow, each in its
own commit. The console is not a parsed language here: it is `mongosh` in a
terminal, decided with the user and built in the second slice.

MongoDB was picked because it is the first source that is neither SQL, nor a
key space, nor a tree of files: a document store, whose collections have no
columns of their own.

## The driver (D283)

Three ways to reach it were weighed:

- Motor — rejected: it is the synchronous driver run in a thread pool, and
  its maintainers have moved to pymongo's own asynchronous client;
- the wire protocol by hand — rejected: authentication alone is SCRAM over a
  handshake that changes between releases;
- pymongo's `AsyncMongoClient` — chosen. It is the vendor's, asynchronous
  without a thread, and `bson` comes with it.

`directConnection` is always set. Discovery would follow a replica set to the
names its members give each other, which are often not reachable from here
and never through a tunnel (D282). The cost is that a secondary cannot be
written through and a `mongodb+srv://` cluster cannot be named; both are
deviations rather than half-working paths.

The connection check asks for `listDatabases` as well as `buildInfo`, because
a server with access control answers `buildInfo` to anybody: without it a
connection with no password would pass its check and fail on its first page.

## Collections as tables (D283)

A collection is a `TableNode` with `term: "collection"`, the way a MySQL
database is a schema named as a database (D229). A kind of its own was
weighed and rejected: a collection is read as rows, described as a relation
and later copied, edited and indexed like a table, and every one of those
paths names the table kind. What differs is the word, and the word is what
`term` carries.

## Columns from documents (D284)

The user chose columns over one JSON column per document: sorting, filtering
and reading need columns. Where they come from:

- `$sample` — rejected: two reads of an unchanged collection give different
  columns, so a filter that named a field could be refused by the next read
  of the same page;
- every document — rejected: a full scan to open a collection;
- the validator's declared properties, then a hundred documents from each end
  in natural order — chosen. It is deterministic for an unchanged collection,
  sees both the oldest and the newest shape of a document, and costs two
  bounded reads.

Fields seen on a page but missing from the sample are still drawn, offered for
nothing, so a document is never shown with a field missing.

Values cross as text (D23). An ObjectId as bare hex and a date as ISO with `Z`
are what a reader types back into a filter; everything nested is relaxed
Extended JSON, which keeps the type of what has no plain spelling
(`{"$date": …}`, `{"$binary": …}`) and is what `mongosh` shows.

## Pages (D285)

A filter is built here as a query document from the closed set of predicates,
so no client text is ever an operator: `{"$ne": null}` typed as a value is a
string compared for equality. Field names must be in the model and addressable
by a path. The order is the reader's sort and then `_id`, which every stored
document has and which is unique, so `skip` pages never repeat a document.
`skip` is bounded by the grid's own offset; keyset paging was weighed and left
for when a page past the first hundred thousand documents is asked for.
