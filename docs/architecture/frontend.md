# Frontend

How a screen is built, where state lives, and what the component kit is. The
panel engine, the layout and floating windows are in
[workspace.md](workspace.md).

Decisions here: D6, D7, D11, D24, D28, D35.

## What exists today

Vue 3, TypeScript, Quasar, Vite, TanStack Query, Pinia. Sign in, a catalog of
source types, a form generated from the adapter's own schema, the list of
connections, the catalog of a connection as a list of one level, and a typed
data grid with server paging, filters, ordered sorting and guarded cell editing;
the structure tab adds and drops columns through source-declared capabilities.
Catalog leaves open through the source's preferred representation: editable
text, JSON and JSONL open as source, PNG and JPEG open in a bounded verified
image viewer, and a declared table alternative opens the grid only when
requested. PostgreSQL relations keep that grid as preferred and expose their
source-issued DDL in a bounded read-only SQL panel. Download is a
source-declared catalog action over the checked nodes; there is no
adapter-specific button in a row or an open content panel.
A connection can be shared with a colleague at a level, and an administrator
manages accounts on a page of their own. Light and dark themes,
switched by a button beside Sign out and remembered.

The visible page of any tabular source can open as a chart beside its rows.
The chart keeps that page's request and visible columns, offers line, bar and
pie views, and derives a deterministic first choice without sending samples
outside the browser.

File upload presents its file field without opening the native picker on its
own, and choosing stages files instead of sending them: the dialog lists what
was chosen, any row can be taken out again, and the action's own button starts
the upload. Several files at once where the action says it takes them, one
request each; what arrives leaves the list and what is refused stays in it.
Only after a file is chosen can a name conflict be meaningful, so that refusal
offers Replace and Keep both; the latter uses the source-issued numbered name. Rename starts from the existing node name, omits a file
extension while editing, keeps the old extension when none is typed and
confirms an explicit extension change. Renaming a database relation starts
from its current name as well. A destructive catalog action asks one plain
question that names its target; it carries no separate warning banner.

```
frontend/public/
└── icons/services/      the logo of a source type, one SVG per type

frontend/src/
├── client/              generated from OpenAPI, never edited by hand
├── shared/
│   ├── ui/              the component kit every screen is built from;
│   │                    tokens.ts turns meaning into Quasar props,
│   │                    theme.css turns meaning into colours in both themes,
│   │                    metrics.css names shared density and geometry,
│   │                    layers.css turns meaning into stacking order,
│   │                    useToast and useConfirm replace $q,
│   │                    index.ts is the one import path
│   ├── api/             client setup, and one reading of an API error
│   ├── auth/            the session, watched across tabs
│   ├── SchemaForm/      JSON Schema to form, framework-independent core;
│   │                    a field says which tab and which row it belongs to,
│   │                    and readSchema tells a plain schema from a union
│   ├── windows/         floating windows and shared question/delete presets
│   │                    — see workspace.md
│   ├── workspace/       the panel engine — see workspace.md
│   └── testing/         helpers for tests, not shipped by any screen
├── stores/              Pinia: client-side state only — the session, the theme,
│                        and what the last connection check said
└── features/
    ├── admin/           the accounts page; users.ts is the form, as plain
    │                    functions
    ├── auth/
    ├── catalog/         the list of one level and the menu of what the ticked
    │                    nodes admit, including source-owned download;
    │                    nodes.ts and actions.ts are pure mappers,
    │                    and nodes.ts holds the
    │                    table that says what a kind of node does;
    │                    useCatalogLevel.ts walks a catalog outside any component
    ├── charts/          closed line, bar and pie views over one bounded page;
    │                    pure builders and suggestions stay outside components
    ├── content/         source editing, bounded native content and read-only SQL,
    │                    the rendered document, and the verified binary viewers:
    │                    an image,
    │                    a player over the ranged stream, and a PDF the
    │                    application draws itself
    ├── grid/            the controlled data explorer: query state, filter and
    │                    sort editors, column layout, selection, clipboard,
    │                    typed renderers and the full-value viewer
    ├── structure/       a relation model in its own tab: columns, ordered
    │                    constraints and indexes; model.ts maps them to badges,
    │                    and source-owned type choices drive column DDL
    ├── connectors/      the list of sources, the catalog of source types that
    │                    starts a new one, and the window that registers one;
    │                    adapterSearch.ts is a pure mapper and access.ts is the
    │                    scale of what a caller may do
    ├── shares/          a link to a view, who may follow it and who is waiting
    │                    to — see sharing.md
    ├── workspace/       the panels and their roles — see workspace.md
    └── dev/             /ui-kit and /workspace-demo, dev builds only
```

