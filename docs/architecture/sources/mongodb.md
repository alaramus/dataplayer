# MongoDB

What a MongoDB source is, how it reaches the server, what its catalog shows,
how a collection becomes columns, how its documents cross to the grid and
how they are changed there, and how a collection's fields and indexes are
changed. Its
console is `mongosh` in a terminal, run in a container (D286, in
[terminals.md](../terminals.md)). The
contract every source type follows is in [contract.md](contract.md); reading a
relation in general is in [relations.md](relations.md). Read this before
changing the `mongodb` adapter.

Decisions here: D283, D284, D285, D287, D288.

## D283. A MongoDB source speaks to one server through pymongo

The adapter uses pymongo's own asynchronous client (`AsyncMongoClient`); Motor
is not used. pymongo and the `bson` package that comes with it are imported
by `app.adapters.mongodb` and nothing else, which an import-linter contract
holds. A connector keeps one client in the resource store; the client is a
pool of its own. A server error is reduced by its code, never by its text.

The client is made with `directConnection`: the host named is the server
spoken to, alone or as one member of a replica set, and a tunnel's end
(D282) is never traded for the names a set calls its members by. Moments come
back aware and in UTC, and a UUID is the standard binary subtype.

Options are host, port (27017), TLS (verified), and either a user, a password
and an authentication database (`admin` unless named), or no password for a
server without access control. An optional database says where the catalog
opens. `mongodb://` addresses with one host are parsed; without `authSource`
the user is looked for in the database the address names, as the driver does.
The check reads `buildInfo` and lists the databases the user may see, so a
server with access control refuses a connection without a password there
rather than at the first page.

The catalog is databases as schemas, named as databases, with MySQL's node
ids (D229); a database name cannot hold a dot, and a collection name may, so
everything after the first dot is the collection. Databases are those
`listDatabases` with `authorizedDatabases` returns; the one the connection
names is listed even when nothing is stored in it yet, since MongoDB has no
empty database. `admin`, `local` and `config` belong to the server, and so
does a collection named `system.*`. Inside a database are its collections and
time series, tables to everything else here named as collections
(`TableNode.term`), and its views. A collection's count and size are
`$collStats`, asked for each collection in one gather, and not at all past two
hundred collections.

A collection has no DDL. Its definition is what `listCollections` says of it —
type, options with the validator, a view's source and pipeline — and its
indexes, offered as the `json` representation.

MongoDB 5.0 and later; the check refuses an older one with its version named.

Known deviations:

- No replica set is discovered: a `mongodb+srv://` address and a seed list are
  refused, and a write to a secondary is refused by the server.
- A self-signed certificate cannot be trusted; TLS is verified or off.
- A user without `collStats` sees collections without counts.

Spec: [A MongoDB source](../../decisions/2026-10-31-mongodb-source-design.md)

## D284. A collection's columns are its validator's and its documents' fields

Columns are the properties a `$jsonSchema` validator declares, in its order,
then the fields of the first and the last hundred documents in natural order,
in the order they are met; `_id` is first, and a collection that shows none
still has one. Both ends rather than `$sample`, so an unchanged collection
gives the same columns every time and a filter that named one is not refused
by the next read. A view and a time series have no natural order to read
backwards and give their first two hundred.

A column's type is the BSON type its documents hold, by `$type` name, with
`int`, `long`, `double` and `decimal` together as `number` and disagreement as
`mixed`; a column is nullable unless every document read holds a value or the
validator requires it. The grid's category follows: a string, a number, a
date, a UUID and bytes as themselves, an ObjectId and a mixed field as other,
an object and an array as JSON.

A value crosses as text (D23): a number as written, NaN and infinity as words,
a `Decimal128` with its digits, an ObjectId as its hex, a date in UTC with `Z`
and milliseconds, a UUID canonically, bytes of subtype 0 as `0x…`; an object,
an array and every other BSON value as compact relaxed Extended JSON, the form
`mongosh` and `mongoexport` write. A missing field and a null are both an
empty cell.

A field met on a page but not in the sample is added to that page's columns
and offered for nothing, so nothing on the page is hidden.

Known deviations:

- A field present only in documents between the two ends is not a column, and
  cannot be sorted or filtered by, until a document holding it is on the page.
- A field whose name holds a dot or begins with `$` is shown and offered for
  nothing: no query path can name it.

