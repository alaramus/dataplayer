# Query documents and execution

The contract for a source that intentionally accepts a complete query, the
documents in which a user develops one, the bounded results it produces and the
transaction state of mutations. Read this before changing query documents, SQL
parsing, execution, history, result snapshots, Explain or query transactions.

Decisions here: D62, D63, D64, D65, D66, D77, D78, D96.

## Implementation state

Phase 3 is complete and verified. It was built in three slices — 3A read and
intelligence, 3B DML, 3C bounded DDL — and what each of them settled is below,
because the code still divides along those lines.

Documents exist: `app/queries` owns `QueryDocument`, the library, revisioned
autosave, Trash and its sweep, and the frontend has a Queries navigation panel
and a console panel.

The read console exists. `SupportsQuery` is declared and PostgreSQL implements
it; a run is started, read, cancelled and paged through routes; the console
runs the selection, the statement under the caret or an explicit script, binds
named parameters, shows ordered statement outputs and messages, keeps and
searches history, and pages, filters, orders, downloads and charts a captured
result.

SQL intelligence exists as well: the source describes its schemas, relations
and columns progressively, the editor completes against them beside the
dialect's own words, a conservative mark appears only where this application
really knows something, the source lays its own dialect out again, and a
bounded SELECT about a node is written by the source rather than assembled in
a browser. With that, PostgreSQL's query capability is offered to users.

Explain is there too, as a capability of its own: a source that will plan a
statement without running it answers with the tree it built, the plan it
prints and the estimate for the whole statement, and the console shows those
as three views of one selection. `EXPLAIN ANALYZE` is not offered, because it
executes: it waits until its effects have the policy the statement itself has.

With that, phase 3A is complete.

Writing exists as well, and phase 3B with it. A connection carries an
execution policy its owner sets; a console opens read-only every time and is
taken out of it deliberately, by typing the name of the connection where the
policy asks for it. Auto-commit makes the whole run one transaction, and a
manual transaction is opened by the console, held by the server across
requests, shown as a commit preview and ended by Commit or Roll back — by the
person, by the idle lease, or by closing the panel, which asks first. A
statement whose reach is not written down is confirmed every time. DML only:
DDL is refused with a sentence saying so until 3C.

Structure changes exist as well, and with them phase 3C. The source holds a
closed vocabulary — schemas, tables, views and indexes created, altered and
dropped, their comments, and emptying a table — and refuses anything else in
its own words, before a run is recorded. Every structure change is asked about
each time, whatever it looks like. A destructive one is first carried out on
the source inside a transaction with a short lock timeout and then rolled
back, so what the console shows before the question is the database's own
account: which dependants a cascade would take, or that the drop would be
refused outright. A rehearsal that could not take its locks stops the run,
because nothing was learnt. Once a change is permanent — when an auto-commit
run succeeds, or when somebody commits the transaction holding it — the source
issues the nodes to re-read, the read cache for that connection is emptied,
and the console drops exactly those cached answers. A rollback issues nothing.

Known deviations:

- The vocabulary is bounded by what the dialect module can read as well as by
  what is listed. `ALTER TABLE t DROP COLUMN a, ADD COLUMN b int` and
  `ALTER SCHEMA s RENAME TO r` are inside the vocabulary in words and are
  refused all the same, because the parser reads them as an opaque command and
  a statement whose shape is not established is not run (D62). One action per
  ALTER is the working form.
- The rehearsal is what a person reads before answering, not a precondition
  the server enforces. What decides whether a change may be made is the same
  four checks a write goes through — policy, level, unlock, confirmation — and
  the console will not run a change whose rehearsal came back blocked, but a
  caller that never asked for one is not refused for that reason.
- `DROP INDEX s.i` names the index, and which relation it was on is not in the
  statement, so the invalidation widens to the whole connection rather than
  naming a node the source did not say. The same is true of any statement the
  dialect module cannot take apart.
- A rename issues the schemas to re-read rather than a node replacement, so a
  panel holding the old relation reports it as gone instead of following it.
  D66 allows the wider answer; D32's replacement is not issued here.

- D65 describes a gutter Run beside each statement. The console has the two
  keyboard commands and their two buttons; the gutter marker is not drawn.
- Completion offers the source's schemas, relations, columns and the
  document's parameters beside the dialect's keywords. Aliases and CTEs are
  not offered as words of their own, and nothing is marked about them either:
  both would need a parse the browser deliberately does not do.
- Statement boundaries are asked of the source rather than parsed in the
  browser as well. D62 allows a compatible browser parser for immediate
  feedback; one parser is used here, so Run waits for a short round trip after
  the text changes rather than answering from a local parse.
- D66 offers three ways out of closing a panel with an open transaction. The
  panel offers two: roll back and close, or keep it open. Committing is not
  one of them on purpose — a commit is decided while looking at the preview of
  what it would commit, and a tab closing is not that moment.
- The writing mode is a property of the console and is never restored: a
  reopened document is read-only again, though the unlock on the connection
  outlives it and the mode can be chosen again without typing the name a
  second time.

A second source runs SQL, and it has no server: the file source answers with an
embedded DuckDB whose relations are its own nodes and whose engine is thrown
away after every run (D77, D78). It reads, and only reads — CSV, TSV, Parquet,
JSON, JSON lines and logs — so the console opens read-only against a file connection
and the write mode is not offered at all. Explain, metadata and a generated
SELECT are there; formatting and transactions are not, and the profile says so
because it is derived from what the adapter implements.

