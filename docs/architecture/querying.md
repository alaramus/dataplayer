# Query documents and execution

The contract for a source that intentionally accepts a complete query, the
documents in which a user develops one, the bounded results it produces and the
transaction state of mutations. Read this before changing query documents, SQL
parsing, execution, history, result snapshots, Explain or query transactions.

Decisions here: D62, D63, D64, D65, D66, D77, D78, D96, D160, D206.

## What exists today

`app/queries` owns `QueryDocument`, the library, revisioned autosave and run
history; the frontend has a Queries navigation panel and a console panel.

`SupportsQuery` is declared and PostgreSQL implements it. A run is started,
read, cancelled and paged through routes; the console runs the selection, the
statement under the caret or an explicit script, binds named parameters, shows
ordered statement outputs and messages, keeps and searches history, and pages,
filters, orders, downloads and charts a captured result. The source describes
its schemas, relations and columns progressively, the editor completes against
them beside the dialect's own words, a conservative mark appears only where this
application really knows something, and a bounded SELECT about a node is written
by the source rather than assembled in a browser. Explain is a capability of its
own: a source that will plan a statement without running it answers with the
tree it built, the plan it prints and the estimate for the whole statement, and
the console shows those as three views of one selection.

A connection carries an execution policy its owner sets. The editor chooses
read mode for reads and auto-commit for writes automatically; it has no separate
write unlock. A confirm-writes policy asks at each changing run. Auto-commit makes the whole run one
transaction; a manual transaction is opened by the console, held by the server
across requests, shown as a commit preview and ended by Commit or Roll back — by
the person, by the idle lease, or by closing the panel, which asks first. A
statement whose reach is not written down is confirmed every time.

The source holds a closed vocabulary for structure changes — schemas, tables,
views and indexes created, altered and dropped, their comments, and emptying a
table — and refuses anything else in its own words, before a run is recorded.
Every structure change is asked about each time. A destructive one is first
carried out inside a transaction with a short lock timeout and then rolled back,
so what the console shows before the question is the database's own account:
which dependants a cascade would take, or that the drop would be refused
outright. A rehearsal that could not take its locks stops the run, because
nothing was learnt. Once a change is permanent the source issues the nodes to
re-read, the read cache for that connection is emptied, and the console drops
exactly those cached answers; a rollback issues nothing.

A second source runs SQL and has no server: the file source answers with an
embedded DuckDB whose relations are its own nodes and whose engine is thrown
away after every run (D77, D78). It reads, and only reads — CSV, TSV, Parquet,
JSON, JSON lines and logs — so the console opens read-only against a file
connection and the write mode is not offered at all. Explain, metadata and a
generated SELECT are there; formatting and transactions are not, and the profile
says so because it is derived from what the adapter implements.

Three things are process-local and stated as such: captured results, the runs
being carried out and open transactions (D66). They hold what cannot cross a
process — memory and a connection — and are correct only because the backend
runs as one process (D124). Under several, a result page or the next statement
of a transaction reaching another process would be answered 404, and a cancel
there would mark the run `cancelling` without reaching its task. A run from
before a restart is still readable, because it is a row, and the restart marks
whatever was left non-terminal as interrupted.

The application module sits above connectors and adapters:

```text
api → queries → connectors → adapters → users → core
```

`queries` owns documents, runs, history, result-store policy and routes.
`connectors` exposes one access-and-adapter resolver rather than making the new
module copy its private route checks. An adapter owns dialect parsing, policy,
metadata and source execution; it knows nothing about stored documents or user
history.

## D62. Complete SQL is an intentional source capability

D2c still governs every statement DataPlayer builds: a client never supplies an
identifier, predicate or fragment for the platform to interpolate into another
query. Query execution is the deliberately different operation in which the
user supplies the complete statement. It exists only for a source implementing
the method-only `SupportsQuery` protocol.

The protocol describes behaviour through methods so capability discovery can
continue to use runtime `issubclass` checks. A query profile states the dialect,
parameter syntax, statement modes, metadata and Explain support, cancellation,
and the default and maximum timeout and result bounds. The declaration is
derived from implemented operations rather than from an adapter-name branch or
a second handwritten capability list.