## D6. Server state lives in vue-query; Pinia holds only client state

The old frontend spread server data across Pinia stores, each with its own cache
and its own invalidation, and that is where its desynchronisation bugs come from.

Enforced by ESLint: `src/stores/**` may not import the generated client or any
feature.

A failed query is asked again only when asking again could answer differently.
vue-query retries everything three times with a growing gap, which is right for
a request that never arrived and wrong for one the server read and refused:
4xx, minus the two codes that are about the moment, is the server saying
something about the request, and it will say it again. Opening a `.dump` in a
file source waited about five seconds to say it is binary, and every second of
it was this.

Spec: [The connector registry and the adapter contract](../superpowers/specs/2026-08-15-connector-registry-design.md)

## D7. The frontend is Vue 3 with Quasar

The value of the rewrite is backend architecture and end-to-end typing; the UI
kit was never the problem. The typed client generated from OpenAPI is kept — it
does not depend on the framework.

Spec: [The connector registry and the adapter contract](../superpowers/specs/2026-08-15-connector-registry-design.md)

## D11. A screen asks the kit for meaning, not Quasar for a look

Every component with a choice of appearance is wrapped once in `shared/ui`, and a
screen says `variant="danger"` rather than `flat color="negative"`. `tokens.ts`
is the only place that turns one into the other, and it is plain functions, so
the mapping is tested without mounting anything.

It is not a facade over Quasar: what has no choice of appearance (`q-icon`,
`q-separator`, `q-td`, `q-form`) and what has one consumer (`q-layout`, `q-tree`)
stays as it is. Undeclared attributes fall through, so a rare case does not force
a change to the kit, and `data-testid` keeps landing where Quasar puts it.

Consequences:

- **A colour is a meaning too, and `theme.css` is where it is spent.** A screen
  carries `var(--dp-hover)`, never `rgba(0, 0, 0, 0.04)`. That file declares the
  light values on `:root` and redeclares them under `body.body--dark`, which is
  what makes a theme switchable at all — a Sass variable is settled at build
  time. `stores/theme.ts` is the only caller of Quasar's Dark plugin.
- **A layer is a meaning too, and `layers.css` is where it is spent.** A screen
  carries `var(--dp-layer-overlay)`, never `2`. A number decided alone cannot be
  compared with another without opening both files, which is how a floating
  window came to be painted over by a sticky table heading that declared `1`, and
  how the drop zone of the workspace lost to the same heading afterwards. Two of
  the values are Quasar's: its header and footer sit at 2000 and its menus and
  dialogs at 6000, so anything of ours that must clear the first and stay under
  the second is placed between them.
- **Density and geometry are shared too.** `metrics.css` names the application
  header, status line, tab strip, workspace inset, spacing and radii. A feature
  may arrange its own content, but it does not invent another height for the
  same kind of toolbar or another almost-equal panel corner. A button belonging
  beside one of the kit's fields goes through its `after` slot: the field kit
  then aligns it with the control rather than with the extra line reserved
  underneath for a validation message.
- **The rule is a lint rule, not a habit.** `vue/no-restricted-html-elements`
  forbids, outside `shared/ui`, exactly those `q-*` that have a replacement, in
  both spellings Vue accepts — matching only `q-btn` would let `<QBtn>` walk
  past. `useQuasar` is forbidden in screens too, now that `useToast` and
  `useConfirm` exist.
- **The kit documents itself at `/ui-kit`**, a route registered only under
  `import.meta.env.DEV`. It renders the real components, so it breaks when one of
  them does; a test compares the page against the files in `shared/ui` so a
  component cannot be added without a demonstration.
- **Reading an API error is one function.** `shared/api/errors.ts` — three
  screens had their own copy, and they had already drifted: only the grid
  understood a validation list.

A test reads every `.vue` under `src` and fails on a `z-index` that is not a
`--dp-layer-…` name. A `.css` file cannot be read from a unit test at all — Vite
hands back its name and an empty string — so the scale's own order is checked in
the browser by a Playwright scenario.

