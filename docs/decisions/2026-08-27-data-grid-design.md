# A grid for exploring data

Date: 2026-08-27
Status: agreed
Round: 9

## Goal

Turn the existing view of the first rows into a working tool for exploring
data: server-side filters and multi-column sorting, explicit pages with a
configurable size, column sizes, order, visibility and pinning, tabular
selection and exact copying, display by value type.

The round stays **read-only**. Editing cells and rows is not hidden behind a
future flag in this same contract: it requires row identity, optimistic
locking and a separate source capability, so it will be the next standalone
stage.

## What exists before the round

`RowGrid.vue` reads 50 rows at a time through `POST /connectors/{id}/fetch`,
pages by `offset`, sorts by one column and shows the result through
`AppTable`. Filters are already part of the backend contract, but the UI
always sends an empty list. Rows arrive as `Any`, and a column's type as one
`data_type` string.

This is enough to prove a safe fetch, but not enough for a tool:

- the frontend would have to parse `numeric(18,2)`, `timestamptz`, `jsonb` and
  user-defined types itself, although D22 has already introduced the server
  model `ColumnType`;
- a JavaScript `number` cannot exactly represent every `bigint` and `numeric`;
- a click on a header does not express ordered multi-sort;
- QTable has no single model of a cell range, sizes, order and pinning;
- all state lives in the component and disappears when the application
  restarts.

The old application solved the table with its own `XTable`: separate
implementations of scroll, paginator, search, sort, resize, rows and fields.
The interaction ideas are useful, but copying yet another table engine is not
allowed — it is the same class of unbounded growth that the backend is being
rewritten over.

## Decisions

### R1. The grid is a separate frontend feature

`RowGrid` moves from `features/catalog` to `features/grid`. The catalog opens a
node and does not own the tool for working with its data.

Boundaries inside the feature:

- `DataGrid.vue` binds the data page, the TanStack Table state and the panels;
- `GridHeader.vue` holds the permanent command row;
- the filter, sort and column editors change only their own slice of state;
- the pure `format`, `clipboard`, `queryState` and `persist` need no mount;
- `RowsPanel` passes `connectorId` and `nodeId` and registers `reload()`, as
  today. The workspace learns not a single internal action of the grid (D12).

Rejected: leaving the feature in `catalog`: the relation structure already
lives separately, and filters, clipboard and column layout are not navigation.

### R2. TanStack Table runs the mechanics, DataPlayer the look

`@tanstack/vue-table` v9 is added. It is an MIT headless engine: state and
operations are there, there is no ready theme and no DOM. DataPlayer draws the
semantic table and header itself through its UI kit.

Only the needed features are used: cell selection, column sizing/resizing,
ordering, visibility, pinning and sorting state. The client row models for
sorting, filtering and pagination are not connected: the browser holds one
page, while the operations apply to the whole relation and are performed by
the source.

Rejected: building on QTable: it has server pagination, but range selection,
resize, stable pinning and reconciling these states would have to be written
by us. Rejected: AG Grid: spreadsheet range selection and a full clipboard
belong to Enterprise, that is, the needed set brings in a licence precisely
for the round's main scenario.

### R3. The result describes the capability of each column

`FetchColumn` becomes:

```text
FetchColumn
  name: str
  type: ColumnType
  sortable: bool
  filter_operators: list[FilterOp]
```

`data_type: str` is removed. `ColumnType` is reused from the relation model:
PostgreSQL builds it with the same `build_column_type`, the file reader
declares plain `number` and `string`. The frontend does not parse `type.sql`,
does not branch on the adapter type and does not decide by itself which
operations the source supports.

The global `FetchResult.sortable` and `filterable` are removed: a capability
can differ between columns. A file answers `sortable=false` and an empty list
of operators on every column; a complex PostgreSQL type may be visible but not
filterable. This is a more precise form of D2d, not a new table of exceptions
in the UI.

### R4. A value for reading is exact canonical text

`FetchResult.rows` becomes `list[list[str | None]]`. The adapter turns the
driver's typed value into canonical text according to `ColumnType`: integers
and decimals are not rounded, boolean is `true`/`false`, date/time is ISO 8601,
UUID is the full string, binary is hex. For a complex type PostgreSQL uses its
server text representation. Filtering and sorting still work over the original
typed column. Names are assembled only through `sql.Identifier`; client text
does not get into the shape of the `SELECT` (D2c).

This preserves `bigint`, `numeric`, UUID, timestamp with timezone, arrays and
ranges without passing through a JavaScript `number`. `None` stays separate
from the empty string. JSON arrives as valid compact JSON, binary as
unambiguous hex. The column type decides only the display; the clipboard and
the full view use the whole original string.

