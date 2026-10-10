# Editing data

Date: 2026-08-27
Status: agreed
Round: 10

## Goal

Add the first modifying scenario to the grid: safely change one cell of an
existing row, without guessing on the client either the row's identity or the
value's type, and without silently overwriting a concurrent change.

Insertion and deletion are not part of this round. Insertion has its own form
of required fields, defaults and identity; deletion has destructive
confirmation and bulk semantics. Making them special values of the update
command would tie three different operations to one unstable contract in
advance.

## What the old application had

The client built `where` itself: it preferred a hidden `ctid`/rowid/PK, and in
its absence sent all non-empty values of the row. It also guessed from the old
value whether to turn the entered text into a number or a boolean. The server
assembled `UPDATE ... SET ... WHERE ...` from these dictionaries and after
success reread the table.

The useful part of the behaviour — double click, a short edit and rereading —
stays. The contract is rejected: identical rows could change together, null
disappeared from the predicate, a concurrent write won silently, and the
browser and the database kept two implementations of types.

## Decisions

### R1. Editing is a separate capability

`SupportsUpdate` is added next to `SupportsFetch`, not inside it. A file stays
readable without implementing a write stub. The type registry derives
`Edit rows` from the Protocol the same way as the other capabilities.

But a type's capability does not yet promise that any of its relations can be
changed. Every `FetchResult` carries `update_supported`, `update_reason` and
`row_handles`, and every `FetchColumn` carries `editable` and `nullable`. So a
view, a table without a key and a generated column answer precisely, without
the frontend branching on PostgreSQL.

### R2. Identity and version are one opaque source handle

The frontend receives a handle string and returns it unchanged. For PostgreSQL
it holds the canonical values of the primary key and `xmin`, but this format
is not a public contract. Another adapter will be able to put an ETag, a
revision or its own key there without changing the API.

PostgreSQL allows update only for an ordinary or partitioned table with a
primary key. `ctid` was not chosen: it is the physical address of a tuple
version and changes with an update and with a rewrite of the table. Matching
on all values was not chosen, because it gives no identity at all.

### R3. UPDATE checks the key and the version that was read

The command holds `node_id`, `row_handle`, the name of one column and
`string | null`. The adapter rereads the metadata, rejects an unknown/generated
column, builds identifiers through `psycopg.sql.Identifier`, and passes values
as parameters.

The predicate consists of the primary key and `xmin`. Zero rows returned means
the record has changed or disappeared, and answers 409. The server does not
run a second SELECT to tell these causes apart: a race is again possible
between two statements, and the user's action is the same in both cases —
reread the row.

Success returns the whole row in the same canonical text as fetch, and a new
handle. This accounts for triggers, generated columns and a change of the
primary key itself.

### R4. The UI edits the exact boundary value

A double click on a simple `editable` cell opens one dialog. For a complex
value an ordinary double click keeps the existing full-value viewer, and
Shift + double click opens the technical editor. An empty string stays an
empty string; SQL `NULL` is a separate checkbox, only for a nullable column. A
boolean is chosen from two values; the other categories are entered as
canonical text at this stage. The server remains the only place of final
validation.

While the request is running, the dialog blocks a repeated write. An error
stays inside it, 409 included. After success the page query is invalidated and
reread: a change of a sort/filter column may change the row's position or
remove it, so an optimistic patch of the current array would be a lie about
server state.

### R5. One cell update — one transaction

There is no unsaved change set and no Apply button for the whole table yet.
One gesture creates one command, one transaction and one possible conflict. A
batch editor will require a model of draft rows, partial success and the order
of dependent changes; it is not added covertly on top of the first command.

## Errors

- 422 — the relation/column/handle/value is not fit for the command;
- 409 — the row was changed or deleted after the fetch;
- 501 — the adapter type does not have the capability;
- 502 — the source did not execute the request; only a safe message goes out.

## Checking

Backend tests prove the metadata, the ban on keyless/generated, an exact
update, the return of a generated value and the conflict of an old handle. A
grid unit test proves that the endpoint receives an opaque handle. Playwright
changes a nullable numeric cell to `NULL`, sees the text `null`, then returns
the fixture's original value.