Preparation is source-owned and authoritative. Each dialect module reads with
its own engine — PostgreSQL with the server's own grammar, the file source
with the engine it runs — so a statement the source accepts is one the
console can read. It identifies statement ranges, named parameters, targets
and a closed class:

```text
read | explain | dml | ddl | transaction | session | copy | unknown
```

The browser may parse for immediate highlighting, completion and the statement
under the caret, but the server parses again. Splitting on semicolons, checking
the first word and blacklists are not accepted substitutes. In the read slice,
`transaction`, `session`, `copy` and `unknown` are refused before execution. A
script requires the highest access level of any statement: `read` for read and
Explain, `write` for DML and `structure` for DDL.

Named parameters are bindings, never text substitution. The editor discovers
`:name` with the dialect parser, asks for every value and sends value, SQL null,
secret and remember state separately. PostgreSQL infers a type from the
expression; an ambiguous value is resolved with a cast in SQL, not a second
type language in the form. A secret value is never retained.

Every read run begins a PostgreSQL `READ ONLY` transaction, validates and safely
sets its source-issued ordered `search_path`, and applies `statement_timeout`
locally. The transaction is the security boundary; classification supplies
policy and explanation, not proof. Explicit temporary writes, transaction and
session commands and COPY are refused as well. A database function may have an
external side effect that neither a parser nor PostgreSQL read-only mode can
discover; preventing that remains the responsibility of the database role.

The first adapter is PostgreSQL. The second is the file source, which proved
the protocol portable once it could state which of its own nodes SQL may see
(D77) — and proved it the other way as well, by implementing a fraction of it:
reads, no transactions, no formatter. The frontend never branches on the
adapter type.

Known deviations:

- **Renaming a schema and moving a relation stay catalog actions.** Both parse
  precisely and stay `unknown` on purpose rather than by a parser falling
  over: the screen that renames what it is looking at is not the query
  editor. Changing an owner and row security are refused as permission
  administration, the way a grant is, and an `ALTER TABLE` that switches a
  tablespace, a trigger or a rule is refused with that family's sentence.
- **PostgreSQL still has a second reader.** Boundaries and classes come from
  the server's grammar (pglast), while the formatter and the post-commit
  invalidation (`effects.py`) still read with sqlglot. A form only the grammar
  reads — `bit varying`, a table-level `NOT NULL` — is left unformatted and
  invalidates the whole connection rather than its nodes: a wider reload,
  never a stale one.
- **Statement boundaries are asked of the source, not parsed in the browser.**
  This decision allows a compatible browser parser for immediate feedback; one
  parser is used, so Run waits for a short round trip after the text changes
  rather than answering from a local parse.
- **Aliases and CTEs are not offered as words of their own**, and nothing is
  marked about them either: both would need a parse the browser deliberately does
  not do.

Spec: [The query editor](../decisions/2026-09-01-query-editor-design.md)

## D63. A document changes; an execution does not

A `QueryDocument` is a server-owned per-user object with an immutable id. It is
bound to one connector and carries an ordered schema context, an optional title,
encrypted body, revision, editor layout and lifecycle timestamps. Any number of
documents may belong to one connector and titles need not be unique.

**A console is not a document until somebody asks for it to be one.** It used
to become one at once — the plus wrote an "Untitled" before a word was typed,
and opening a table as a query left a document behind on every press, so the
library filled with rows nobody had decided to keep and became a log of every
console ever opened. A console now holds its text in its own browser tab, and
`Remember` is the one command that puts it into the library. Nothing else
writes one: running does not, because an `ExecutionRun` is the record of what
was executed and needs no document (`document_id` is nullable), so a console
nobody kept runs and appears in the history exactly like one they did.

Until it is remembered the text lives in that tab's `sessionStorage` under the
panel's own draft id — never in the workspace layout, which is durable and
would be the plaintext browser cache this decision forbids. It dies with the
tab, which is the point: a console closed without being kept leaves nothing
anywhere.

