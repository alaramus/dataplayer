# ClickHouse

What a ClickHouse source is, how it reaches the server, what its catalog shows,
how its values and pages cross to the grid and are changed there, how its
structure is changed and a table designed, its reports, search, export and
catalog actions,
and how its SQL console differs from PostgreSQL's. The contract every source type
follows is in [contract.md](contract.md); reading a relation in general is in
[relations.md](relations.md). Read this before changing the `clickhouse`
adapter.

Decisions here: D267, D268, D269, D270, D271, D272, D273, D274, D275, D276.

## D267. A ClickHouse source speaks HTTP, with the application's own client

The adapter talks to the server's HTTP interface (8123, or 8443 with TLS)
through `httpx`, which the application already has; there is no driver package.
A value is one of the server's own `{name:Type}` parameters, never in the
statement; the statement and every `param_<name>` travel as fields of a
multipart body, so the address — which httpx writes into its log — carries
settings alone, and the user and password travel as Basic authentication. An
insert's rows are its body, and its statement, which binds nothing, is in the
address. A read carries `readonly=2` and
`cancel_http_readonly_queries_on_client_close`, so it cannot write and a
request that goes away stops its statement on the server. A connector keeps one
client in the resource store; its connections are reused below the server's
keep-alive. A server error is reduced by its code, never by its text.

TLS, when asked for, verifies the server's certificate. Options are host, port,
TLS, a user (`default` unless named), an optional password and an optional
database that says where the catalog opens. `clickhouse://`, `http://` and
`https://` addresses are parsed; `?secure=true` or `https` is TLS.

The catalog is databases as schemas, named as databases, whose node ids are
MySQL's (`app.adapters.database_ids`, D229), then their tables, views and
materialized views from `system.tables`. `system`, `information_schema` and
`INFORMATION_SCHEMA` belong to the server. The `.inner.` and `.inner_id.`
tables a materialized view keeps its rows in are not listed. A row estimate and
a size are `total_rows` and `total_bytes`, which only some engines report.

ClickHouse 23.8 and later; the check refuses an older one with its version
named.

Known deviations:

- A user whose profile sets `readonly = 1` cannot read through this source: the
  server refuses every setting a request carries, and every read carries some.
- A self-signed certificate cannot be trusted; TLS is verified or off.
- The native protocol (9000) is not spoken.

Spec: [A ClickHouse source](../../decisions/2026-10-25-clickhouse-source-design.md)

## D268. Values are the server's own JSON, numbers as written

Every answer is `JSONCompactEachRowWithNamesAndTypes` with 64-bit integers and
decimals unquoted, decimals with their whole scale, NaN and infinity as words,
UTF-8 validated, and `date_time_output_format=iso`. Lines are decoded with
every number kept as the text the server wrote, so a `UInt256`, a `Decimal(76,
…)` and a `Float64` cross unrounded. A scalar is its text; an array, a map or a
tuple is compact JSON with its numbers as written (a named tuple as an object).
Every `DateTime` and `DateTime64` is shown in UTC with `Z`, whatever zone its
column keeps; a filter value without an offset is UTC as well. A page is
buffered by the server (`wait_end_of_query`), so a failure halfway is a refusal
and not half a page; an exception inside a streamed answer is plain text, which
no line of JSON is.

Known deviations:

- A `String` or `FixedString` holding bytes that are not UTF-8 shows them as
  replacement characters.

Spec: [A ClickHouse source](../../decisions/2026-10-25-clickhouse-source-design.md)

## D269. No key is unique: a page is ordered by the whole row

ClickHouse's PRIMARY KEY orders and finds rows and never refuses one, so it is
shown as an index (`primary`, not `unique`) and never as a constraint, and a
table has no candidate key. A page is ordered by the reader's sort, then by the
sorting key's columns, so the server reads in its own order, then by every
other column the grid can sort; rows equal in all of those are the same row to
anybody reading them. Only an engine whose rows are a finite set the server can
sort is ordered so — the MergeTree family, Log, Memory, Join, Dictionary,
Distributed, Merge, Buffer, the views, EmbeddedRocksDB and KeeperMap; anything
else, `system.numbers` among it, is read in the order its engine gives. Checks
and assumptions are read from the table's own `CREATE` text, the only place the
server keeps them; skipping indexes from `system.data_skipping_indices`.

