# A BigQuery source

Google BigQuery as a source type of its own: a warehouse reached over its REST
API, read as projects, datasets and tables, queried in GoogleSQL from the
console, and changed by the console's DML and DDL and the catalog's actions.
It signs in the way GKE (D477) and Cloud SQL (D455) do: with one of the
owner's Google Cloud accounts (D451). Everything a query costs is said before
it runs, and a connection carries a ceiling Google itself enforces.

Decided with the owner on 2026-11-28:

- **Writes** go through the console only: DML (`INSERT`, `UPDATE`, `DELETE`,
  `MERGE`) and DDL are run there, each rehearsed for its cost first; the grid
  reads and never edits a row. Datasets and tables are made, renamed and
  dropped from the catalog.
- **Cost guard**: a hard ceiling per connection (`maximumBytesBilled`, 10 GB
  by default, changed in the form) that Google refuses above, and a question
  before any query estimated above a threshold (1 GB by default) naming the
  bytes and the price.
- **Test stand**: `goccy/bigquery-emulator` under the `tools` profile for
  pytest and Playwright; live checks by hand against the owner's GCP project
  (the one GKE was checked against, D477).
- **Sign-in**: a Google Cloud account only — a service account's key or the
  server's own identity (D452). No key in the connection form, no OAuth.

The next free decision numbers are D480–D489. Facts marked *to check* are
probed in a scratch script against the real API (and, separately, the
emulator) before the slice that relies on them, and the spec's architecture
file says *checked* with what was found. The template to copy is
`clickhouse/` (an SQL server spoken to over HTTP with the application's own
client) for the console and values, and `kubernetes/gke.py` for the token and
the REST client.

## One type, REST over httpx, a Google Cloud account (D480)

One type, `bigquery`, in a package `app/adapters/bigquery/`. **No client
library**: `google-cloud-bigquery` is synchronous, pulls in gRPC, protobuf and
(for speed) pyarrow, and adds nothing the REST API v2 does not give;
`bigquery.googleapis.com/bigquery/v2` is JSON and is read with httpx, as the
Container API is (D477). google-auth stays in `app.adapters.cloud.gcp`: the
adapter asks the account for an access token (`GoogleAccessToken`, scope
`cloud-platform`, already issued for GKE) at every session and again when it
has five minutes left, exactly as `kubernetes/session.py` renews GKE's.

The options are a discriminated union on `auth`:

- **account** — a Google Cloud account (`account_field("gcp")`); the
  **billing project**, where every job runs and is billed (empty: the key's
  own `project_id`; the server's identity must name one); **more projects**
  to show beside it, one per line, for data the account may read in other
  projects (`bigquery-public-data` is the obvious one); a **cost ceiling**
  (bytes, default 10 GB, at most 10 TB, D484); a **question above** (bytes,
  default 1 GB, D484); a **price per TiB** used only to say what a query
  costs (default 6.25 USD, the US on-demand list price; 0 for a project on
  capacity pricing, which then says bytes only); a **default location** for a
  query that names no table (empty: `US`).
- **emulator** — an `http(s)://host:port` endpoint and a project, no
  credentials: the emulator accepts any request. It exists for the test
  stand and a developer's own machine; the form says so in its description,
  and nothing about it is hidden, since it can reach nothing a person could
  not reach with `curl`.

A refusal is Google's status said by what it means (the D467 rule for
Kubernetes): 401 the account's token, 403 with `reason` (`accessDenied`: the
IAM role names the role that would do — BigQuery Data Viewer to read, Job
User to query, Data Editor to change; `billingNotEnabled`, `quotaExceeded`,
`rateLimitExceeded`: a sentence each), 404 a project, dataset or table that is
gone, 400 `invalidQuery` with Google's message — which is about the SQL the
person wrote and names no secret, so it is shown, cut to 500 characters. The
check is `projects.list` plus a dry run of `SELECT 1` in the billing project,
which proves the account may list and run jobs.

Not a pool: an HTTP client per session, as GKE's. The connection string shown
is `bigquery://<billing project>`; never a token (D15).