From `Remember` on it is an ordinary document and behaves as it always has.
Debounced autosave sends the base revision; a mismatch stops saving and offers
keep mine, use remote or save mine as a copy. Closing a tab only removes it
from the workspace. Deletion removes its body, remembered parameters and layout
immediately after confirmation. While autosave
cannot reach the server, one unsynchronised shadow may live in that browser
tab's `sessionStorage`, is marked visibly and is removed after a successful
save. No durable plaintext browser cache is introduced.

The connector id never changes silently. Losing a grant or deleting the
connector leaves the user's document readable but makes its context unavailable
and Run impossible. Running it elsewhere creates a copy. The ordered
`search_path` is initialised from the effective source context and may contain
only schemas the source has issued and revalidated at execution time.

An `ExecutionRun` is an immutable snapshot of document id and revision,
executed text and range, connector/database/schema context, parameter metadata,
transaction mode and request policy. Every statement has an ordered durable
output record and terminal status. Editing the document while a run is active
does not change its snapshot; a diagnostic highlights the live editor only when
the text still matches and otherwise opens the executed snapshot for compare or
restore.

Searching the library obeys the same rule as searching history: titles are
plaintext, bodies are not, so a search decrypts the user's newest 500
documents in memory, on a worker thread rather than the event loop, and builds
no index. The search text is neither stored nor logged — the access line drops
the query string it travels in (D184). A list of documents carries the first line of each, built
per response for the same reason — most documents are drafts nobody has named.

Documents, executed SQL and remembered non-secret parameter values are
encrypted at rest with a required, independent 32-byte `QUERY_CONTENT_KEY`.
Titles and operational metadata remain plaintext. SQL, parameter values and
result rows never enter application logs or metric labels. Changing the key
without a data migration makes stored content unreadable and is not a supported
rotation procedure.

History is a view of accepted immutable runs, not a second collection of query
text — and the screen has to say so, because a list of runs and a list of
documents are both lists of SQL and read alike. A run row names the document it
was run from when that document still has a name, which is what makes it
visibly an event of a document rather than another copy of one; the library
  holds two named places — Favorites and History. Successful, failed, cancelled,
  timed-out and interrupted runs are kept;
requests rejected before execution are not. Rows are never retained. The
default is the earlier of ninety days and one thousand runs per user, with
7/30/90-day and no-retention choices and deletion of one, selected, older or
all entries. A search decrypts the newest 500 of those retained runs — of up
to 1,000 — in server memory, on a worker thread, and builds no plaintext token
index. Secret values are absent; ordinary
values are present only when the document explicitly remembers them.

Saved favourites are unnecessary: a useful query is one somebody remembered.
Legacy history and favourites are not migrated because their ownership,
ordering, context and retention are not trustworthy. Documents, history and
query results are not shareable.

Known deviations:

- **A console nobody remembered is lost with its browser tab.** That is what
  not keeping it means, and the history still holds whatever was run from it;
  but a tab restored in a *new* browser tab comes back empty rather than with
  the text, because the text was never anywhere durable.
- **Remember has no undo of its own.** What it makes is an ordinary document;
  removing it requires confirmation and deletes it permanently.

Spec: [The query editor](../decisions/2026-09-01-query-editor-design.md)

## D64. A run is asynchronous; its result is a bounded snapshot

Starting a run is an idempotent command. The client chooses its execution UUID;
repeating the same id and payload returns the existing run, while reusing the id
with another payload is a conflict. The HTTP request validates and records the
run, then returns. A process task executes it, the existing realtime transport
announces state, and an authenticated status route remains the authority and the
polling fallback. Cancellation is a separate idempotent HTTP command.

The lifecycle is explicit:

```text
accepted → running → cancelling → cancelled
                   ↘ succeeded | failed | timed_out | interrupted
```

PostgreSQL cancellation is not optimistic. `cancelling` remains until the query
connection reports its terminal outcome; a query that won the race may honestly
finish `succeeded`. Closing a panel, reloading or losing the socket does not
cancel a server-owned run. On application startup, durable non-terminal rows are
marked `interrupted`; SQL is never replayed automatically.