Known deviations:

- **Part of the kit has one consumer** (`AppBadge`, `AppFileInput`, `AppSpinner`,
  `AppTooltip`). A knowing departure from "generalise on the second or third
  use": the point of the kit is predictability as the number of screens grows.
- **Attribute fall-through is a way around the kit.** Nothing stops a screen
  passing `color="purple"` straight to the Quasar component underneath. Only
  review catches it.
- **`AppTree` is a wrapper over `q-tree`, not a tree of its own.** The types of
  its nodes and of a lazy load are read off Quasar's props, so replacing the tree
  would change what a screen passes it.
- **`AppTree` is in the kit and nothing uses it.** The catalog was its only
  consumer and is now a list. It stays because the kit is built as an alphabet,
  and it is still demonstrated at `/ui-kit`.
- **The theme does not follow the system.** The browser is asked once, when
  nothing has been chosen; after that the choice stands, and there is no way back
  to "as the system says" but clearing the stored value.
- **The theme is one per browser.** `localStorage`: it does not follow a user to
  another machine and is not shared between two windows.
- **The dark palette was picked, not derived.** The values under
  `body.body--dark` were chosen by eye against Quasar's own dark colours; nothing
  measures contrast against WCAG.

Spec: [The shared UI kit](../superpowers/specs/2026-08-22-shared-ui-kit-design.md)

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
request shows a skeleton, a subsequent request covers old rows with an overlay,
and failure removes them rather than presenting a previous page under a new
query.

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

Spec: [The data exploration grid](../superpowers/specs/2026-08-27-data-grid-design.md)

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

Spec: [A grid that re-reads itself](../superpowers/specs/2026-09-02-auto-refresh-design.md)

## D28. A download is a fresh copy of the bounded visible page, kept in personal storage

Download repeats the grid's current `FetchRequest`, including its bounded
limit, offset, filters and ordered sort, then writes only the columns visible
in the controlled layout, in their displayed order. It is available for every
source that can answer `SupportsFetch`: CSV is a representation of the common
table boundary rather than a source-specific adapter capability.

The server writes UTF-8 CSV to
`downloads/<connector-id>/<table>-<timestamp>.csv` inside the current user's
personal directory and returns that same file as the HTTP attachment. SQL null
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

Download now asks which of two honest scopes is meant. **Current page** is the
bounded operation above. **All matching rows** keeps the committed filters,
ordered sort and visible-column order but drops paging, and is enabled only
when the source implements D44's streaming export. Its finished personal file
is followed through a native browser download rather than an XHR Blob, so a
whole relation is not reassembled in browser memory.

Spec: [Downloading the visible page, and the commands of an open table](../superpowers/specs/2026-08-28-page-download-design.md)

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

Spec: [Charts over a bounded page](../superpowers/specs/2026-08-30-bounded-page-charts-design.md)

## Checking the types at all

`vue-tsc` has two ways of checking nothing while looking clean, and this project
has been bitten by both. Under the bun runtime it fails to register the `.vue`
extension, so every component drops out of the compiler program — measured: 4
files under Node, 0 under bun. On Windows the `.cmd` shim invokes Node, which
hides that half. The other half is configuration: `vue-tsc --noEmit` against
`tsconfig.json`, which lists project references and `"files": []`, reads no file
at all and exits 0. `type-check` therefore runs `vue-tsc -b --force`, under Node.

## D50. Markdown is rendered in the browser, and everything that becomes DOM is sanitised twice

`.md` and `.markdown` declare two representations under D47 — `markdown` first,
`text` second — so a document opens rendered and its source is one click away in
the editor D48 already provides. The server sends the document's text and
nothing else: no HTML crosses the API boundary and nothing is stored rendered.
The ceiling is 1 MB, between the 256 KB text preview and the 4 MB editor,
because a rendered document is parsed, tokenised and turned into DOM in the
browser. Above it the panel says it is showing the first megabyte.

