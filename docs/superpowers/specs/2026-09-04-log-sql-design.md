# SQL over log files

A log follows the existing JSON workflow: open its source, choose View as table,
then open that table in the SQL editor. Its filename is the relation name, such
as `SELECT level, count(*) FROM "server.log" GROUP BY level`. No conversion or
additional connection is required. SQL remains read-only.

The legacy file explorer also parsed logs before querying them, but rewrote
the first FROM with a regular expression and loaded an unbounded DataFrame.
Reuse the workflow, not either implementation choice. D77's parsed relation
names, containment and sandbox remain authoritative.

## One projection

SQL reuses the grid's log detector and row parser. PostgreSQL, bracketed,
container, syslog and plain timestamp/level lines retain their named fields.
Continuation lines retain their message and null fields; unknown formats retain
line_no and line. JSON-object logs use the same record projection, column order,
null handling and malformed-record refusal as the grid. JSON log projection
keeps the existing 4 MiB source ceiling.

All SQL log columns are VARCHAR containing the canonical, lossless cell text.
This preserves timestamps, large numeric identifiers and nested JSON without a
second inference rule. Arithmetic and date operations use explicit CAST; JSON
functions can read nested JSON text. Metadata describes these actual SQL types.

## Whole input and bounds

The server reads a bounded byte snapshot, projects it once and registers an
Arrow table with DuckDB. Every statement of a script sees that same log input;
joins with other supported files use the existing sandbox. The input is the
whole file, not the page currently visible in the grid.

Across all logs referenced by one run or Explain, the ceilings are 32 MiB of
source bytes, 100,000 projected rows and 500,000 cells; one cell is at most
4 MiB. Exceeding a ceiling refuses the input before executing SQL, never
silently truncates it. JSON projection checks the cell count before building
its row matrix. Byte reads are bounded even if a file grows while being read.
No snapshot is written to disk, and D64's separate result bounds still apply.

Preparation runs on a worker thread, checks cancellation and timeout between
reads and row batches, and closes its engine on success, refusal or interruption.
The preparation deadline is the smaller of the statement and script timeouts;
standalone metadata/Explain use the file query's default timeout.

Tests cover parser parity, continuation/unknown/JSON logs, aggregates beyond
the first page, joins, repeated script reads, metadata, Explain, limits,
cancellation and cleanup, and the viewer-to-grid-to-console workflow. Validation
remains deferred at the user's request.
