# The tabular surface

How a page of rows is drawn, kept, re-read, written out and charted. The
screens around it are in [frontend.md](frontend.md); what a source says about
its rows is in [sources/relations.md](sources/relations.md).

Decisions here: D24, D67, D28, D35, D111, D116.

## D24. The tabular surface is controlled state around a headless engine, and source operations stay server-side

`features/grid` owns the data explorer; the catalog only opens a node and the
workspace only hosts its panel. `TabularGrid.vue` binds a controlled typed page
and layout to the headless engine and owns selection, clipboard, presentation,
the full-value viewer and load/error states. Column identity is distinct from
its display label so duplicate or unnamed query columns remain addressable.
`DataGrid.vue` is the relation controller: it fetches and persists the page and
supplies editing, insertion, deletion, references, import, download and other
source operations through the tabular surface's slots. Query construction,
persistence, filter, sort, selection, clipboard and presentation rules remain
in plain modules. `GridHeader.vue` stays mounted at one height in loading, empty
and error states; a controller alone decides which source commands exist and
why a supported one is disabled.

The tabular surface paints its own `--dp-surface` background, matching sticky
headings, row selectors and pinned columns. Moving it into a floating window
does not expose the window's raised background through ordinary cells.

Data rows use one text line with compact vertical padding; a row action sits
beside its number and does not add another line. The column header uses the
shared toolbar height and the same button size as the command bar above it.
Columns without a saved width fit the current page's values and header,
within 72–480 pixels; double-clicking the resize handle fits them again. The
table uses fixed layout and the sum of visible column widths, so content and
unused viewport space cannot stretch a column beyond its chosen width. Dragging
updates the visible widths and saved layout continuously, including pinned offsets.

A captured query result is the second controller of that surface: it supplies
typed columns and a page read from the snapshot store, offers paging, filtering
and ordering over what was captured, and offers none of the row commands,
because an arbitrary projection has no row identity to act on.

TanStack Table v9 is the headless engine for cell selection, column sizing and
resizing, ordering, visibility, left pinning and controlled sorting state.
DataPlayer renders the semantic table and every control through its own kit.
TanStack's client-side sorting, filtering and pagination row models are not
registered: the browser holds one bounded page, while filters, ordered
multi-sort and paging apply to the relation and therefore remain adapter
operations.

Rows are fetched through TanStack Query with connector, node and the full
`FetchRequest` in the key. Changing filter, sort or page size resets the offset;
switching page changes only the offset; reload refetches the same key. A first
request shows a skeleton, a subsequent request covers old rows with an overlay
once it has lasted a quarter of a second, and failure removes them rather than
presenting a previous page under a new query. The delay is what keeps a tab on
a five-second refresh from blinking: the read is usually answered in tens of
milliseconds, and an overlay mounted over the whole grid for two frames is not
information.

Versioned local storage persists filters, ordered sort and column width, order,
visibility and left pinning per `connectorId + nodeId`; page size is global.
Filters and sort are committed only after the server accepts their fetch, so a
rejected query cannot become the view restored on the next open. The error state
also offers a query reset that clears both without depending on column metadata
from the failed response.

A column renamed or dropped while the tab is open leaves a live query naming
something the relation no longer has, and the source refuses it every time. The
grid recovers by itself: it forgets the cleared page in the client cache, asks
once with neither filters nor sorting, keeps back every filter and sort the
fresh answer still knows, and names the ones it dropped. Nothing reads the
refusal — the surviving columns come from an answer the source has just given,
so the same recovery covers a change made outside the application. It is
attempted once per exact query, so a 422 about anything other than a missing
column surfaces as the error banner instead of being cleared and refused for
ever.
Unknown versions and contradictory shapes are discarded, and restored state is
reconciled with the columns the server actually returned. Offset, selection and
open editors are transient: reload starts at the first page and a page or
structural column change clears a selection that has no stable row identity.

Selection and TSV copying use the current page's data and visible column order,
never rendered or truncated DOM text. Typed renderers change alignment and
appearance but not the canonical string; complex or long values open that same
full string in a read-only viewer. The page ceiling is 500 rows, with explicit
pagination rather than virtualization until browser measurement demonstrates a
need.