The document is split at fence boundaries before it is parsed, so a `mermaid`,
`echarts` or `svg` fence never reaches the Markdown parser. Prose is rendered by
`markdown-it` with KaTeX and task lists, and sanitised at two levels that are
not duplicates: author-written raw HTML goes through DOMPurify at token level
with `style` forbidden, and the assembled result goes through it again keeping
inline `style` only inside `.katex`, whose layout depends on generated styles.
Links and images are then hardened. An `http(s)`, `mailto` or `tel` link opens
in a new window with `rel="noopener noreferrer"`, because a document lives
inside a panel and following a link in place would take the application with it;
an anchor is left alone; anything else — including every relative path — loses
its browser `href` or `src` and is marked for source-aware resolution after the
DOM is mounted. Images are lazy and send no referrer, and `iframe`, `object`, `embed`, `form`
and `button` cannot appear at all. SVG, including everything Mermaid draws under `securityLevel: "strict"`,
goes through the SVG profile with `script` and `foreignObject` forbidden.

**Remote resources are blocked by default and the block is visible.** A document
can arrive from somebody else's connection through a read grant (D33), and a
remote image in it is a read receipt for whoever hosts it. The reader did not
ask to send one.

Rich blocks are bounded and lazy: a fence over 250 000 characters is refused by
the block itself, and Mermaid, ECharts, SVG and code blocks mount through an
`IntersectionObserver` when they scroll into view, so a document of forty
diagrams costs one to open. Code fences reuse the CodeMirror of the editor in
read-only mode and resolve their language through the same `language.ts`, so
there is no second syntax highlighter in the bundle. Both take their colours
from `highlight.ts`, whose palette is theme tokens rather than CodeMirror's
built-in one — that default is a light-theme palette, and it was putting dark
purple keywords on a near-black ground in both places.

**A callout an agent wrote is a card.** A fence named `summary`, `warning`,
`decision`, `risk`, `file`, `verification`, `command`, `result` or `question`
— with or without a `callout:` prefix — is shown with that kind named, an icon,
and a colour that is the meaning rather than decoration; the leading run of
`Key: value` lines becomes a field list and the rest is Markdown. The convention
costs the document nothing: in any other tool the same fence is an ordinary code
block, which is why it is worth reading here.

**Every rich block wears the same frame.** `BlockChrome` gives a diagram, a
chart, a drawing and a listing one header: what the block is on the left, what
can be done with it on the right. The source of any of them goes to the
clipboard, anything drawn as SVG can be saved as a file, and an `svg` fence can
be read as its own source instead of its picture. Copying and saving go through
`shared/clipboard.ts` and `shared/download.ts`, the boundaries the application
already has.

Three things about drawing that were found by reading a real document rather
than by any test. **Mermaid is not re-entrant**: it renders through one shared
element and re-reads global configuration on every call, so diagrams drawn at
once take each other's output — ids and a queue therefore live in module scope,
in `mermaid.ts`. **Mermaid writes labels into a `foreignObject` of HTML** unless
told not to, and that element is forbidden for content nobody here wrote, so
`htmlLabels` is off and labels come back as native SVG text. **An ECharts option
naming a series this bundle does not carry is reported to the console and then
drawn as an empty box**, so the option is asked first and the series is named in
the block.

Two further corrections come from the same reading. Without HTML labels Mermaid
draws an opaque `rect.background` behind every edge label, so `yes` and `no` on
a flowchart arrived boxed; CSS scoped to the diagram's own id hides it, and
gives a subgraph frame this application's colours. And a document names a
chart's parts but rarely their geometry, while ECharts places each part
independently: a title and a legend both default to the top and overlap.
`normalizeLayout` stacks title, legend and plot in order and fills in only what
the document left unsaid.

The renderer is ported from `rich-md-viewer`, a standalone application by the
same author, on this repository's usual terms: its two-stage sanitisation,
fence splitting, remote-resource gating and block ceilings are the ideas worth
having. Its tabs, share links and i18n are not ported — the workspace and file
source already own those concerns. Its table of contents, visible-text search
and inert rendered export are now adapted to a panel rather than a page.

Relative document references do not weaken D21. The client never joins a path
to an id: it starts from the source-issued path of the open node, walks every
segment through the existing one-level catalog read and copies the node it
finds. A link opens that node's preferred declared representation, while an
image additionally has to declare `image` and then travels through D49's
verified preview ticket. Resolution is lazy near the viewport; HTML/PDF export
resolves every local image, embeds its bytes, removes viewer controls and
search marks, and exports no script. A cross-document fragment is a one-shot
workspace target consumed after the destination document renders.

