# The query editor

Date: 2026-09-01. Settles roadmap phase 3 and D62, D63, D64, D65, D66.

Sources read:

- `myquasar/src/myapp/components/SqlEditor/`;
- query and history paths in `myquasar/src/myapp/serverAPI.ts` and the table
  repository;
- `dbwebtool/webdb/webapi/view_services/execute_data_handler.py`;
- the legacy PostgreSQL, SQLite, MySQL and MSSQL execution methods;
- the current adapter protocols, PostgreSQL session, fetch boundary, workspace,
  CodeMirror wrapper and grid in this repository.

External interaction evidence:

- [JetBrains query consoles](https://www.jetbrains.com/help/pycharm/query-consoles.html)
  and [query execution](https://www.jetbrains.com/help/idea/query-execution.html);
- [DBeaver SQL execution](https://dbeaver.com/docs/dbeaver/SQL-Execution/);
- [Microsoft SQL extension for VS Code](https://learn.microsoft.com/en-us/sql/tools/visual-studio-code-extensions/mssql/mssql-extension-visual-studio-code?view=sql-server-ver17).

Those products are evidence about mature gestures, not a visual specification.
DataPlayer keeps its own workspace, source capabilities, access funnel and typed
grid boundary.

## The goal

Developing a non-trivial query should feel like work in a database IDE: open a
console in a known source context, edit without fear of losing the draft, run
the selection or statement under the caret, inspect several outputs, cancel a
mistake, compare results and return later. The first useful job is interactive
data exploration and development of complex read SQL. Administrative scripts
and migrations are later, explicit modes with a different price of error.

The editor is desktop-first and keyboard-first. It remains operable with a
pointer and degrades to an Editor/Results switch when the workspace is too
narrow for a split, but it does not pretend that completion, diagnostics and
several result sets are a mobile-first interaction.

Phase 3 is not closed by a SELECT text box. It includes the complete read
console, metadata intelligence and Explain, then DML transactions and a bounded
PostgreSQL DDL vocabulary. PostgreSQL is the one implementation. The next local
relational adapter proves portability in phase 6 rather than holding this phase
open for a file-path contract that does not yet exist.

## What the old application proves

The useful idea is capability-driven entry: a backend profile told one editor
whether it was speaking SQL, CQL, Mongo, Redis, a shell, a REST endpoint or SQL
over files. A result became a normal application document and could be searched,
downloaded, shared and reopened as a query. History was connector-scoped and a
favourite could be recovered into the editor.

Everything about identity and execution around that idea was unsafe:

- the editor was a 1000 by 600 popup and always ran its whole text;
- Run reread the global current table instead of the context in which the
  editor opened, so switching another tab could change the target;
- executions reused a result id, so an older response could overwrite a newer
  one;
- an HTTP error could produce no socket terminal event and leave loading
  forever;
- read/write classification used one permissive parse attempt, and a parse
  error became write rather than a refusal;
- the permission check rejected safe reads for a read-only user before it knew
  what the statement was;
- history was written before connector and permission validation, had no
  retention or stable ordering, and one user could address another user's row
  for deletion;
- raw exceptions and the query itself were returned as a pseudo-table;
- completion was a static demonstration list rather than source metadata;
- there was no cancellation, timeout state, transaction model, parameters,
  affected row count, Explain or per-statement output;
- different adapters silently disagreed about multiple statements and commit.

Porting that component would preserve the defects that justify the rewrite. The
new design keeps the capability and result-as-work ideas and gives every other
concept an explicit identity and lifecycle.

## Four identities, not one document-shaped dictionary

The model is:

```text
QueryDocument
  └─ ExecutionRun (immutable snapshot of one press of Run)
       └─ StatementRun[] (ordered outcome of parsed statements)
            └─ ResultSet[] (bounded tabular, command, diagnostic or plan output)
```

An `ExecutionSession` is orthogonal. In read-only and auto-commit modes it is a
logical context and the physical pool connection lives for the run. Manual
mode leases one connection while the transaction is open. This separation is
what prevents a document left open overnight from consuming a connection and
what lets a run keep the exact text the user has already edited away.

### The document

A console is one object in two stages, not scratch and saved-query types. It is
created as an unnamed server-owned draft and naming it changes only its title.
It is owned by a user and bound to one connector; running it elsewhere makes a
copy. Its context includes the connector's database and an ordered source-issued
`search_path`, constantly visible in the toolbar and captured with every run.

The body is revisioned and debounced-autosaved. Closing a workspace tab merely
closes the view. Delete means Trash for thirty days, with explicit permanent
deletion. A revision conflict never silently picks the last writer: keep mine,
use remote and save mine as copy are the three choices. When the backend is
unreachable, a visibly unsynchronised `sessionStorage` shadow lets the same tab
survive reload; it is removed on save and never becomes a long-lived plaintext
browser library.

Queries are navigation of their own, not nodes invented in a source catalog.
The Queries panel presents open, draft, named and recent documents and filters
by connector. Names need not be unique. Connector, catalog and grid affordances
open an empty document; generated SELECT and insertion of a qualified name or
column list are separate source-owned commands, so the browser never assembles
identifiers.

### The run

Every Run has a client-generated UUID. Retrying the same request is safe and
returns the same run; changing its payload is a conflict. The run snapshots the
document revision, exact executed range, context, parameters, mode and policy.
One document admits one active run, while another document is the explicit way
to run concurrently. A user admits three active runs by default, additionally
bounded by the source and pool; excess is refused, not queued invisibly.

The user can edit while the snapshot runs. A later error points into the live
document only if the executed text still matches; otherwise it points into the
snapshot and offers compare or restore. This is a direct correction of legacy's
global context and reused result identity.

## What Run means

Ctrl+Enter runs a non-empty selection, otherwise the statement under the caret.
A gutter command names one statement. Ctrl+Shift+Enter is the deliberately
different command that runs the whole document. A selection containing several
statements needs Run selection as script. Ordinary Run never falls back to the
whole file.

Statement boundaries belong to the adapter's dialect parser. The browser runs a
compatible fast parser for highlighting and completion, but the server confirms
the range, parameter list and mode. Quoted semicolons, comments, dollar strings,
CTEs and dialect extensions therefore do not pass through home-grown splitting.
The closed classification is read, Explain, DML, DDL, transaction, session,
COPY or unknown. Unknown is a refusal, not a write-shaped guess.

A script is sequential in one transaction and snapshot. On the first error the
rest is not run; completed outputs stay visible and explicitly become rolled
back where the mode requires it. One script admits one hundred statements, one
statement or selection 256 KiB and a document 1 MiB. These are input bounds,
separate from time and result bounds.

Named `:parameters` enter the extended query path as bindings. The value form
distinguishes SQL null, secret and remembered. PostgreSQL infers the type from
the expression, and the SQL author adds a cast where the expression is
ambiguous. The platform does not add a type mini-language or interpolate a
value into text.

## Read-only is a database state

Parser classification chooses policy, messaging and the access level, but it is
not the defence. A read execution runs inside a PostgreSQL read-only transaction
with a local statement timeout and a safely composed validated search path.
DataPlayer additionally refuses explicit transaction, session, temporary write
and COPY forms whose state it could not represent honestly.

The guarantee is precise: no persistent database change admitted by PostgreSQL
read-only mode. A function may send email, call an extension or mutate something
outside the database; neither a generic parser nor the database's transaction
flag can prove otherwise. Restricting callable functions is the database role's
job. The UI and documentation say this rather than claiming that the word
SELECT means harmless.

Thirty seconds is the default per statement, the user may choose up to five
minutes, and a script has a ten-minute ceiling. The source applies the timeout;
an upstream HTTP deadline alone would leave work running. Closing or reloading
the panel does not cancel a server-owned execution. Explicit Cancel moves to
`cancelling` and waits for the source's terminal answer; PostgreSQL cancellation
can lose a race to completion, so the honest result may still be success.

HTTP starts, reads and cancels a run. The application socket announces changes
through a topic, while the read route remains the authority and polling fallback.
A missing socket event can no longer leave the UI without a terminal path. At
startup, accepted/running/cancelling rows left by a stopped process become
interrupted and are never replayed.

## A result is captured once

Keeping a cursor would hold a transaction and pool connection while the user
reads. Re-executing for page two would show another snapshot and could repeat a
side effect. Uploading browser rows would trust untrusted data. The chosen answer
is one bounded server-owned materialisation followed by an opaque result id.

The result reads at most 10,000 rows and one extra, 32 MiB per result, 4 MiB per
cell, twenty result sets and 64 MiB per run. The browser asks for 100 rows by
default and no more than 500. A cell is never truncated; an oversize one is a
typed publication refusal. One extra row states that the source result was
larger. Result store exhaustion is distinct from statement failure.

The process-local result store is bounded by bytes, LRU and a thirty-minute idle
TTL. It evicts terminal results before refusing new materialisation and never
evicts an active one. Pin is a UI promise against replacement, not infinite
server retention. This is an explicit single-process boundary; phase 5 may
install a shared store under the same API.

Paging, filters and sorting act on the captured set and say so. Sorting is a
portable platform order, not the database collation: arbitrary precision for
numbers, chronological dates and times, false then true, Unicode code points for
text, null at the far end and original ordinal as the stable tiebreaker. Current
page and all captured rows are downloadable without rerunning SQL. The chart is
the existing D35 bounded current-page chart. A whole-result aggregate and a
large execute-to-file stream are separate later operations.

Duplicate and empty headings are ordinary SQL results. Each column therefore
has a stable positional id and a separate display name. Cells keep the D23
canonical boundary, source type description and lossless null distinction.

## The editor belongs to this workspace

The panel is editor over results, initially 60/40. Each side can fill the panel
and the split is remembered per document. The permanent toolbar shows document
and save state, connector/database/schema, execution policy, transaction mode,
Run or Cancel, elapsed time and layout controls. Narrow space becomes an
Editor/Results switch without destroying either side.

During a new run the previous answer stays readable and is labelled previous.
A successful answer replaces only an unpinned card; a failure opens its own
statement output and does not disguise the previous data as current. The
statement list carries status and duration, the selected statement carries its
result tabs, and Messages is a permanent chronological view. No SQL error is a
toast or a two-row fake result.

Pin keeps a card inside the console. Open in workspace makes a result-id panel
that may be dragged beside another with the layout engine already in use. One id
opens once; different runs remain different even when their text matches. A
data diff is deliberately absent because it needs keys, duplicates and its own
bounds.

The shared surface is an extraction, not a flag-filled universal component.
`TabularGrid` takes controlled columns, page, layout, selection and commands.
The existing relation controller continues to own fetch, row handles, edits,
references and structure. The query controller owns snapshot paging, filtering,
sorting, download and chart; it never offers mutations. Result layout follows a
signature of document, statement/result ordinal and positional column id/name/
type, so a compatible rerun feels stable and a changed result reconciles.

Focus remains in the editor after Run. A command moves it to results, terminal
state is announced, and all statement/result/split controls are keyboard
reachable. Line numbers and matching brackets are on, wrapping and the minimap
off, and two-space indentation is the small fixed first preference set. Format
statement, selection and document are explicit one-undo commands; autosave never
formats.

## Intelligence is progressive and conservative

The editor first loads relations in the current search path, loads columns when
a relation is mentioned or completion asks, and follows an explicit qualifier
to another schema. Source functions and dialect vocabulary arrive separately.
The cache lasts five minutes, refresh is a visible command, DataPlayer DDL
invalidates exact scopes and a missing-object execution error invalidates the
relevant metadata without retrying the query.

Completion covers keywords, functions, schemas, relations, columns, aliases,
CTEs and parameters. It inserts the shortest unambiguous spelling: objects in
the first search-path schema unqualified, outside it schema-qualified, and
columns through an alias where one exists. Syntax errors are local errors;
unresolved objects become warnings only when the relevant metadata is known to
be complete. Otherwise the editor says insight is limited instead of drawing
false diagnostics. None blocks Run.

Explain is a separately declared read capability. Its structured source answer
drives a synchronised operation tree, sortable table and raw plan. Explain
Analyze is not a spelling variant: it runs the statement and therefore waits for
the same write/effect policy before being designed.

## History is sensitive content

A document is the current intention; history is what actually ran. Every
accepted success, failure, timeout, cancellation and interruption is retained by
default for the earlier of ninety days and one thousand runs. A user may choose
7, 30 or 90 days or no retention, and delete one, selected, older or all. When
retention is off, the operational row lasts only through terminal publication
and result expiry.

Query bodies, executed snapshots and explicitly remembered non-secret values are
encrypted under an independent query-content key. Secret values are never
stored. Plaintext metadata is limited to ownership, connector id, timestamps,
status, duration and counts. Search decrypts at most the bounded retained set in
server memory and creates no token index. The search text is neither retained
nor logged.

A lightweight lifespan task performs idempotent batch cleanup on startup and
periodically. Trash and history expiry do not justify a durable job framework;
snapshot TTL belongs to the in-memory store. There is no hidden audit copy after
the user deletes history. An audit product would need its own disclosure and
retention decision.

## Writes are a different mode

The existing grant scale remains the one authority: read opens the console and
read mode, write admits DML, structure admits DDL. An owner does not bypass the
scale. A connector adds an owner-controlled execution policy—read only, confirm
writes or allow writes—above those rights; a recipient cannot weaken it.

Every document opens read-only and never restores an unlocked mode. Confirm
policy requires typing the connector name and expires after fifteen idle
minutes; allow policy still names connector and database once. High-risk DML
and every DDL ask per execution. High risk is structural, determined by the
adapter: unrestricted update/delete/merge, truncation, drop, destructive alter,
permission change or a mutating script. A magic comment cannot turn it off.

Auto-commit wraps the whole run and commits only complete success. Manual mode
leases a connection on first Run and holds one visible transaction across runs.
It rolls back after five minutes without a database command, warns through the
last minute, and cannot be hidden by closing the panel without choosing Commit,
Rollback or Keep open. Lost heartbeat gets a short grace and then rollback.

PostgreSQL aborts a transaction after a statement error. Error, timeout and
Cancel consequently roll back the whole manual transaction and name the earlier
mutations undone. This is safer and clearer than holding an unusable connection
until the user discovers why every later command fails. Commit previews context,
age, ordered mutations, targets, affected rows, DDL and unknown counts and is a
durable event. User SQL cannot issue transaction, savepoint, session or prepared
statement control, because those would make the displayed state a lie.

DML arrives before DDL and returns command tag, affected rows, bounded RETURNING,
messages, duration and pending/committed/rolled-back state. A SELECT result is
never editable: the platform cannot infer a stable updatable row from arbitrary
joins, projections or aggregates, while relation tabs already have source-issued
handles.

The DDL vocabulary is deliberately closed to schemas, tables, views and indexes
for create/alter/drop, plus comments. Grants, roles, databases, tablespaces and
extensions need another security model; vacuum, reindex, cluster and similar
maintenance are actions or jobs. Destructive DDL is rehearsed and rolled back
under a short lock timeout, using PostgreSQL's own dependency answer. On commit
the adapter issues exact node invalidations, replacements or an explicit wider
scope. No client reparses ids from SQL.

## Rejected shapes

**A popup and an output document.** It loses the editor's identity, encourages
global current-state lookups and makes several consoles awkward. The workspace
already owns persistent work.

**One console per connector.** Independent drafts and parallel investigation
would overwrite each other. Connector plus document UUID is the identity.

**A saved-query type separate from scratch.** It creates a conversion step and
two lifecycles for one text. Naming a draft is enough.

**Holding a cursor for result paging.** It consumes a connection and transaction
for the time a person thinks. The manual transaction is the only feature allowed
to do that, visibly and with expiry.

**Re-executing for paging, filters, charts or downloads.** It changes the
snapshot and can repeat side effects. Every downstream tool reads the captured
result id.

**The parser as a security boundary.** Dialects and extensions defeat complete
classification. PostgreSQL transaction mode and the database role enforce what
the source can enforce.

**Every result in a new workspace tab.** Normal edit-run cycles would create a
tab explosion. Results live under the editor until explicitly promoted.

**A universal grid with source flags.** Relation mutations and query snapshots
have different controllers. The common part is presentation, not a bag of
optional callbacks.

**Editable SELECT results.** Appearance does not prove update identity.

**Arbitrary DDL and administrative SQL.** A complete text box is not authority
to invent a new permission or job model.

**Sharing queries in this phase.** Documents can contain secrets and snapshots
expire. Neither fits the existing link-to-a-view contract.

## Delivery order

1. Write these decisions and the threat model.
2. Extract and prove the shared tabular presentation with relation behaviour
   unchanged.
3. Add encrypted documents, library, revisions, conflict and Trash without
   publishing a query capability.
4. Add the PostgreSQL read kernel: prepare, immutable runs, idempotency,
   admission, timeout, cancel, safe diagnostics and snapshot store.
5. Complete selection/script execution, parameters, outputs, history, result
   tools and intelligence. Only then publish `SupportsQuery`.
6. Add Explain as a separately declared capability.
7. Add DML and its transaction lifecycle.
8. Add the bounded DDL vocabulary, preview and invalidation.

The deliberately hidden early slices let schemas and state machines be tested
without offering a primitive product. DuckDB/file SQL, execute-to-file, whole
snapshot charts, editable results, result diff, shared queries, Explain Analyze,
maintenance jobs and permission administration stay outside phase 3.

## Acceptance

Backend tests use real PostgreSQL for quoted delimiters, dollar strings,
writable CTEs, functions attempting writes in read-only mode, forbidden state
commands, parameter injection, mixed-class scripts, revocation between prepare
and execute, foreign document/run/result/cancel ids, idempotent retry and
conflict, timeout/cancel cleanup and a following pool query. Direct database
inspection proves encrypted bodies and remembered values are not plaintext;
captured logs prove SQL, secrets and connection strings are absent.

Every exact resource boundary is exercised, including the extra row for
truncation, oversize cell, total bytes, result count, document and statement
size, admission limit and LRU protection of active results. Cancellation of a
test `pg_sleep` reaches a terminal state within five seconds in the integration
environment. Tests shorten manual idle timeout through configuration and prove
rollback and pool return rather than sleeping for the production interval.

Frontend unit tests cover statement selection, keyboard commands, parameter
state, optimistic conflict, session shadow recovery, immutable snapshots,
previous-result labelling, pin/promotion, duplicate columns, platform sort,
history deletion, focus and the semantic state distinctions. The existing
relation grid suite proves the extraction did not change its behaviour.

End to end: a draft survives reload and becomes named; a parameterised current
statement returns typed rows; a script shows ordered outputs and stops; a long
query cancels and the next one runs; results pin, promote, compare, download and
chart; failed history restores; two tabs resolve a conflict; a read grantee
cannot unlock writes; auto-commit changes a relation; manual error rolls every
mutation back; destructive DDL previews and invalidates open views; revocation
leaves the document and disables Run.

After each API shape changes, the generated client is rebuilt. Phase 3 closes
only after backend tests and static checks, frontend unit/type/lint/build,
documentation checks and the complete E2E matrix are clean with user-approved
commands. Written implementation without that validation is `[~]`, not done.
