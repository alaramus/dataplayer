# A ClickHouse source

Decisions D267–D269. The first slice of a ClickHouse source type that is meant
to reach what PostgreSQL does, in the six slices MySQL and SQLite went through.
This slice reads: a connection, its catalog, a relation's model, its summary and
DDL, and its rows. The SQL console, writing rows, structure changes, reports and
actions, exports, table copies, backups, sample data and metrics follow, each in
its own commit.

## Over HTTP, with the client the application has (D267)

ClickHouse speaks two protocols, native TCP on 9000 and HTTP on 8123. Three
ways to reach it were weighed:

- `clickhouse-connect`, the vendor's library — rejected: its asynchronous
  client is the synchronous one run in a thread pool, it converts every value
  to a Python object that has to be turned back into text (D23), and it brings
  NumPy-sized dependencies for formats this application never asks for;
- `asynch` or `clickhouse-driver` over the native protocol — rejected: a
  third-party reimplementation of a binary protocol that changes between
  releases, and ClickHouse Cloud is reached over HTTPS anyway;
- the HTTP interface through `httpx` — chosen. It is the interface the vendor
  documents first, it is asynchronous without a thread, cancelling a request
  closes its connection and `cancel_http_readonly_queries_on_client_close`
  makes the server stop the statement, and the server's own query parameters
  keep every value out of the statement text. There is no driver SDK to
  contain; an import-linter contract keeps every other source's driver out of
  the package instead.

Every read carries `readonly=2`: a read cannot write, and the request may still
carry the output settings of D268. The cost is that a user whose profile sets
`readonly=1` cannot be used at all; it is recorded as a deviation rather than
worked around by sending reads without settings, which would make values depend
on the user's profile.

The password travels as Basic authentication, which httpx encodes as UTF-8,
rather than in ClickHouse's `X-ClickHouse-Key` header; a test signs in with a
password in Cyrillic.

23.8 is the floor: the oldest LTS release that knows every output setting the
adapter sends. An older server would refuse a setting it does not know, and the
check says why instead.

A database is a schema to the catalog, as MySQL's is, and ClickHouse accepts a
dot in its name, so MySQL's node ids are moved to `app.adapters.database_ids`
and shared rather than copied.

A materialized view created without `TO` keeps its rows in a table named
`.inner_id.<uuid>`. Listing it beside the view would show a person a table they
never made, under a name they cannot type; it is read through the view.

## Values as the server writes them (D268)

The HTTP interface can answer in any of the server's formats. Two were tried:

- `JSONCompactStrings`, every value as its text — rejected: a NULL is the string
  `ᴺᵁᴸᴸ`, which a `String` column can also hold, and the two cannot be told
  apart;
- `JSONCompactEachRowWithNamesAndTypes`, typed JSON — chosen, with every number
  decoded as the text the server wrote rather than as a Python number. Integers
  and decimals are sent bare so that the decoder sees them as numbers, and
  `output_format_decimal_trailing_zeros` keeps `0.0000000000` the value a
  `Decimal(38, 10)` holds instead of `0`.

`date_time_output_format=iso` writes every moment in UTC with `Z`. The
alternative was the server's own `YYYY-MM-DD hh:mm:ss` in the column's zone,
which says nothing about which zone that is unless the type is read too; the
grid shows instants, and an instant with its `Z` needs no second fact.

An array, a map and a tuple cross as compact JSON rather than ClickHouse's text
format: JSON is what the grid already renders for structured values, and it is
also what `JSONEachRow` accepts back, which the row editing of a later slice
needs.

## Pages without a unique key (D269)

ClickHouse has no unique key: `PRIMARY KEY` is a sparse index over the sorting
key and accepts any number of equal rows. MySQL and SQLite order a page by a
key so that page two does not repeat page one (D231); here no key would do it.
A page is therefore ordered by the sorting key, which lets the server read in
its storage order and stop early, and then by every other column the grid can
sort. Rows equal in all of them are indistinguishable to a reader, so pages are
stable for everything a person can see.

An infinite table cannot be sorted, and `system.numbers` is one click away in
the catalog. The order is applied only for engines whose rows are a known
finite set; a URL, a file, a stream or a generator is read in its engine's
order, which is what a person reading it expects of a stream anyway.

The primary key is shown as an index marked primary and not unique. Showing it
as a primary-key constraint would promise what it does not do, and the row
editing of a later slice would believe it.

Filters compare with a parameter typed by the column, not a string: the server
then parses the value as the column holds it, so `-1` against a `UInt32` is
refused with the column's own message instead of silently matching nothing.
The type written into a parameter is either one of a fixed set or a number type
the catalog stated and a regular expression accepted; a client never writes it.
