# ClickHouse copies, backups and metrics

Decisions D277, D278 and D279. The first half of the sixth slice of the
ClickHouse source: copying tables with their structure, a backup and its
restore, and the counters a dashboard reads.

## Copying from catalog parts

MySQL's copy reads `SHOW CREATE TABLE` and composes the destination's
statement from parts (D239); ClickHouse's `create_table_query` is one string
that names its database, and replacing that name inside it means parsing the
statement. The parts are in the catalog already — `system.columns` for each
column's expression, codec and comment, `system.data_skipping_indices` for the
indexes, `engine_full` for the engine with its keys and settings — so the copy
is composed from them, each checked to stand alone with ClickHouse's quoting.

Replicated and shared engines are refused: their definition names a path in
the coordinator, and a copy with the same path would be a replica of the
original rather than a copy. Tables over a URL, a file, a stream or another
server have no rows of their own.

## TabSeparated for the rows

The rows are the server's own text. TabSeparated reads back exactly what it
writes, including arrays, maps, NaN and moments, without the application
knowing any of the types; JSON would need the booleans bare and the large
integers quoted, and is larger.

The HTTP interface reports a failure that happens after the first rows by
writing `__exception__` and the message into the answer. The last 64 KB of a
stream are held back until it ends, so a failure is not handed on as rows.

## A backup by script

Three programs could copy a database out. `clickhouse-client` speaks the native
protocol on port 9000, which the connection does not know and which a server
behind a proxy may not publish at all. `BACKUP DATABASE … TO Disk(…)` writes
where the server is, and the job model of D87 expects a file in the owner's
storage. The HTTP interface the connection already uses is the one way that
always works, and a script of the standard library in the Python image speaks
it. The image is the one SQLite's backup uses, so a host keeps one image for
both.

The format is the script's own, a text file: JSON lines for what the file is
of and the statements that make each object, then each table's rows as
TabSeparated. A row cannot be the line `\.`, since TabSeparated writes a
backslash as two, so that line ends a table's rows, as it does in PostgreSQL's
COPY text. The last line says the file is whole; the inventory reads it
without reading the rows, from the end of the file.

## Restore order

Tables are made and their rows loaded before any view, so a materialized view
reading a table is not fed the rows a second time; then the materialized view's
own rows, when it keeps them, are inserted into it. Views are made in passes:
one that reads another view waits for it. Each object is dropped before it is
made again, which is what makes this a restore rather than a merge.

## Only into a database of its name

The statements the server writes name the database: `CREATE TABLE db.t`, and a
view's query names the tables it reads in the same way. Restoring into another
database would need every statement rewritten, and a view's query parsed. The
inventory refuses instead, and the guide says so.

## Metrics

`system.events` lists only events that have happened at least once, so a
counter missing from it is nought rather than unknown; leaving it out would
start a dashboard's rate at the first insert rather than at the first poll.
