# MongoDB copies, backups, metrics and the lab

Decisions D291–D294. The sixth slice of the MongoDB source (D283–D290): what
the other database sources gained last — copying tables with their structure,
backups, metrics, the service template and sample data.

## Copies within one dialect (D291)

Copy tables (D182) moves tables between sources of one dialect, because a
second dialect would have to translate the source's description. A MongoDB
collection is not a table in any SQL dialect, so MongoDB is a dialect of its
own: the description is the collection's options and its indexes, and the
rows are its documents.

The documents travel as canonical Extended JSON rather than the text a cell
shows (D284): a copy must keep `Int64`, `Decimal128` and an ObjectId as what
they are, and canonical JSON is the one text form that does. BSON itself was
weighed and rejected: the transfer's progress counts lines, and a line per
document keeps that true.

Indexes are built after the documents, as the SQL sources build theirs after
the rows: once over all of them rather than document by document, and a
unique index that the documents break fails the copy in one place, which is
then undone.

## Backups (D292)

`mongodump` and `mongorestore` are the vendor's tools and come in the image the
console already uses. Their archive keeps collections, views, indexes and
options, which a hand-written dump would have to reproduce. Both take the
password on the command line or in a configuration file; the command line is
what D87 forbids, so a shell line writes the file inside the container, with
a umask that keeps it the tool's, from an environment variable it then unsets.

The inventory a restore checks first is a dry run of `mongorestore`, which
lists the archive's prelude without writing, after `gzip -t` reads the archive
to its end: a dry run alone stops at the prelude and would pass a truncated
file.

## Metrics (D293)

`serverStatus` is the server's own account of itself and every user with
`clusterMonitor` may read it. The counters among its fields are reported as
counters, so a dashboard draws their rate.

## The template and the lab (D294)

The image's `MONGO_INITDB_ROOT_*` variables make a root user in `admin`, which
is what the connection then signs in as. The lab is made by code rather than
a script because documents are values: a script would be JSON this module
writes anyway. A seeded generator keeps every lab the same, which a test
checks.