Two things are process-local and stated as such: captured results and the runs
being carried out. Both hold what cannot cross a process — memory and a
connection. A run recorded elsewhere is still readable, because it is a row,
and a restart marks whatever was left non-terminal as interrupted. Cancelling a
run this process is not carrying out marks it `cancelling`; the process that
holds it, or the next restart, settles it.

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

Preparation is source-owned and authoritative. It identifies statement ranges,
named parameters, targets and a closed class:

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
from the workspace. Deletion moves it to a thirty-day Trash; permanent
deletion removes its body, remembered parameters and layout. While autosave
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
plaintext, bodies are not, so a search decrypts a bounded number of the user's
newest documents in memory and builds no index. The search text is neither
stored nor logged. A list of documents carries the first line of each, built
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
holds three named places — Queries, History, Trash — one of which is always the
one you are in. They were two independent toggles, and the pair had a state
that meant nothing: Trash pressed while History showed did nothing, and had to
be greyed out to say so. Successful, failed, cancelled, timed-out and interrupted runs are kept;
requests rejected before execution are not. Rows are never retained. The
default is the earlier of ninety days and one thousand runs per user, with
7/30/90-day and no-retention choices and deletion of one, selected, older or
all entries. A bounded search decrypts at most those retained runs in server
memory and builds no plaintext token index. Secret values are absent; ordinary
values are present only when the document explicitly remembers them.

Saved favourites are unnecessary: a useful query is one somebody remembered.
Legacy history and favourites are not migrated because their ownership,
ordering, context and retention are not trustworthy. Documents, history and
query results are not shareable in phase 3.

Known deviations:

- **A console nobody remembered is lost with its browser tab.** That is what
  not keeping it means, and the history still holds whatever was run from it;
  but a tab restored in a *new* browser tab comes back empty rather than with
  the text, because the text was never anywhere durable.
- **Remember has no undo of its own.** What it makes is an ordinary document,
  so the way back is Trash.

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
Pinning protects a card from replacement in the UI, not from expiry. Phase 5
may supply a shared backend without changing the API. Paging, closed typed
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

Spec: [The query editor](../decisions/2026-09-01-query-editor-design.md)

## D65. The editor and its results are one workspace panel

A query document opens as a `work` panel, with the existing workspace identity
and persistence rules. Its top bar keeps title/save state, connector, database,
schema context, transaction mode, execution policy, Run/Cancel, elapsed time and
layout controls visible. The editor and result area start in a vertical 60/40
split, resizable to either side; geometry and line wrapping persist per document.
The editor stays above the results at every panel width. Narrowing the panel
keeps both visible and preserves the adjustable split.

Run follows the IDE convention without importing an IDE shell: Ctrl+Enter runs
the non-empty selection or statement under the caret, gutter Run names one
statement, and Ctrl+Shift+Enter runs the document explicitly. Formatting has
selection, statement and document commands and is one undo operation; autosave
never formats. Focus stays in the editor after execution and terminal states are
announced without stealing it.

The result area lists statement status and duration on one side and the selected
statement's result tabs on the other, with a permanent chronological Messages
view. Errors are outputs, not pseudo-table rows or generic toasts. While a new
run is active the previous result remains readable and is labelled as previous;
success replaces only the current unpinned result. Pin keeps a card in the
console, while Open in workspace gives one `result_id` one independent work
panel. Two runs are two panels even when their SQL is equal, and existing split
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
errors, unresolved objects are warnings only with complete metadata, and limited
metadata produces a status rather than false red underlines. Browser analysis
never blocks Run.

Queries are user objects rather than catalog nodes. A Queries navigation panel
lists open, draft, named and recent documents with connector filtering and
search. Connector, catalog and grid commands open an empty document; a separate
source-generated command opens a bounded SELECT or inserts a qualified name or
column list. The browser does not build SQL identifiers. Explain is a separate
result type with synchronised operation tree, table and raw plan; Explain
Analyze is deferred.

Spec: [The query editor](../decisions/2026-09-01-query-editor-design.md)

## D66. Writes require an explicit mode and the UI owns the transaction

Every document opens read-only. A connector adds an owner-controlled execution
policy above grants: `read_only`, `confirm_writes` or `allow_writes`, defaulting
to confirmation. A shared user cannot weaken it. `read` admits the editor and
read mode, `write` admits DML, and `structure` admits the bounded DDL set; owning
a connector is not an unconditional SQL bypass.

The modes are read-only, auto-commit and manual transaction. Switching out of
read-only is deliberate and never restored after reload or copied to another
document. Under confirm policy the user types the connector name and the unlock
expires after fifteen idle minutes; allow policy still asks once with the full
context. High-risk DML and every DDL statement ask each time. High risk includes
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

## Verification boundary

The feature is ready only after the security matrix is exercised against real
PostgreSQL: statement delimiters inside every quoting form, writable CTEs,
write-capable functions in read-only mode, forbidden session/transaction/COPY,
parameter injection, mixed permission scripts, revocation between prepare and
execute, cross-user ids, idempotency conflicts, cancel/timeout pool cleanup,
redaction and encryption at rest.

End-to-end coverage follows documents through reload and conflict, parameterised
read scripts, multiple outputs and errors, cancellation, promoted results,
history recovery, shared read access, auto/manual DML rollback and commit,
destructive DDL invalidation and a revoked connector. Phase 3 stays open until
3A, 3B and 3C and every required project check are clean.
