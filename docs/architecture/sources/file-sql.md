# SQL over files

What complete SQL may name in a file source and the engine that runs it. The
console, runs, results and transactions every source shares are in
[querying.md](../querying.md); the tree of files itself is in
[explorer.md](explorer.md). Read this before changing what a file source's SQL
accepts, the DuckDB sandbox, or which file formats become relations.

Decisions here: D77, D78, D96.

## D77. A file source's SQL names its own nodes, and nothing else

The file source accepts complete SQL under the same rule as any other: D62
governs it, and the exception it describes is deliberate and bounded. What the
statement may name is what is bounded here.

A relation is a node id — `"sales.csv"`, `"reports/2026/q1.parquet"` — and not
a path, and not a name invented for SQL. Every name goes through the file
session's one containment rule, the same call the listing, the download, the
archive walk and the upload go through, so a `..` segment, an absolute path, a
drive reference or a symbolic link out of the root is refused once rather than
per operation. A name the text does not define as a CTE and the source cannot
resolve is refused before anything is opened, because with no relation
registered under that name the engine would read the name as a file path of its
own. A qualified name is refused: this source has no schemas and its search
path is empty.

A table function is refused — all of them, not a list of the dangerous ones —
because a table function is how a path is written in this dialect, and
admitting one would mean a client-supplied path judged by the engine's
containment instead of the source's. The check is structural: the statement is
serialized to the engine's own parse tree, and a table-function reference
anywhere in it refuses the statement. A text the engine will not serialize is
`unknown` and is not run.

The vocabulary is read only. Statement modes are `read` and nothing else, and
each other class is refused with its family named: writing to somebody's file
through SQL is a different promise from reading it and the grid already owns
changing a delimited file's rows and columns (D51); `COPY … TO` writes a file
and export is a capability with its own ceilings (D45); a transaction or a
session command would be about an engine that is thrown away after every run;
and Explain is a command of its own with its own result type (D65). The class
comes from the engine's parser rather than from a first word.

Parameters are the engine's own spelling, `$name`. DuckDB has no `:name` at
all, so `parameter_syntax` carries a second value rather than the source
pretending to a spelling it would have to rewrite. The browser reads the
spelling from the profile.

Known deviations:

- A worksheet is not offered to SQL. Reading `.xlsx` needs an extension the
  sandbox will not download, and handing the openpyxl reader's rows to the
  engine materialises the whole sheet, which needs a ceiling that refuses
  rather than truncates — a decision worth making when somebody asks for it.
  A worksheet node is refused by name, with that reason.
- The same delimited file is typed twice over: every column is text in the
  grid, because D51 makes it editable, and the engine sniffs types because
  arithmetic needs them. Two readers for two purposes rather than one answer
  computed in two places.
- `range(10)`, `unnest` and every other table function that names nothing on
  disk are refused with the rest. Separating them would mean a list of names,
  which is the blacklist this rule exists to avoid.

Spec: [SQL over tabular files](../../decisions/2026-09-02-file-sql-design.md)

## D78. The engine is a disposable sandbox, not a database the source keeps

D77's refusals are the rule. This is what stands behind them, so that a hole in
a parse is not the last thing between a person and the disk.

Every run gets its own in-memory database and closes it at the end; nothing
persists between runs, and there is no file for one run to leave behind for the
next. The relations the statement names are registered first, because
registering them reads the files, and only then is the configuration closed:
the connector root is the one allowed directory, external access is off,
network filesystems are disabled, extensions are neither installed nor loaded,
and the configuration is locked. External access being off is what turns the
allowed directory from a list into a restriction — on its own it restricts
nothing — and the lock is what stops the user's own SQL reopening any of it,
which `SET` being a refused class already stops once. Memory and threads are
bounded and there is no temp directory, so a runaway aggregation fails instead
of filling the server's disk.

The engine is synchronous, so every call to it is on a worker thread: a
blocking call inside a handler stalls the loop for everyone. That is also why
cancellation cannot be a cancelled task — the thread would go on reading — and
is an interrupt on the connection instead, called from the loop. A timeout is
the same interrupt from a watchdog, and which of the two happened is a fact the
server holds rather than something read out of a message.

Driver text never reaches the caller, for the same reason it never does from
PostgreSQL and a different secret: what an engine error names is the layout of
the server, and this source's whole promise is that a person sees node ids. A
diagnostic carries the exception's class as its code, a category, and one
bounded line with the root redacted out of it.

Spec: [SQL over tabular files](../../decisions/2026-09-02-file-sql-design.md)

## D96. SQL over a log reuses its table projection

A `.log` follows the JSON workflow: source viewer, View as table, Open as query.
Its opaque file node id names the SQL relation. The grid's log detector and
parser supply the fields, continuation rows and unknown-format numbered lines;
JSON-object logs reuse the record projection and its 4 MiB source ceiling.
SQL columns contain canonical text as VARCHAR, preserving identifiers and
nested JSON; numeric and date calculations require explicit casts.

Logs are bounded byte snapshots, projected once into Arrow and registered in
the existing DuckDB sandbox. A script reuses that snapshot, and joins with
other supported files need no extra connection. Input ceilings across all logs
in a run or Explain are 32 MiB source, 100,000 rows, 500,000 cells and 4 MiB per
cell. Exceeding one refuses the input before SQL runs; it never computes over
a truncated prefix or the visible grid page. Preparation checks cancellation
and a deadline and always closes its engine, including on failure. Result
bounds, read-only execution and path containment remain D64, D77 and D78's.

Spec: [SQL over log files](../../decisions/2026-09-04-log-sql-design.md)
