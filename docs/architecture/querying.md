# Query documents and execution

The contract for a source that intentionally accepts a complete query, the
documents in which a user develops one, the bounded results it produces and the
transaction state of mutations. Read this before changing query documents, SQL
parsing, execution, history, result snapshots, Explain or query transactions.

Decisions here: D62, D63, D64, D65, D66.

## Implementation state

The phase is split into 3A read and intelligence, 3B DML and 3C bounded DDL;
PostgreSQL does not publish the capability until the complete 3A vertical slice
is verified.

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

What remains of phase 3 is 3C, the bounded DDL vocabulary.

Known deviations:

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

The first adapter is PostgreSQL. DuckDB or SQLite proves portability in phase 6,
after a file capability can state which paths SQL may see. The frontend never
branches on the adapter type.

Spec: [The query editor](../superpowers/specs/2026-09-01-query-editor-design.md)

## D63. A document changes; an execution does not

A `QueryDocument` is a server-owned per-user object with an immutable id. It is
bound to one connector and carries an ordered schema context, an optional title,
encrypted body, revision, editor layout and lifecycle timestamps. Any number of
documents may belong to one connector and titles need not be unique.

A new console is an unnamed document from the first edit. Debounced autosave
sends the base revision; a mismatch stops saving and offers keep mine, use
remote or save mine as a copy. Closing a tab only removes it from the workspace.
Deletion moves it to a thirty-day Trash; permanent deletion removes its body,
remembered parameters and layout. While autosave cannot reach the server, one
unsynchronised shadow may live in that browser tab's `sessionStorage`, is marked
visibly and is removed after a successful save. No durable plaintext browser
cache is introduced.

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
text. Successful, failed, cancelled, timed-out and interrupted runs are kept;
requests rejected before execution are not. Rows are never retained. The
default is the earlier of ninety days and one thousand runs per user, with
7/30/90-day and no-retention choices and deletion of one, selected, older or
all entries. A bounded search decrypts at most those retained runs in server
memory and builds no plaintext token index. Secret values are absent; ordinary
values are present only when the document explicitly remembers them.

Saved favourites are unnecessary: a useful query is a named document. Legacy
history and favourites are not migrated because their ownership, ordering,
context and retention are not trustworthy. Documents, history and query
results are not shareable in phase 3.

Spec: [The query editor](../superpowers/specs/2026-09-01-query-editor-design.md)

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

Spec: [The query editor](../superpowers/specs/2026-09-01-query-editor-design.md)

## D65. The editor and its results are one workspace panel

A query document opens as a `work` panel, with the existing workspace identity
and persistence rules. Its top bar keeps title/save state, connector, database,
schema context, transaction mode, execution policy, Run/Cancel, elapsed time and
layout controls visible. The editor and result area start in a vertical 60/40
split, resizable to either side; geometry and line wrapping persist per document.
Below the useful width the two sides become an Editor/Results switch rather than
two unusable slivers.

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

Spec: [The query editor](../superpowers/specs/2026-09-01-query-editor-design.md)

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
views and indexes, plus comments. Permission administration, database/role/
tablespace/extension commands and maintenance operations remain actions or later
jobs. Destructive DDL is rehearsed in a rollback transaction with a short lock
timeout, and a blocked preview disables execution. After commit the adapter
returns exact node invalidations, replacements or an explicit schema/database
scope; the client never reconstructs affected ids from SQL. Rollback invalidates
nothing.

Spec: [The query editor](../superpowers/specs/2026-09-01-query-editor-design.md)

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
