# Charts over a bounded page

## Problem

DataPlayer can read one bounded page of rows from PostgreSQL and files, but it
can only present that answer as a grid. A chart should be another view of the
same source-neutral table boundary. It must not quietly become an unlimited
read, an aggregation language or a client-provided dataset the server is asked
to trust.

The old application contains a capable chart workspace, but it takes arbitrary
arrays from a table store, infers types from samples and mixes deterministic
presets, AI suggestions and a dashboard layout in one feature. Those are useful
ideas, not a contract to copy.

## One view, named completely

Pressing **Charts** opens a work panel. The panel stores:

- the connector it came from; the node is named once by the request's `node_id`;
- the exact `FetchRequest`, including limit, offset, filters and ordered sort;
- visible column names in their displayed order;
- the title, connection name and adapter type needed after a reload.

The panel does not receive row values. It calls the same `useRowsPage` query as
the grid. Because the query key already contains the connector and complete
request, the first render normally reuses the answer in TanStack Query; an
explicit reload asks the source again with the same request. A chart restored
from workspace storage therefore remains meaningful without a rows component
being mounted beside it.

One panel identity is derived from the complete view. Opening the same request
and column order activates it; another page, filter, sort or column selection is
another chart view and may stand beside it. The small chance of a view-key hash
collision is accepted for a browser-local identity; the full request is still
stored and validated rather than reconstructed from the key.

The panel says `Current page` together with the absolute row range. When
`has_more` is true it also says that later rows are not included. This wording
is part of the correctness of the result: a sum or share drawn from fifty rows
must not look like a claim about five million.

## A closed chart vocabulary

`ChartSpec` is a discriminated union:

- line: an X field and one numeric Y field;
- bar: a category field and one numeric value field;
- pie: a label field and one non-negative numeric value field.

The synthetic `Row` dimension is allowed so a table with one numeric column can
still be plotted. Nothing else is executable: no SQL, formula, formatter
function or raw ECharts option crosses the feature boundary. The renderer is an
implementation detail behind pure builders.

The server's `ColumnType.category` is never rewritten. A declared `number` is a
measure. CSV deliberately declares every field as text because the source may
not infer a whole-file type from one page; the chart may nevertheless offer a
text field as _numeric on this page_ when every present value in this exact
bounded answer converts to a finite number. That label and the page notice make
the weaker claim explicit, and a different page may offer a different choice.
Datetime, string, enum, boolean and the other losslessly rendered types may
label a dimension. SQL null and failed conversions are absent observations,
never zero.

Lines keep row order for categorical X and use value/time axes where the source
type permits it. Bars aggregate equal labels by addition over the bounded page.
Pies do the same, reject negative observations and keep the largest twelve
slices, combining the rest as `Other`. These are presentation operations over
the fetched page, not source operations.

## Local suggestions and remembered choice

Suggestions are pure and deterministic:

1. a datetime and a numeric measure produce a line;
2. otherwise a dimension and measure produce a bar;
3. a pie is offered only for at least two labels and non-negative observed
   values;
4. identifier-shaped measures (`id`, `*_id`) rank behind another numeric field;
5. a numeric-only answer falls back to a line over `Row`.

The user may select any valid type and fields. The selection is client state and
is stored under the exact chart-view key; rows remain exclusively in TanStack
Query. When D32 replaces a node identity, the workspace replaces the chart
panel and moves that stored selection to the replacement key.

## Deliberate boundary of the first slice

There is one chart per panel, not a dashboard. The first slice has line, bar and
pie only. It does not fetch beyond the grid ceiling, aggregate on the server,
send samples to an AI model, accept arbitrary renderer configuration or invent
a saved-view backend model.

Whole-relation charts need an adapter capability with a closed grouping and
aggregate vocabulary. Multiple widgets need their own layout and persistence
decision. AI suggestions need explicit third-party disclosure and validation
of an even narrower output union. Each may be added later without changing what
this bounded chart claims today.