One document has at most one active run. The default admission limit is three
active runs per user, additionally bounded by adapter and pool policy. Excess is
refused immediately rather than placed in an invisible queue. PostgreSQL uses a
thirty-second default statement timeout, configurable up to five minutes, and a
ten-minute whole-script ceiling. A run may show preparation, pool acquisition,
statement ordinal, elapsed time, materialisation rows/bytes and cancellation,
but never invents a percentage.

Statements in a script execute sequentially in one transaction and one
snapshot. The first failure stops the script; earlier outputs remain visible and
later statements are `not_run`. Run selection/current accepts exactly one
statement, while a separate script command accepts several. A run may contain
at most one hundred statements; a document is at most 1 MiB UTF-8 and an
executed statement or selection at most 256 KiB.

A tabular output is materialised once, never re-executed for paging. It receives
an owned opaque `result_id`, then the source connection and transaction are
released. The bounds are:

| Boundary | Maximum |
| --- | ---: |
| Browser page | 500 rows; 100 by default |
| One result | 10,000 rows or 32 MiB canonical cells |
| One cell | 4 MiB |
| One run | 20 result sets or 64 MiB |
| Messages in one run | 1,000 or 1 MiB |

One extra row establishes truncation. A cell is never shortened; a cell beyond
the ceiling produces `result_too_large`. Hitting storage after SQL succeeded is
a result-publication failure, not a claim that the statement failed. Query
results have stable positional column ids distinct from duplicate or empty
display names.

Snapshots live in a process-local TTL/LRU store for thirty minutes after last
access. Active results are not evicted; terminal least-recently-used results are.
Pinning protects a card from replacement in the UI, not from expiry. A shared
backend could be supplied later without changing the API. Paging, closed typed
filtering and deterministic platform sorting operate over captured rows only:
numeric by arbitrary precision, date/time chronologically, booleans false then
true, text by Unicode code point, null last ascending and original ordinal as
tiebreaker. The interface names this snapshot scope.

Downloads offer current page and all captured rows with snapshot filters, sort
and column layout. A future execute-to-file is a new streaming run, not a larger
snapshot. Charts reuse D35 over the current snapshot page only. Result rows do
not survive reload; durable run metadata offers Run again.

Diagnostics are an adapter-owned safe model: SQLSTATE, category, normalised
primary message, statement and character range, and an optional vetted hint.
Raw exceptions, DETAIL, CONTEXT, server paths, connection strings and bound
values do not cross. Notices are length-bounded and stripped of control
characters. Operational telemetry names ids, status, timings, rows and bytes,
not query content.

Known deviation:

- **The console does not listen to `queries.runs`.** It polls a live run every
  second, in a hidden page as well, so a finished run reaches it whatever
  became of the socket; the announcement has no reader yet.

Spec: [The query editor](../decisions/2026-09-01-query-editor-design.md)

## D65. The editor and its results are one workspace panel

A query document opens as a `work` panel, with the existing workspace identity
and persistence rules. Its top bar keeps title/save state, connector, database,
schema context, manual transaction choice, Run/Cancel, elapsed time and
layout controls visible. The editor and result area start in a vertical 60/40
split, resizable to either side; geometry and line wrapping persist per document.
The editor stays above the results at every panel width. Narrowing the panel
keeps both visible and preserves the adjustable split.

Run follows the IDE convention without importing an IDE shell: Ctrl+Enter runs
the non-empty selection or statement under the caret, gutter Run names one
statement, and Ctrl+Shift+Enter runs the document explicitly. A selection inside
a single statement runs that whole statement — undo leaves the restored text
selected, and the literal fragment would only be refused as unknown — while a
selection spanning several statements runs literally as a script. Formatting has
selection, statement and document commands and is one undo operation; autosave
never formats. Focus stays in the editor after execution and terminal states are
announced without stealing it.