Rejected: `Any`: it is convenient for a short endpoint but does not promise
precision at the JSON boundary. Rejected: a tagged object in every cell: the
semantics are already listed once in the column, and repeating `kind` in every
row bloats a wide response.

### R5. A filter is a strict command, not a partially filled object

`Filter` becomes a discriminated union by `op`:

- `is_null` and `is_not_null` have no value;
- `in` requires a non-empty list of text values;
- the other operators require one text value.

The adapter checks the column name and that the operator is in its
`filter_operators`, then converts the value by the server-side metadata and
passes it to the driver as a parameter. An unsuitable operator and a wrong
value give 422 before the main query is run. Neither a type nor an SQL cast is
accepted from the client.

PostgreSQL starts with a conservative table: number, string and datetime
support comparison, `eq`, `ne` and `in`; string additionally `contains` and
`starts_with`; boolean, uuid and enum — `eq`, `ne`, `in`; all types — null
checks. Complex types are not filtered in this round except for null checks.
Sorting is enabled for number, string, boolean, datetime, uuid and enum. The
file source enables nothing. A new type capability is added on the server and
arrives in the response, rather than appearing as separate knowledge in the
frontend.

All conditions of the first round are joined with `AND`. `OR` and
parenthesised groups remain the next stage: they need a recursive expression
contract and a tree UI, not one more field in a flat list.

### R6. A page is a query, though the HTTP method stays POST

Reading moves from `useMutation` to `useQuery` with a key made of connector,
node, page size, offset, filters and ordered sort. POST is chosen so that a
structured filter does not get into the URL; that does not make an idempotent
read a mutation.

A query gives cancellation of a stale request, deduplication and protection
against a response that arrives after a newer one. Changing filters, sort or
page size sets page to zero. Moving to another page changes only offset.
Reload does a `refetch` of the same key without resetting the request (the tab
reload decision).

Page size is chosen from `50 / 100 / 250 / 500`, 100 by default. Pagination
stays explicit: it corresponds to a bounded `offset + limit`, makes selection
predictable and does not hide the cost of queries behind infinite scrolling.

WebSocket does not carry fetch. D18 explicitly rejects a second way to call
the same HTTP contract. A real-time row source will later add a capability and
a new topic; the transport will not have to change for that.

### R7. The grid header is a permanent place for commands

The first row always has one height and contains:

- `Filters` and the number of active conditions;
- `Sort` and the number of keys;
- column management;
- pin/unpin of the current column;
- Copy;
- page size;
- overflow for future commands.

An unavailable command stays in place, disabled, with an explanation, so the
header does not jump between sources and keeps a shape for extension.

`Filters` opens a second band: the active conditions, an editor for one
condition, Apply, removal and Clear all. A nullary operator hides the value.
Boolean and enum give a choice, `in` a list of separate values; number and
datetime are entered in a technical format without localisation. An error
stays with its condition and does not start a fetch.

### R8. One model of multi-column sorting has two entry points

An ordinary click on the main area of a header replaces the sort with one
column and cycles `ASC -> DESC -> none`. `Shift + click` adds or changes a
column in the ordered sort. An arrow shows the direction, a number the
priority.

The Sort button opens the same state as a list: direction, up/down by
priority, remove, clear. It is an accessible path that needs no knowledge of
the modifier, not a second sort that would have to be synchronised.

A separate zone of the header selects the column, because one click cannot
sort and select at the same time.

### R9. The layout and the query survive the session, the position does not

A versioned Zod schema stores, per `connectorId + nodeId`:

- column width, order, visibility and left pinning;
- filters;
- ordered sort.

Page size is one user setting for all grids. Page number, selection and an
open editor are not saved. After a start the user sees the first page with the
previous query: a saved offset could point at data that is no longer there.

Filters and ordered sort are written only after a successful response to their
`FetchRequest`. A failed query stays as state of the current tab and does not
become a saved view; from the error state retry and resetting filters/sort are
available, and the reset does not depend on column metadata in the failed
response.

On reading, the saved layout is reconciled with the actual columns by full
name: vanished ones are dropped, new ones are added on the right; a sort on a
non-sortable column and a filter with an operator no longer allowed disappear
too. An unknown version, invalid JSON or contradictory state is discarded
whole.

Resize is by drag; a double click fits the width to the header and the current
page. Pinning in the first round is left only. Columns manages order,
visibility, pinning and resetting the layout.

### R10. Selection applies only to the loaded page

Supported: a cell click, dragging a rectangle, `Shift + click`, arrows and
`Shift + arrows`. The number selects a row, a separate zone of the header a
column, the corner the whole page. Moving to another page and a structural
change of columns clear the selection: a page row id is not a record's
identity.