A cell whose column stands in a foreign key carries an arrow out of the row, on
the first of that key's columns that is on screen — one arrow per key, so a
composite one does not become two links. An empty cell carries none: there is
nothing in it to act on, which is the same reason a null value does not open the
viewer. Whether an incomplete key names anything is not decided here; the source
answers that when the arrow is pressed (D36).

What comes back is a node and a predicate. The workspace opens the rows tab of
that node, as the catalog would, and leaves the predicate where the tab picks it
up — the same shape `revealTarget` uses, because a tab opened a moment ago is
not mounted yet and a call into it would be lost. A followed predicate replaces
the tab's query and is remembered exactly as a filter the user typed is: a tab
shows the last question asked of its relation, whoever asked it. It lands over
the remembered query rather than under it, which is why the grid knows it was
navigated to.

Double-click opens an editor only when the fetched column is marked editable and
the row has a handle. A complex value keeps the established double-click viewer;
Shift + double-click opens its technical editor. The value remains canonical
text; SQL null is a separate choice, never an empty string. Saving is pessimistic
in the dialog and the successful mutation invalidates the page because a filter
or sort change can move the row. A 409 stays in the editor and asks for a reload
rather than overwriting a newer value.

Insert adds a draft row at the end of the current page, in the same columns as
the data it will become. Required columns are always supplied; entering an
optional cell includes it, while a reset action returns it to the source
default. Nullable cells offer SQL `NULL` separately from empty text. Omitted
fields never cross the boundary, so source defaults remain source defaults.
Hidden required columns are revealed when the draft opens. Delete becomes
available only when selection ranges span complete visible rows and every row
has an opaque handle. One destructive confirmation sends all handles together;
success clears the selection and invalidates the page, while any version
conflict leaves every selected row intact.

Known deviations:

- **There is no virtualization.** A browser scenario exercises a 500-row page;
  TanStack Virtual is deferred until measurement shows that bounded DOM is not
  responsive enough.
- **Saved views are local and unnamed.** Grid state follows one browser and one
  connector/node pair; it cannot yet be shared or selected as a named view.
- **Clipboard and selection stop at the current page.** Exporting rows that are
  not loaded needs a server-side export capability, not a larger client page.

Spec: [The data exploration grid](../decisions/2026-08-27-data-grid-design.md)

## D67. A grid re-reads itself on a timer it wears, and a pause is a rule

The tab's reload button belongs to the panel engine, which knows nothing about
the application (D12). An interval, a persisted choice per relation and a list
of reasons not to fetch are knowledge about relations, so they live in
`features/grid`: `autoRefresh.ts` holds the offered intervals, the storage and
the pause rule, `AutoRefreshButton.vue` is the control, and `DataGrid.vue`
owns the timer because it owns the fetch.

The interval — 1 s, 5 s, 10 s, 30 s, 1 min, 5 min, or off — is written on the
button rather than hidden in its tooltip. A grid that refetches by itself and
looks exactly like one that does not is a grid whose rows move for no visible
reason.

Consequences:

- **A tick is "fetch unless something says not to".** One list says not to: a
  cell is open in the editor, a row is being written, rows are ticked, the tab
  is not on screen, or a read is already running. Both the timer and the
  tooltip read it, so what the grid does and what it says it is doing cannot
  drift. A selection holds it because a page arriving underneath a ticked row
  takes it away, and on a list of processes that means the row somebody meant
  to terminate is no longer the row they ticked.
- **A held tick is skipped, not queued.** The next one is at most an interval
  away, while a queue of them would all land together when the editor closes.
- **Not on screen covers both ways of being away.** A panel kept alive behind
  another tab and a hidden browser window are the same thing to the source, and
  a kept-alive grid would otherwise poll for ever with nobody looking. Coming
  back reads once at that moment.
- **The interval is remembered per connection and node**, beside the columns
  and the query already stored that way, in three states rather than two:
  nobody has ever chosen, somebody chose an interval, somebody chose Off.