A filter compares with a parameter typed by its column: a number as the
column's own number type, so the server refuses a value the column cannot hold
(`BAD_QUERY_PARAMETER`), a moment as `DateTime64(6, 'UTC')`, a day as
`Date32`, and text, an enum's label, a UUID, an address and a boolean as theirs.
`contains` and `starts_with` are `position` and `startsWith`, so `%` and `_` are
characters.

Known deviations:

- Rows equal in every sortable column but different in a map, JSON or another
  column the grid cannot sort may change places between pages.
- A table of an engine outside the list above may repeat or skip rows between
  pages.

Spec: [A ClickHouse source](../../decisions/2026-10-25-clickhouse-source-design.md)

## D270. Statements are read by sqlglot's ClickHouse dialect; a parameter is `{name:Type}`

Statements are split by sqlglot's ClickHouse tokenizer and classed by its
parser, as MySQL's are (D232). What the parser keeps as a bare command is
classed only by the keyword it kept: `SHOW` is a read, `OPTIMIZE` and `SYSTEM`
maintenance, `ALTER`, `CREATE`, `DROP`, `RENAME`, `EXCHANGE` and `ATTACH`
structure, `ALTER … UPDATE` a change of rows. Three shapes the parser refuses
are read off the tokens: `EXISTS` and `CHECK TABLE` are reads, and `INSERT …
FORMAT` with its rows after it is a change of rows. A mutation, `ALTER TABLE …
DELETE` or `UPDATE`, is a change of rows rather than of structure. `EXPLAIN`
is Explain, a command of its own beside Run (D65); `EXPLAIN AST`, `SYNTAX`,
`QUERY TREE`, `PIPELINE`, `ESTIMATE` and `TABLE OVERRIDE` answer about the
statement and are reads.

The vocabulary of structure changes is databases, tables, views and
dictionaries. Users, roles, row policies, quotas, settings profiles, functions
and named collections are refused by name, and so are `SYSTEM`, `DETACH` and
`ATTACH`, `GRANT` and `REVOKE`, and a `SELECT … FORMAT`, whose answer the
console could not read.

A parameter is the server's own `{name:Type}`: its value travels as
`param_<name>` and the server parses it as the type the statement names, a
NULL as `\N`. `QueryProfile.parameter_syntax` is `named_braces`, and the
editor offers a known parameter as far as its name.

Spec: [The ClickHouse console](../../decisions/2026-10-25-clickhouse-console-design.md)

## D271. Every change is kept at once, so a change runs alone