`Ctrl/Cmd+C` and Copy produce TSV of the rectangle from the full original
values. Headers are not added automatically; `NULL` becomes an empty cell, and
an empty string stays empty too — the type is distinguishable in the grid, but
TSV has no representation of SQL NULL. Inner tab, CR, LF and quotes are escaped
by a single pure serializer, and writing to the clipboard stays a thin browser
wrapper.

### R11. The type changes the renderer, not the value

- number is right-aligned and not localised;
- boolean is shown as the original canonical text `true`/`false`;
- date and timestamp stay in technical ISO 8601, the timezone is neither
  hidden nor recalculated by the browser;
- `NULL` is shown as the text `null`, separately from an empty string;
- UUID, network and binary use monospace;
- JSON, array and long text are shortened only visually.

A double click on a complex or shortened value opens a read-only viewer with
the full text and Copy. In the first round there is one text viewer; syntax
highlighting, images and specialised binary viewers are not part of the task.

### R12. An error does not pass old rows off as new ones

On the first load the table shows a skeleton. On a new query the previous page
is covered by a loading overlay. A new query cancels the previous one. After an
error the rows are removed and a safe message and Retry are shown: a page from
another filter state does not stay under a new header.

The header is available during an error. An invalid condition does not leave
the editor; a clipboard failure gives a toast. An empty page after a data
change does not trigger a hidden move back: `No rows`, Previous stays
available.

There is no virtualization in the first round. Page size limits the DOM to 500
rows, and an ordinary semantic table is simpler for sticky columns, focus and
accessibility. A separate browser scenario measures a wide page of 500 rows. If
it does not stay smooth, TanStack Virtual is added on measurement, not in
advance.

## What changes

**Backend.** `adapters/fetch.py` gets per-column capability and a strict filter
union. PostgreSQL reuses `build_column_type`, declares operators, converts
filter values and selects lossless text. File readers return the same models
with empty operators. The route stays the same; after the schema change the
OpenAPI client is regenerated.

**Frontend.** The dependency `@tanstack/vue-table` is added; `features/grid/`
gets components and pure modules. The old `catalog/RowGrid.vue` and `rows.ts`
are moved and split by responsibility. `RowsPanel` changes only an import. For
the header and viewer exactly those semantic wrappers are added to `shared/ui`
for which there really is a choice of appearance; Quasar primitives without
such a choice stay direct (D11).

**Documentation.** After implementation the new decision about the
column-specific grid contract gets a line in AGENTS.md and a home in
`architecture/adapters.md`; the structure of the frontend feature is updated in
`architecture/frontend.md`. Before the code, these files do not describe the
future as already existing.

## How it is checked

Backend:

- `FetchColumn` carries `ColumnType`, sortability and the allowed operators;
- `bigint`, `numeric`, datetime, JSON, binary and `NULL` pass without loss;
- an unsuitable operator and a wrong value give 422 before the main SQL;
- two filters give `AND`, multi-sort keeps its order;
- the file source declares the absence of sorting/filtering;
- the existing page, limit, ownership and injection tests stay green.

Frontend unit and component:

- parse, versioning and reconciliation of the saved grid state;
- page reset on filters, sort and page size;
- the formatter of each TypeCategory;
- TSV for a cell, range, row and column;
- click and `Shift + click` sorting;
- the filter editor and local validation;
- resize, auto-fit, visibility, ordering and left pinning;
- mouse/keyboard selection;
- loading, error, retry and disabled capabilities.

Playwright:

- open a PostgreSQL relation, apply two `AND` filters and an ordered
  multi-sort;
- change page size, select and copy a range;
- resize and pin a column, reload the application and see the restored layout
  and query on the first page;
- open the full viewer of a typed value;
- open a CSV and see disabled filters/sort;
- check the light and dark themes, a narrow workspace column and a page of 500
  rows without overlaps or a stuck interaction.

Checks of the affected sides: backend pytest, mypy, ruff, import-linter;
regeneration of the API client; frontend type-check, lint, unit, build and
Playwright; `scripts/check-docs.sh`.

## Next stages

- editing cells and rows: a write capability, a row key, concurrency and
  confirmation of changes;
- `OR` and filter groups: a recursive expression and a tree UI;
- realtime rows/streaming: a separate capability and topic, without a second
  fetch API;
- navigation along foreign keys from the relation model;
- saved named grid views and sharing them;
- export beyond the current page;
- virtualization, only if measuring a bounded page shows it is needed.

## What this round does not include

- writing, inserting and deleting rows;
- `OR`, parentheses and raw SQL conditions;
- infinite scrolling;
- polling and automatic refresh;
- client-side sorting/filtering of the current page;
- aggregations, groupings and pivot;
- localisation of numbers and dates;
- copying or exporting rows that are not on the current page.