- **A source may suggest one**, and the suggestion applies only where nobody
  has chosen for that relation. It is never written down — a default is not a
  decision — and Off therefore survives a source that suggests five seconds
  ([D70](sources/relations.md)). A suggestion that is not an offered interval
  is rounded up rather than down: polling faster than a source asked to be
  polled is the one direction that costs it something.
- **It re-reads through the grid's explicit refresh**, so the read cache is
  bypassed exactly as the reload button bypasses it (D31).

Known deviations:

- **Nothing says how long ago the page was read.** The button says the interval,
  not the age of what is on screen.
- **A refusal stops nothing.** A relation that has been dropped goes on being
  asked for every interval until the tab is closed or the interval turned off.
- **The shortest interval is one second, and no source is asked whether it can
  bear that.** A relation that takes four seconds to read simply never finishes
  before the next tick is skipped.

Spec: [A grid that re-reads itself](../decisions/2026-09-02-auto-refresh-design.md)

## D28. A download is a fresh copy of the bounded visible page, and where it goes is asked

Download repeats the grid's current `FetchRequest`, including its bounded
limit, offset, filters and ordered sort, then writes only the columns visible
in the controlled layout, in their displayed order. It is available for every
source that can answer `SupportsFetch`: CSV is a representation of the common
table boundary rather than a source-specific adapter capability.

**Downloading it and keeping it are two things, and the dialog asks which.**
They used to happen together: the file went to the browser and a copy stayed
in personal storage, so whoever wanted one of the two got the other as litter,
and a folder of every table anyone had ever looked at built up where the user
keeps their own files. **Download** hands the file over and leaves nothing;
**Save to my files** writes the copy and sends nothing back — its answer
carries a filename and a row count and deliberately no address, because an
address would be an invitation to do both again.

A kept file is UTF-8 CSV at
`downloads/<connector-id>/<table>-<timestamp>.csv` inside the current user's
personal directory. A download of the bounded page is the same bytes in the
response and no file at all; a download of every matching row is staged in a
temporary directory of its own outside personal storage, because a native
browser download needs an address to point at, and that file is removed as
soon as the ticket for it is redeemed. SQL null
is an empty unquoted field and every other value is quoted, which is what
PostgreSQL's own `COPY ... CSV` writes and reads back, so null stays distinct
from an empty string without a sentinel that a real value could equal. The
`\N` sentinel this started with could not: a cell holding those two characters
was indistinguishable from a null. The connector id in the
path preserves provenance even when two connections or tables have the same
display name.

The client does not upload the rows it already holds. The server authenticates
the connector, reads the bounded page again and validates the requested visible
columns against the fresh answer. Consequently, a source changed between the
screen read and the press of Download may produce a file newer than the pixels
still on screen. Freezing an exact earlier page would require a source-owned
snapshot or version token, not trusting client-supplied cells.

Commands concerning an open table live in its grid header. **Show structure**
therefore opens the structure beside the rows and is no longer repeated on
every describable catalog row; the catalog remains navigation and selection.
The header shows only commands the current representation supports, as icon
buttons with tooltips. A rows tab opened from the catalog retains the source's
ordered representations, so a source-named content alternative such as
**View DDL** is reachable without the grid inferring one. Column names select
whole columns; sorting, pinning and hiding are separate controls inside each
column header. The row-number column
and pinned data columns remain at the left edge, while reference controls sit
over the top-right of their cells without changing row geometry. Cell content
is aligned left regardless of its source type.

**Create table from these rows** uses D43's bounded cross-connector creation.
The grid remains the source: the workflow chooses a structure-writable target
connection and schema, starts the name from the source title, and maps each
source column to a target name and a target-declared type.

Download also asks which of two honest scopes is meant. **Current page** is the
bounded operation above. **All matching rows** keeps the committed filters,
ordered sort and visible-column order but drops paging, and is enabled only
when the source implements D44's streaming export. Its finished file is
followed through a native browser download rather than an XHR Blob, so a whole
relation is not reassembled in browser memory.