## What the catalog shows (D481)

A tree of levels like the database types (D229's ids, `database_ids.py`):

- the **billing project** and each of the more projects, as groupings;
- in a project, its **datasets** (`datasets.list`, paged), each a schema with
  its location as the caption;
- in a dataset, its **tables** (`tables.list`, paged): a table, a view, a
  materialized view, an external table and a snapshot, each the catalog's own
  kind (`table` or `view`) with BigQuery's word as the caption. Routines and
  models are listed in a dataset's **Routines** and **Models** folders, as
  read-only nodes whose content is their DDL.
- a **System** section of reports (D487).

`tables.list` gives no row count; opening or describing a table reads
`tables.get` once: its schema, `numRows`, `numBytes`, `numLongTermBytes`,
partitioning, clustering, expiry, labels and description. That answer is the
relation model (columns with their modes; a `REPEATED` field is an array, a
`RECORD` a struct), the summary (D75) and the content: the table's DDL
generated from it, the way `bq show --schema` would, read-only and marked
as generated (D57).

A project the account may not list datasets in is shown with its refusal on
it rather than hidden, so a typo in "more projects" is visible. Datasets and
tables are cut at 10,000 per level with a notice (D199's bounds).

## Reading rows without paying for them (D482)

A table's page with **no filter and no order** is `tabledata.list`
(`startIndex`, `maxResults`, `selectedFields`): free, and as fast as the API
pages. A page with a filter or an order, a view, a materialized view and an
external table are a query: `SELECT <columns> FROM \`p.d.t\` WHERE … ORDER BY …
LIMIT … OFFSET …`, built from the closed set of predicates (never a client
string, ENGINEERING's rule), every identifier checked against `tables.get`
and quoted with backticks, every value a named query parameter. That query
goes through the cost guard (D484) like any other, and the grid says above
the page what it read and cost.

*To check*: whether `tabledata.list` serves materialized views and snapshots
(it does not serve views); a table with `requirePartitionFilter` read by a
query without a partition filter is refused by Google with 400 — the grid then
says to filter on the partitioning column, named.

A page past 10,000 rows from the start is read by query only when the
offset could not be reached by `startIndex`, which is never for a table; for a
query it is the usual D64 bounded snapshot.

## Values (D483)

`tabledata.list` and `getQueryResults` give rows as `{"f": [{"v": …}]}`
with every scalar as a string; `formatOptions.useInt64Timestamp` makes a
TIMESTAMP a count of microseconds, turned into an ISO instant in UTC here.
Each type crosses as text the grid knows:

| BigQuery | Category | Text |
| --- | --- | --- |
| INT64 | number | as given (64-bit exact, never a float) |
| NUMERIC, BIGNUMERIC | number | as given, every digit |
| FLOAT64 | number | as given; `NaN`, `Infinity` kept as words |
| BOOL | boolean | `true` / `false` |
| STRING | string | as given |
| BYTES | string | base64, as given |
| DATE, DATETIME, TIME | datetime / string | ISO, no zone for DATETIME |
| TIMESTAMP | datetime | ISO in UTC from microseconds |
| INTERVAL, RANGE | string | BigQuery's own text |
| GEOGRAPHY | string | WKT |
| JSON | string | the JSON text, opened as a tree (D295) |
| STRUCT, ARRAY | string | JSON built from the nested `f`/`v` and the schema |

Filters take a column's category's operators; STRUCT, ARRAY, JSON and
GEOGRAPHY take none. Sorting on them is refused, as Google refuses it.

## The cost guard (D484)

Every job this source runs — a console statement, a filtered page, a query
behind an export or a report — is first sent with `dryRun: true`, which is
free and answers `totalBytesProcessed`, the statement type and the tables it
reads. Then:

- above the connection's **ceiling** the run is refused here, naming the
  bytes, without asking Google; the real run also carries
  `maximumBytesBilled` = the ceiling, so Google refuses whatever the estimate
  missed (`bytesBilledLimitExceeded`, said as the same sentence);
- above the **question** threshold the person is asked first, with the
  estimate in bytes and in money ("about 3.2 GB, ≈ 0.02 USD at 6.25 USD per
  TiB"), through the confirmation D66 already asks for a change — one
  question, whatever else it asks;
- below both it runs. A result served from cache costs nothing, and the
  answer's `cacheHit` says so beside the run.

The minimum Google bills per referenced table (10 MB) is added to the
estimate before comparing, so a small query on a small table is not called
free. The agent's tool runs the same guard; it never answers a cost question
itself — a query above the threshold ends its turn with the question to the
person (D136's rule for a change).

*To check*: whether `maximumBytesBilled` applies under capacity (editions)
pricing or is ignored there; what the emulator answers to a dry run (likely
0 bytes) — the tests of the guard then use a stubbed answer.

## The console (D485)

GoogleSQL only: `useLegacySql: false` on every job, and a statement starting
with `#legacySQL` refused. Statements are classified by sqlglot's `bigquery`
dialect (D62), as ClickHouse's are by its own (D270); a parameter is
`@name` and is sent as a named query parameter.

Families refused by their words because they reach outside the warehouse or
outside what the console owns (D383's rule): `EXPORT DATA`, `LOAD DATA`,
`CREATE EXTERNAL TABLE`, `CREATE … CONNECTION`, `GRANT` / `REVOKE`,
`CREATE CAPACITY` / `RESERVATION` / `ASSIGNMENT`, and `BEGIN TRANSACTION` /
`COMMIT` / `ROLLBACK` written by hand. `CALL` and an unclassified statement
are `unknown` and run alone as the owner, confirmed (D383).

Transactions: **Read** and **Auto-commit** only, as ClickHouse (D271). A run
of several changing statements is one script job wrapped in `BEGIN
TRANSACTION; … COMMIT TRANSACTION;`, so the run's promise — kept when it
succeeds — holds; DDL cannot run in a transaction (*to check*), so a run
holding DDL holds that statement alone. No manual transaction: BigQuery's
sessions could hold one across jobs, which is a later decision.

A run is `jobs.insert` with a job id made here (`dataplayer_<uuid>`), the
location the dry run reported, `maximumBytesBilled`, and a label
`dataplayer=console`. Results are read with `jobs.getQueryResults` page by
page up to D64's ceiling; Stop is `jobs.cancel`. A DML statement's
`numDmlAffectedRows` is its count. The run's line says the job id, bytes
billed, slot time and whether the cache answered. Explain is the dry run's
answer plus the finished job's `queryPlan` stages, read as rows.

## Structure and catalog actions (D486)

From the catalog, each rehearsed by a dry run of the DDL it will send and
answered with what it would do (D46):

- **datasets**: make one (name, location chosen from BigQuery's list of
  locations, default table expiry, description), drop one (with its contents
  named by count; `DROP SCHEMA … CASCADE` only when the person ticks it);
- **tables and views**: rename (`ALTER TABLE … RENAME TO`), drop, copy
  within the project (a copy job, free), set expiry, description and labels;
- **columns**: add (nullable or with a default), drop, rename, widen a type
  BigQuery allows widening (`INT64` → `NUMERIC` → `BIGNUMERIC`, `NUMERIC` →
  `FLOAT64`), set or drop a default, set a description — each its own
  `ALTER TABLE`, since BigQuery runs them without a transaction.

The table designer (D117) makes a `CREATE TABLE` with columns of BigQuery's
types (STRUCT and ARRAY written in its own syntax), a partitioning (by a DATE,
TIMESTAMP or DATETIME column, by ingestion time, or by an INTEGER range),
clustering by up to four columns, a description and an expiry. Indexes and
constraints are not offered: BigQuery's primary and foreign keys are not
enforced, and declaring one is a known deviation (ddl.md) — read and shown,
not made.

## Reports, search, export and metrics (D487)

A **System** section of reports read like tables (D55), every one from an
API that costs nothing, not from `INFORMATION_SCHEMA` (each query of which
bills at least 10 MB):

- **Jobs**: `jobs.list` of the billing project, the last 24 hours, this
  account's and, when allowed (`allUsers`), everybody's — kind, state, who,
  started, duration, bytes processed and billed, slot time, cache, error;
- **Datasets**: every dataset of the shown projects with location, tables,
  default expiry, created and changed;
- **Locations**: BigQuery's regions and multi-regions.

Search: `EnumeratesNames` and `SupportsNodeSearch` over datasets and tables
by name, read by the list APIs (D199's bounds); `SearchesColumns` over the
columns of the tables already described this session, never by asking every
table.

Export (D44): a table's every row by `tabledata.list` pages (free) when the
grid has no filter or order, otherwise the grid's query through the cost
guard. A query result is exported from its job's results.

Metrics (D125): a poll reads `jobs.list` since the last poll — jobs run,
failed, bytes billed and slot seconds, per user — a free call; the preset is
**BigQuery jobs**.

## Copying tables and loading files (D488)

Out of BigQuery: a table's rows travel as its `tabledata.list` pages into
another connection (D182, D168), its structure described from `tables.get`
in the shared vocabulary of types.

Into BigQuery: rows pasted or copied from another connection, and a CSV or
JSON file loaded (D45), go through a **load job** with a multipart upload of
newline-delimited JSON — free, not streamed, so it also works in the
sandbox — into a table made first from the structure, or appended to a
ticked one. A load is a job (D81) with the upload's progress and the load
job's outcome. Rows as `INSERT` statements are not used: each would be a paid
query.

## The test stand and what is not a lab (D489)

`goccy/bigquery-emulator` (*to check*: the image and version that answer the
REST paths above) runs under the `tools` profile with a project `test` and a
dataset seeded from a YAML file kept in `backend/tests/adapters/`, its entry
in `tests/utils/services.py`, skipped without it. The emulator's known gaps
are written down as they are found; the cost guard and the refusals are tested
against stubbed answers recorded from the real API.

Live checks are done by hand, not in CI: a scratch script and the browser
against the owner's project with the service account already used for GKE,
whose role needs BigQuery Job User and BigQuery Data Editor on a test dataset
(`dataplayer_test`, made and dropped by the check). The public dataset
`bigquery-public-data.samples` is read for the free paths.

There is **no lab and no service template**: BigQuery is not a server that
runs in a container, and the emulator is a test tool, not a product a person
would start here.

## The slices

1. **Read only** (D480–D483): options, the account's token and its renewal,
   the emulator way in, the check, the catalog with projects, datasets,
   tables, routines and models, `tables.get` as relation model, summary and
   generated DDL, free pages by `tabledata.list`, values, a card and an icon
   (`bigquery.svg`); filters and order as a query **with the cost guard
   (D484)**, since that is the first query the type runs.
2. **Console** (D485): classification, refused families, Read and
   Auto-commit, jobs with ids, labels and locations, results paged, Stop,
   Explain, the cost question in the console.
3. **Structure and catalog actions** (D486): datasets, tables, columns, the
   designer.
4. **Reports, search, export, metrics** (D487).
5. **Copying tables and loading files** (D488).

Every slice keeps what ENGINEERING asks: tests beside the code, the seven
locales, the guide page `source-bigquery.md` and its translations, the
architecture file `docs/architecture/sources/bigquery.md` with one section per
decision, and the AGENTS.md rows. The work is on a branch `bigquery-adapter`.

## Not planned

- **Editing rows in the grid.** Every edit would be a paid DML query and
  BigQuery has no row key; the console is where a change is written.
- **The Storage Read and Write APIs.** gRPC and Arrow for speed the REST API
  does not need at the sizes a grid and an export read.
- **A manual transaction across runs** through BigQuery sessions.
- **Legacy SQL**, BigQuery ML beyond listing models, BI Engine, reservations
  and capacity management, Data Transfer Service, row-level and column-level
  policies beyond showing that a table has them.
- **Signing in** with a key in the form or with a person's Google sign-in.
- **INFORMATION_SCHEMA reports** that bill per query; revisited if a free API
  is missing for something people ask for.