ClickHouse has no transaction a client can hold or roll back: an insert, a
mutation and a structure change are kept the moment they end. The console
therefore offers Read and Auto-commit only, never a manual transaction and
never a rehearsal, and a run that changes anything holds that one statement,
so Auto-commit's promise — a change is kept when its run succeeds — holds
(the rule D233 makes for MySQL's structure changes, for every change here).
A read carries `readonly=2`, which the server enforces under the class. A
mutation is waited for (`mutations_sync=1`), so its statement ends when the
rows have changed.

A statement's limit is the server's `max_execution_time`, with the adapter's
own clock five seconds behind it; when that runs out, or Stop is pressed, the
statement is killed by its query id from a request of its own. A result is
read a line at a time and the request closed once the row ceiling is passed,
which stops a read on the server; anything else that was cut short is killed.
The server's sentence of a failure is shown without its error name and
version, with the position of a syntax error.

Known deviations:

- A script that changes several things is run a statement at a time.
- `SET` and `USE` are not run: each statement is a request of its own, so a
  setting would last for that statement alone. `SETTINGS` on the statement
  and the document's database do the same work.

Spec: [The ClickHouse console](../../decisions/2026-10-25-clickhouse-console-design.md)

## D272. A row is its whole row; rows alike are changed together

No key of ClickHouse is unique (D269), so a row's handle carries every value
its page showed and a digest of them (`app.adapters.row_handles`, shared with
MySQL). It is found again by every column that compares exactly — not a float,
which may be NaN, not a map, JSON, a variant or an aggregate state — and the
change is made only when every row found digests as the row shown; rows alike
in what compares and different elsewhere are refused rather than guessed
between. Rows the same in every value are one row to anybody reading them:
an edit changes all of them and a delete removes all of them, and the count
says so.

A change is a lightweight `UPDATE` or `DELETE`. A table made without the block
number column a lightweight update needs answers `NOT_IMPLEMENTED`, and is
changed by the `ALTER TABLE … UPDATE` or `DELETE` mutation instead, with
`mutations_sync=1`. The row is then read back as the server shows it.

A value goes back as it was shown: `accurateCast` of its text to the column's
type, which refuses what the type cannot hold, a moment through
`parseDateTime64BestEffort` in UTC, and an array, a tuple or a shape from its
JSON to the server's text first. The column's type travels as a parameter too.
Every value is cast by a `SELECT` before anything is written, a refused batch
halved until the refused values are named, so a paste lands whole or not at
all. Rows are inserted as `JSONEachRow` in one statement; a column left out
takes its default, which every ClickHouse column has.

Only a MergeTree table's rows are changed; Log, TinyLog, StripeLog, Memory,
Buffer and Distributed tables take inserted rows; a view, an engine reading
from outside and the server's own tables take nothing. A column of the
sorting, primary or partition key, a computed column and a map, JSON, variant
or aggregate column are not edited.

A parameter's value is sent in the server's escaped text, so a backslash, a
tab or a line break in a name, a filter or an edited value arrives as typed.
A value typed for the console keeps the server's own reading, as
clickhouse-client's `--param_` does (D270).

Known deviations:

- The check and the change are two requests with no transaction between
  them, so a change somebody makes in between is not seen.
- A table without lightweight updates is changed by a mutation, which rewrites
  the parts it touches; a paste of many rows is a mutation per row.
- An inserted row has no handle until the page is read again.

Spec: [Editing ClickHouse rows](../../decisions/2026-10-25-clickhouse-rows-design.md)

## D273. Structure changes are checked before the mutation that makes them

Only a MergeTree table's structure is changed: Log, Memory and the rest answer
`NOT_IMPLEMENTED` to most of `ALTER`, and a view has no columns of its own.
Every statement waits for what it starts (`mutations_sync`, `alter_sync`).

A column is added, dropped, renamed, given or relieved of a literal default,
and changed in type or nullability. A type comes from a closed vocabulary of
scalars; a column that may hold NULL keeps `Nullable`, and `LowCardinality`
stays outside it. `MODIFY COLUMN` with the type alone keeps the default, the
comment and the codec. A default is a parameter typed as the column, which the
server keeps as a constant. A column of the sorting, primary or partition key
is not dropped, renamed or changed: it decides where rows are kept.

ClickHouse changes a column's type in its metadata at once and converts the
rows in a mutation afterwards; a mutation that meets a value it cannot convert
leaves the table unreadable and every later change waiting behind it. So the
values the new type refuses are counted first with `accurateCastOrNull`, and
the NULLs before a column is made to require a value, and the change is not
made while either count is above zero. A mutation that fails all the same is
killed and the old type put back.

A skipping index — min and max, a set of up to a hundred values, or a Bloom
filter, over any columns, one granule at a time — is added and then
materialized over the parts already written, and dropped again if that fails.
Its name is derived from the table and its columns. None is unique, and the
primary key is not dropped. ClickHouse has no unique key and no foreign key,
so no constraint is made or dropped.

Known deviations:

- A conversion `CAST` accepts and `accurateCastOrNull` refuses — `1.5` into an
  integer — is refused rather than rounded.
- A type change rewrites every part of the table, however few rows it has.

Spec: [Changing ClickHouse structure](../../decisions/2026-10-25-clickhouse-structure-design.md)

## D274. A designed table is one CREATE TABLE of a MergeTree

The table designer plans one `CREATE TABLE … ENGINE = MergeTree`, the
statement the person reviews and the one that runs composed by the same code,
as MySQL's is (D236). The primary key becomes `ORDER BY`, and the plan warns
that it orders and finds rows without stopping two from sharing it (D269); its
columns must require a value, since a key cannot be `Nullable`. No primary key
is `ORDER BY tuple()`.

A column that may be empty is `Nullable`, `LowCardinality` kept outside it; an
array and JSON cannot be, and the plan says such a column will always have a
value. A literal default is a string literal the server converts to the
column's type; an expression default and a computed column (`MATERIALIZED`)
use the published functions — `now()`, `today()` and `generateUUIDv4()` fill a
default or a computed column only. A check is `CONSTRAINT … CHECK`, a
skipping index is written inside the table with the methods of D273, and every
name is derived from the table when none is given.

A unique key, a foreign key, an identity column, a collation, an index with an
order, extra columns or a predicate, a partition by range, list or hash, an
unlogged table and a hypertable are each a problem on the object that asks for
it. Create table is the source's catalog action on a database the server does
not own.

A table made from rows is a MergeTree with `ORDER BY tuple()` and every column
`Nullable`; every value is tried before the table is made, and the table is
dropped again if its rows are refused once it exists.

Spec: [Designing ClickHouse tables](../../decisions/2026-10-25-clickhouse-design-design.md)

## D275. Reports read the system tables; search narrows on the server

A System section after the databases holds eight reports, each a statement
written in this package over the server's `system` tables: processes,
mutations, merges, table sizes, disks, changed server settings, metrics and
users. A report pages, sorts and filters as a subquery, its columns as
`DESCRIBE TABLE` gives them, ordered by a stable key of its own; its rows are
lines of an answer, so nothing is written through them and no table is made
of them (D72, D111). Changed settings are the server's (`system.server_settings`):
every request here carries settings of its own (D268), which would fill a list
of the session's.

Processes offer Cancel query (`KILL QUERY … SYNC` by query id) and Mutations
offer Stop mutation: a mutation's own id repeats from table to table, so its
report names each by a hash of its database, table and id, and `KILL MUTATION`
finds it by the same hash. A failing mutation holds up every later change of
its table (D273), and this is how a person clears one.

Search by name and by column asks the server for candidates holding every
word — `positionCaseInsensitiveUTF8` on a bound value, so nothing typed is
compiled and `%` is a character — at most five thousand, and classes them here
by the shared word rule (D202), as SQLite's search does. A relation found by a
column carries that column, or the column's comment, or its own comment as
evidence. The inner tables of materialized views are not found. Every
matching row of a page is exported from one streamed request, the server
stopping the read if the reader goes away.

Known deviations:

- A search reaching five thousand candidates says it may have missed some;
  the best of a larger catalog may be among those not handed over.

Spec: [ClickHouse reports, search and export](../../decisions/2026-10-25-clickhouse-reports-design.md)

## D276. Catalog actions preview from the system tables; nothing is rehearsed

New database at the top of the connection; on a database Create table (D274),
Load from CSV, Drop database and Model as code; on a table or a view Rename,
Move to database, Drop and Model as code. The server's own databases offer
Model as code alone. Every statement is waited for (`alter_sync`).

ClickHouse keeps every structure change at once (D271), so nothing is
rehearsed; a preview reads the `system` tables instead. No foreign key stops a
drop, so what a preview names is what would stop working: the materialized
views fed by a table being dropped, which `system.tables` records as its
dependencies. Plain views are not recorded and are not named. A database is
dropped only when the preview has said what it holds — tables, views,
dictionaries — and the person ticked to drop it all. Views are dropped before
tables in a set, so a materialized view goes before the table it reads.

Rename and Move are `RENAME TABLE`, for tables and views alike. A table loaded
from a CSV file is a MergeTree of `Nullable(String)` columns made as a table
from rows is (D274). The server's own limit on dropping a large table
(`max_table_size_to_drop`) is passed on as a sentence.

Known deviations:

- A plain view that reads a dropped table is not named in the preview: the
  server keeps no list of what a view reads.

Spec: [ClickHouse catalog actions](../../decisions/2026-10-25-clickhouse-actions-design.md)