Known deviations:

- **A download of every matching row is written down before it is sent.** The
  file is outside personal storage and is removed when the ticket is redeemed,
  but a ticket nobody redeems leaves it in the system's temporary directory
  until that directory is cleared.

Spec: [Downloading the visible page, and the commands of an open table](../decisions/2026-08-28-page-download-design.md)

## D35. A chart is a closed view over one bounded fetch, not another query language

**Charts** in the grid header opens a work panel carrying the exact current
`FetchRequest` and the visible column names in their displayed order. The panel
asks through the same TanStack Query key as the grid, so opening it normally
reuses the answer already held by the browser and reloading it reads the same
bounded page again. The panel states its row range and whether more rows were
left out; it never implies that a page is the whole relation.

The chart vocabulary is a discriminated union of line, bar and pie with named
fields. There is no raw ECharts option and no expression string. The source's
column type is never rewritten: a declared number is a measure directly.
Because a CSV deliberately declares every field as text, a text field is also
offered as _numeric on this page_ only when every present value in this bounded
answer passes a finite-number conversion. The label says so, and another page
may honestly offer something different. A failed conversion and SQL null are
omitted rather than silently turned into zero. Bar and pie categories are
aggregated in the browser over this page only, and pie omits negative
observations.

Choosing a chart is controlled in the same way the grid is: the picker, the
suggestions and the remembered choice live in one component that is given
columns, rows and where they start. A relation's page and a captured query
result are two controllers of it, so neither grows its own chart language.

Suggestions are deterministic and local. A datetime plus a number suggests a
line, a categorical field plus a number suggests a bar, and the same pair may
suggest a pie only when the page has non-negative values and more than one
category. The model never sees the rows. The chosen chart is stored per exact
connector, request and visible-column set, while server data stays in
vue-query. Renaming a source node replaces the chart panel identity and moves
that client-only choice with it, like the rows and structure panels follow the
source-issued replacement identity under D32.

The first slice deliberately has no whole-relation aggregation, multiple chart
widgets, candlesticks or AI suggestions. Those require a source-owned aggregate
contract, a dashboard layout and a separate disclosure decision respectively;
none is smuggled into the bounded fetch contract.

**Known deviation.** An `echarts` fence inside a Markdown document (D50) does
carry a raw option object, and draws from a wider vocabulary than this panel —
scatter, radar, heatmap, gauge and funnel, with titles, zooming and marks. It is
not a chart over a connection: it reads no rows, names no relation and cannot
express a filter — the numbers were typed into the document by its author. The
rule above governs charts built from a source's data, and it is not extended to
pictures drawn inside documents. The two registrations are deliberately
separate: this panel can draw what it offers to build, and a document can draw
what documents contain.

Spec: [Charts over a bounded page](../decisions/2026-08-30-bounded-page-charts-design.md)

## D111. One row is read downwards over the page the grid is on

A wide relation is unreadable a row at a time in a grid, and the old
application's row window was where people actually worked. It is a panel of the
relation, not a second reading of it.

- **The same page, by the same query key.** The row view reads through the same
  `useRowsPage` the grid does, so opening a row costs no request and the two
  cannot disagree about what the row holds.
- **A row is a position, not a handle.** A handle exists only where a source can
  version a row ([D25](sources/relations.md)), and a keyless relation still has
  rows worth reading. The page travels with the position, because that is what
  the position is relative to.
- **Walking crosses pages.** `PREV` and `NEXT` move within the loaded rows and,
  at either edge, move the request by the limit it already carries. The request
  stays one the grid also uses, so the page a walk lands on is shared.
- **Walking does not move the page around.** The controls stay at the foot of
  the panel, one at each edge, while the table owns the space and scrolling
  above them. Its column tracks do not depend on the current row's values, so
  replacing a short value with a long one cannot move the other columns.
- **Badges come from the relation model and nowhere else.** A page of rows says
  nothing about a primary key, so a node the source will not describe has none
  and everything else still works — which is how a CSV is read here.
