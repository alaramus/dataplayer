# MongoDB documents

Decision D287. The third slice of the MongoDB source (D283–D286): changing
documents from the grid, and reading them whole.

## Naming a document

Every stored document has an `_id`, unique in its collection and never
changed, so it is the key PostgreSQL's primary key is. What it is not is text:
an id may be an ObjectId, a number, a string, a UUID, even a document. The
handle carries it as canonical Extended JSON, which keeps the type exactly
(`{"$numberLong": "7"}` is not `7`), rather than as the hex or text a cell
shows.

A version was needed beside it, as D25 versions a row. MongoDB keeps none a
client can read, so the version is a digest of the document as it was read,
the way MySQL's and ClickHouse's rows carry one (D234, D272). Checking a
digest and then writing leaves a moment between; the write itself is
therefore filtered by the whole document read, which the server compares as
one value in the same operation, and a document that changed in that moment
is not matched. Rejected: an `updatedAt` field the application would maintain
— it would write into the user's documents and protect only writes that went
through here.

## Typing a value

A cell is text, and the field's type decides what it becomes (D284): the
same reading a filter's value gets, plus relaxed Extended JSON for objects
and arrays, which is what the cell showed. A mixed field takes JSON when the
text is JSON, so `42` is a number and `hello` a string; that is a guess, and
it is the guess `mongosh` makes when a value is typed into it.

An emptied cell becomes null rather than removing the field. Both show as an
empty cell, and removing a field from one document is a structural change the
next slice offers for a whole collection.

## Many documents

A server alone has no transactions, and a replica set's need a session this
source does not yet keep. A paste is therefore checked whole — every value
typed, every handle readable — and then written a document at a time, each
under its own filter. A block of new documents is the exception that can be
made whole: an ordered `insertMany` stops at the first refusal, and the
documents before it are deleted again by the ids the driver gave them.

## Documents whole

The grid shows a document as columns, which loses its shape. The `jsonl`
representation the file explorer already uses for JSON lines — a page of
records, each a JSON tree — shows each document as itself, every level of it.
No new viewer was needed.