Spec: [A MongoDB source](../../decisions/2026-10-31-mongodb-source-design.md)

## D285. A page is a find with a query document built here

A filter becomes a query document from the closed set of predicates, naming
only a column of the model and only one a path can address. Its value is read
as the column holds it — a number by its width, a date as a moment (UTC when
no offset is given), an ObjectId by its hex, a UUID, a truth word — and text
that will not read refuses the request before the server is asked. `contains`
and `starts_with` are an escaped `$regex`, for strings only; `is_null` matches
a null and a missing field alike. Comparisons are BSON's: an ObjectId orders
by when it was made. An object, an array and bytes cannot be sorted; nothing
the client sends becomes an operator.

A page is `find` with the reader's sort and then `_id`, `skip` and a limit one
past the page to know whether there is another, stopped by the server after a
minute.

Spec: [A MongoDB source](../../decisions/2026-10-31-mongodb-source-design.md)

## D287. A document is named by its `_id` and changed only as it was read

A page's row handle is the document's `_id` as canonical Extended JSON, so an
id of any BSON type comes back as exactly itself, and a digest of the whole
document as it was read (`app.adapters.row_handles`, D234). A change reads the
document by its id, compares the digest, and writes with a filter that holds
the document read compared whole by the server
(`$expr: {$eq: ["$$ROOT", {$literal: …}]}`), so a document changed in between
matches nothing and the change is a conflict, answered 409.

A cell's text is stored as its column holds values (D284): a number by its
width, a date as a moment, an ObjectId by its hex, bytes from `0x…`; an object
or an array from relaxed Extended JSON; a mixed field from JSON when the text
is JSON and as a string when it is not. An empty cell is null. `_id` is never
editable, and a field no query path can name is neither editable nor
insertable. A new document holds the fields given and no others: an empty
value is no field, and the driver makes an `_id` when none is given.

A pasted block and a deletion are checked whole before anything is written and
then applied document by document, each all or nothing, as ClickHouse's rows
are (D272). A block of new documents goes in with one ordered `insertMany`;
when the server refuses one, those it took before it are deleted again, so the
block goes in whole or not at all. A unique index's and a validator's refusals
are said by their codes.

A view's documents come from its pipeline and are not changed; a time series
takes new documents and changes none; the server's own collections take
nothing.

A collection is also offered as its documents whole (`jsonl`, "View as
documents"): a page of documents by `_id` as relaxed Extended JSON trees, one
past 256 KB shown as the beginning of its text.

Known deviations:

- A block is not a transaction. A conflict on the tenth document of a paste
  leaves the nine before it changed; a replica set's transactions are not used.
- A missing field and a null are both an empty cell, so emptying a cell writes
  null rather than removing the field.

Spec: [MongoDB documents](../../decisions/2026-10-31-mongodb-documents-design.md)

## D288. A field is changed in every document, and an index is MongoDB's own

A collection has no columns, so a column's change is a change to every
document that has the field, made by the server with one `updateMany`: added
as null where it is missing (a new field is nullable, and its type is only
what it will hold), dropped with `$unset`, renamed with `$rename`, converted
with `$convert` in a pipeline update. A conversion first counts the documents
whose value would not convert, up to ten thousand, and changes nothing when
there are any (`ColumnTypeBlocked`); null and missing stay as they are. `_id`
is never changed, and a new name must be one a query can address and not one
already there. The types offered are those `$convert` reaches: text, 32- and
64-bit integers, double, decimal, truth, date and ObjectId.

Indexes are made with `createIndex` on the fields chosen, in their order, of
one kind for all of them: ascending, descending, hashed (one field, not
unique), text and 2dsphere (not unique). A unique index first counts the
groups of documents that share their values — missing counts as null, as the
index would see it — and is not made when there are any (`IndexBlocked`). The
server names an index as it does (`n_-1_label_-1`); `_id_` cannot be dropped.

A view's fields are its pipeline's and a time series keeps its fields in
buckets: neither is restructured here, and neither are the server's own
collections.

Known deviations:

- A change to every document is not atomic: a server that stops halfway
  leaves some documents changed. A conversion's count makes the refusal that
  matters happen before anything is written.
- No unique and foreign keys beyond unique indexes, and no validator editing:
  a collection's `$jsonSchema` is changed in `mongosh` (D286).

Spec: [MongoDB structure](../../decisions/2026-10-31-mongodb-structure-design.md)