- **One panel per relation.** Opening another row tells the panel, the way a
  rows tab is told a predicate ([D36](sources/relations.md)); a tab per row
  would fill the strip by reading a table.
- Both directions of key navigation are offered per column, from the same two
  routes the grid uses ([D110](sources/relations.md)).
- **A source may withdraw it.** `record_supported` on the fetch result says
  whether one of these rows opens at all. A report is the answer to a statement
  rather than a thing that holds rows: it has no relation model, no key and no
  reference to follow ([D55](sources/actions.md)), so the panel would be these
  same values in a column and nothing else. The corner of the row then holds
  what the source does offer on it ([D70](sources/relations.md)).

Known deviations:

- **No editing.** The old window had one; editing a row is the grid's cell
  editor and its rules about what a source accepts, and a second editing
  surface is a second set of those rules.
- **No physical row identity on screen.** The old view listed `ctid` as a line
  of the row. That is a row handle by another name, and D42 already decided
  whose business identity is.
- **It does not follow the grid's selection.** The old window did until it
  froze itself, and the freezing is the tell: the useful state was the frozen
  one, on the row somebody chose to look at.

Spec: [One row, read downwards](../decisions/2026-09-05-row-view-design.md)

## D116. The row of commands keeps its shape, and says why a command is off

Twenty commands sat in one undifferentiated run, and which of them appeared
changed with the source: a file drew eleven, a table eighteen, a query result
eight. Nothing said where one kind of command ended and the next began, and no
button had a place a person could learn, because the buttons before it came and
went.

Two rules, and they only work together.

**Nothing is hidden for want of support.** A command the source cannot carry
out stays where it is, greyed, and says why on hover. The same answer the
command bar gives (D69) and for the same reason: a row that changes shape as
somebody walks between a table and a file is a row they have to read every
time. A group in which nothing is available keeps its place too — the point is
that the row is the same row everywhere.

**The commands are grouped by what they act on, and each group is named.** Five
groups, in the order of a working session: *The view* narrows what is on
screen, *Read it as* opens the same rows in another shape, *Take it out* copies
them somewhere, *Change the rows* writes, *This tab* is about the tab rather
than the data. `features/grid/toolbar.ts` holds the names and the order;
`GridHeader.vue` draws them and the lines between them, and offers a slot per
group so the grid that owns a command decides which group it belongs in.

Group captions use the shared UI font size and strong text token in sentence
case. Their names are navigation aids, not faint micro-labels; the toolbar
retains its horizontal scrolling when the captions need more room.

Consequences:

- **Everything that writes is together and apart.** That is half of why the
  groups are worth their room: it answers "where do I look" and "what can I
  press by accident" at once.
- **There are two kinds of off, worded apart and drawn the same.** One names
  something to do — tick a row, copy some cells — and the other says the source
  will never offer this, so a person can stop looking. They are two shades of
  the same grey on purpose: two shades of grey in one row is a distinction
  nobody compares, and the sentence is where the difference lives. What the
  source will never do outranks what is merely missing this second, because
  "tick a row" under a button that will never delete anything is a lie.
- **A disabled button has to be able to speak.** Quasar gives a disabled button
  no pointer events, so a tooltip hung on it never opens. `AppIconButton` wraps
  the disabled shape in a span that carries the tooltip instead — which is what
  removes D69's deviation for icon buttons rather than repeating its workaround
  at every call site.
- **The bar scrolls sideways.** It does not wrap, and it folds nothing away
  behind a "more" button: either would put a command somewhere other than where
  it was learned, which is the thing this decision exists to stop.
- **How many rows a page holds moved to the pager.** It is a fact about paging
  and it now sits beside the range it changes, rather than at the far end of a
  row of commands where it was the only control that did not do anything.
- **A command the source declares for itself goes in *Change the rows*.** An
  adapter says whether a command is destructive and not whether it writes, so
  this is true of every one that exists rather than known to be true of every
  one that could. A source-declared command that only reads would land in the
  wrong group; the fix then is for the declaration to say which it is.

Spec: [The row of commands above a table](../decisions/2026-09-06-grid-toolbar-design.md)