Progressive rendering by token batch and embeds remain out. The 1 MB document
ceiling bounds parsing for now, and an explicitly allowed remote image remains
an external reference in an export rather than being fetched a second time.

Spec: [Markdown as a rendered document representation](../superpowers/specs/2026-08-31-markdown-document-representation-design.md)

## Screens

The catalog is a list of one level: a click opens what can be read and walks into
what cannot, a tick box picks a node out without opening it, the way back is the
first row, and the path above it starts at a home button. One menu in the head
carries everything the source can do, live for what is ticked and greyed out for
the rest — standing in a folder is not choosing it. What that menu offers comes
from the server; see D9 in [sources/actions.md](sources/actions.md).

A connection is a row of two things: the icon of its type, with the dot of the
last check standing on it, and its name. Everything else about it lives in the
window that icon opens.

**What a screen may offer, it is told.** A connection carries `access`, so the
window of one that belongs to somebody else shows its options disabled, names
who shared it, and drops Apply, Delete and Share; sharing is offered only to
the owner. Nothing below that is decided here — a page that may not be edited
arrives with its columns marked uneditable, and a relation whose shape is not
the caller's arrives saying so, both through the fields those screens already
read. The one comparison the client makes is `atLeast` in
`features/connectors/access.ts`, and its scale is read off the generated client
rather than written out again. See D33 in [backend.md](backend.md).

Accounts are a page of their own at `/users`, opened from a header button that
appears only for an administrator. It creates people, switches them off and
removes them, and it decides nothing about data (D34). The form rules —
a password required when there is no account and optional when there is — are
plain functions in `features/admin/users.ts`.

The catalog opens on the grouping the source named, if it named one: a Redis
connection is written with a database number in it, and only the source has
read it. Otherwise on every grouping the source calls its own while there are
few of them, and on the first while there are many. A database with two or
three schemas is one where a person wants to see what is in it — a server this
application started has `public` and the demonstration schema, and opening
only the empty one of the two shows nothing — while a database with forty is
one where opening them all is a page nobody asked for. The ceiling is
`DEFAULT_GROUP_CEILING` in `useCatalogLevel.ts`.

What the groupings are called above that control — Schemas, Databases — is a
table keyed by the kind of the node, in `nodes.ts` beside the roles and the
icons. A screen that asked which type of source it was looking at is the thing
that table exists to prevent.

A form field is drawn from what the schema says about it and nothing else: a
value written on several lines asks for a box rather than a line
(`x-ui-multiline`, set by `layout()` where the field is declared), the
sentence under a field is the source's own `description`, and the shape of a
filled field is its `examples` — JSON Schema's own keyword — shown inside the
empty control and gone the moment anything is typed. All three are statements
only the model can make: the type is `string` either way, and "one per line,
as field=value" is a fact about a Redis hash. A field carrying an example
keeps its label above the box, because Quasar hides a placeholder until the
label floats and a floating label sits exactly where the example would be. A
toggle has no line under it, its label being the whole statement, and a select
shows no example, its list being one.

Known deviations:

- **The ceiling on opened groupings is a number, not a measurement.** Five was
  chosen for the shape of the two cases; nobody has looked at what a database
  with six schemas feels like.
- **Where one was in a catalog is not remembered.** The layout survives a reload;
  the path inside a catalog does not, so a reloaded page is back at the root.
- **The name of a row loses to its captions in a narrow column.** With several
  groupings on, the row carries the name of its grouping and its size or row
  estimate, and the name is elided first. Resizable columns are the only answer
  today.
- **A row of the list carries four marks.** The icon, the name, the state dot on
  that icon and the highlight that says it is open. On a long list with several
  catalogs open the column becomes busy, and nobody has measured that.
- **The two states of the connections column agree by arithmetic, not by
  construction.** The wide list pads by four pixels because that is where a
  forty-pixel strip centres a thirty-two pixel button. Change the size of the
  button and the two drift apart; a scenario measures both and fails when they
  do.
- **A revoked grant is noticed when something is asked.** The connection stays
  on the colleague's screen until the list is read again; the socket says
  nothing about a level being taken away. Every route refuses in the meantime,
  so nothing is reachable — only the row is stale.
- **The state dot only knows about this session.** A connection shows grey until
  the user checks it; nothing checks in the background, because that would mean
  opening a connection to every source on every load. The record is not
  persisted: a dot restored from yesterday would claim more than it knows.