The result area lists statement status and duration on one side and the selected
statement's result tabs on the other, with a permanent chronological Messages
view. Errors are outputs, not pseudo-table rows or generic toasts. While a new
run is active the previous result remains readable and is labelled as previous;
success replaces only the current unpinned result. Pin keeps a card in the
console, while Open in workspace gives one `result_id` one independent work
panel; both stand in the result grid's *This tab* group rather than a bar of
their own above it. Two runs are two panels even when their SQL is equal, and existing split
and drag behaviour supplies side-by-side comparison; a data-diff language does
not.

The existing relation `DataGrid` is not embedded. A behaviour-preserving first
slice extracts a controlled `TabularGrid`: typed columns and page, layout,
selection, clipboard, renderers, full-value viewer and load/error states.
Relation and query controllers supply different behaviour. Query results have
no update, insert, delete, reference, structure or import commands. Layout is
reconciled by document, statement/result ordinal and a signature of positional
ids, display names and types.

SQL intelligence is progressive. The current search path's relations arrive
first, columns when a relation appears or completion asks, and another schema
when qualified. A five-minute cache, manual refresh, DDL invalidation and
missing-object errors control freshness. Completion covers dialect vocabulary,
functions, schemas, relations, columns, aliases, CTEs and parameters; minimal
qualification is used unless ambiguity requires more. Syntax errors are local
errors, unresolved objects are warnings only with complete metadata, limited
metadata produces a status rather than false red underlines, and a change the
connection would run as a change is not marked as unrunnable. Browser analysis
never blocks Run.

Queries are user objects rather than catalog nodes. A Queries navigation panel
lists open, draft, named and recent documents with connector filtering and
search. Connector, catalog and grid commands open an empty document; a separate
source-generated command opens a bounded SELECT or inserts a qualified name or
column list. The browser does not build SQL identifiers. Explain is a separate
result type with synchronised operation tree, table and raw plan; Explain
Analyze is deferred.

Known deviations:

- **The gutter Run is not drawn.** The console has the two keyboard commands and
  their two buttons.
- **The manual transaction choice is never restored.** A reopened document
  runs reads in read mode and changes in auto-commit unless chosen again.

Spec: [The query editor](../decisions/2026-09-01-query-editor-design.md)

## D66. The UI owns the transaction and the source bounds SQL changes

Every document follows its connection's owner-controlled execution
policy above grants: `read_only`, `confirm_writes` or `allow_writes`, defaulting
to confirmation. A shared user cannot weaken it. `read` admits the editor and
read mode, `write` admits DML, and `structure` admits the bounded DDL set; owning
a connector is not an unconditional SQL bypass.

The modes are read-only, auto-commit and manual transaction. The editor picks
read-only for reads and auto-commit for changes; a person may explicitly choose
a manual transaction. Under confirm policy, each changing run asks for consent.
High-risk statements and every DDL statement ask each time. High risk includes
UPDATE/DELETE without a top-level predicate, unrestricted MERGE, truncation,
drop, destructive alter, permission change and a mutating script.

Auto-commit makes the complete run one transaction and commits only after every
statement succeeds. Manual mode leases a physical connection lazily, keeps the
transaction and its state visible, and ends only by explicit Commit/Rollback or
server cleanup. Five minutes without a database command rolls it back, with a
visible final-minute countdown. Closing the panel with an open transaction is
blocked on Commit, Rollback or keeping it open; lost heartbeat receives only a
short grace before rollback.

PostgreSQL makes a transaction unusable after a statement error. Error, timeout
or cancellation therefore rolls back the whole manual transaction immediately
and names the earlier successful mutations that were undone. A Commit preview
lists context, transaction age, mutating statements, targets, affected rows,
DDL and unknown effect counts. Commit itself is a durable event. Query text may
not issue transaction, savepoint, session or prepared-statement controls; the UI
owns the state it displays.

DML is the first write slice and returns command tag, affected rows, bounded
RETURNING output, messages, duration and pending/committed/rolled-back state.
Query results remain read-only because an arbitrary projection has no safe row
identity; relation editing continues to use D25's handles.

