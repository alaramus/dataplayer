# ClickHouse

What a ClickHouse source is, how it reaches the server, what its catalog shows,
and how its values and pages cross to the grid. The contract every source type
follows is in [contract.md](contract.md); reading a relation in general is in
[relations.md](relations.md). Read this before changing the `clickhouse`
adapter.

Decisions here: D267, D268, D269.

## D267. A ClickHouse source speaks HTTP, with the application's own client

The adapter talks to the server's HTTP interface (8123, or 8443 with TLS)
through `httpx`, which the application already has; there is no driver package.
A statement is the request body, a value is one of the server's own
`{name:Type}` parameters sent apart from it as `param_<name>`, and the user and
password travel as Basic authentication. A read carries `readonly=2` and
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