DDL follows with a PostgreSQL allowlist for create/alter/drop of schemas, tables,
views and indexes, plus comments and truncation — a truncation is a table
operation with a stronger lock, and refusing it while admitting `DELETE FROM t`
would be an arbitrary line. Permission administration, database/role/
tablespace/extension commands and maintenance operations remain actions or later
jobs. The list is an allowlist because the alternative cannot be written down:
what falls outside it is refused with a sentence naming the family, and a form
the dialect module cannot read is refused as unknown rather than admitted by
omission. Destructive DDL is rehearsed in a rollback transaction with a short
lock timeout, inside the open transaction when there is one so that a person's
own locks are not read as somebody else blocking them; a blocked preview
disables execution. After commit the adapter returns exact node invalidations,
replacements or an explicit schema/database scope; the client never
reconstructs affected ids from SQL. Rollback invalidates nothing.

Known deviations:

- **The rehearsal is what a person reads before answering, not a precondition the
  server enforces.** What decides whether a change may be made is the same four
  checks a write goes through — policy, level and confirmation — and the
  console will not run a change whose rehearsal came back blocked, but a caller
  that never asked for one is not refused for that reason.
- **`DROP INDEX s.i` widens the invalidation to the whole connection.** The
  statement names the index and not the relation it was on, so nothing can name a
  node the source did not say. The same is true of any statement the dialect
  module cannot take apart.
- **A rename issues the schemas to re-read rather than a node replacement**, so a
  panel holding the old relation reports it as gone instead of following it. This
  decision allows the wider answer; D32's replacement is not issued here.
- **Closing a panel with an open transaction offers two ways out**, roll back and
  close, or keep it open. Committing is not one of them on purpose: a commit is
  decided while looking at the preview of what it would commit, and a tab closing
  is not that moment.

Spec: [The query editor](../decisions/2026-09-01-query-editor-design.md)

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

Spec: [SQL over tabular files](../decisions/2026-09-02-file-sql-design.md)

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

Spec: [SQL over tabular files](../decisions/2026-09-02-file-sql-design.md)

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

Spec: [SQL over log files](../decisions/2026-09-04-log-sql-design.md)

## D160. Connection rights govern SQL; saved queries have no Trash

The connector's execution policy and the caller's grant are the only persistent
permissions for user-authored SQL. A read runs in read mode; a change runs in
auto-commit unless the user selected a manual transaction. There is no editor
write unlock or unlock expiry. The server checks the current policy and grant
for every changing run and when opening a manual transaction. Under
`confirm_writes`, each changing run must carry a fresh confirmation; high-risk
statements still require their specific confirmation. A source that only
supports reads continues to reject writes independently of connector access.

Deleting a remembered SQL document requires confirmation and deletes its body,
layout and remembered parameters in that request. Favorites and History remain
separate views; History retains its own deletion and retention controls, and
deleting one run asks first, as every delete does. The
migration deletes documents already in Trash, removes the Trash column and
write-unlock table, and keeps run history through its nullable document link.
The editor keeps Remember in its toolbar as a disabled command after the query
is in the library; deletion is available in the library row. The editor has no
reload command: its live text is deliberately not replaced by a server refetch,
while the library can still re-read its list.

Spec: [SQL editor permissions and immediate deletion](../decisions/2026-09-24-sql-editor-simplification.md)

## D206. Maintenance commands run alone, outside a transaction

ANALYZE, VACUUM, REINDEX, CLUSTER, CHECKPOINT and REFRESH MATERIALIZED VIEW are
the class `maintenance`, read from the leading keyword. It is a change: write
access, the owner's confirmation policy, never a read run. It runs with no
transaction, because VACUUM, CLUSTER and the CONCURRENTLY forms refuse one: the
source puts the borrowed connection in autocommit, sets the timeout and schema
context for the session, and resets both before the pool gets it back —
closing it when it cannot. With nothing to roll back, a maintenance command is
the only statement of its run, is refused in a manual transaction and is not
rehearsed. VACUUM FULL, CLUSTER and a non-concurrent REINDEX or REFRESH are
high risk (D66), since they hold the table from its readers. Which classes
change a source is one server set, sent with each prepared statement as
`changes` so the editor does not keep its own.

Spec: [Maintenance commands in the SQL editor](../decisions/2026-10-04-maintenance-statements.md)
