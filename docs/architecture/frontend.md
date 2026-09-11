# Frontend

How a screen is built, where state lives, and what the component kit is. The
panel engine, the layout and floating windows are in
[workspace.md](workspace.md); the grid, its downloads and its charts are in
[grid.md](grid.md). Domain-independent 2D and 3D graph viewers are described in
[graphs.md](graphs.md).

Decisions here: D6, D7, D11, D50, D99.

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
manages accounts on a page of their own. The user icon at the right of the
header opens an account menu with Sign out and, for administrators, Admin.
Light and dark themes are switched by the adjacent button and remembered.

The application uses the legacy cube artwork: blue for the browser favicon
and the light header, white for the dark header.

Detected frameworks appear below the catalog filter for the selected schemas.
Every match is shown once; clicking its label fills the filter with the
source-issued table pattern, and clicking the active label clears it. The
labels come from schema metadata, so filtering the rows does not hide them
([D98](sources/contract.md#d98-framework-detection-belongs-to-the-schemas-catalog-metadata)).

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
│   ├── auth/            the current account and session, watched across tabs
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

## D99. A browser tab belongs to one backend context

The configured default and named server profiles are selectable before login
and from the footer. Profiles are shared in browser storage; the selection is
per browser tab. Changing servers performs a guarded full navigation, leaving
old requests and sockets in the old document. Editing a saved address never
retargets another running tab.

The canonical installation URL identifies a server. HTTP, WebSocket, download
and media URLs use it, including any deployment prefix. Tokens, workspace
layouts, source histories, grid/chart/graph state and query drafts are separated
by server. Legacy keys are pinned once to the original default server; a later
default change cannot inherit that server's credentials. Theme remains shared.

The public `/api/v1/utils/server-info` endpoint identifies the product and API
generation. A separate anonymous client checks a candidate before connecting;
login also checks compatibility. An unknown backend in a shared link requires
explicit selection. Old links belong to the configured default server.

Panel and window close guards run before switching. Server-owned work stays on
its server; unsaved editor changes and transactions are handled before leaving.
The server must allow the frontend origin through CORS and support the browser's
HTTP(S)/WebSocket transport requirements.

Spec: [Choosing a DataPlayer server](../decisions/2026-09-04-server-profiles-design.md)

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

Spec: [The connector registry and the adapter contract](../decisions/2026-08-15-connector-registry-design.md)

## D7. The frontend is Vue 3 with Quasar

The value of the rewrite is backend architecture and end-to-end typing; the UI
kit was never the problem. The typed client generated from OpenAPI is kept — it
does not depend on the framework.

Spec: [The connector registry and the adapter contract](../decisions/2026-08-15-connector-registry-design.md)

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
  `AppSelect` clips its append area so the rotating dropdown arrow cannot
  temporarily widen a scrollable toolbar. The teleported options remain outside
  that clipping boundary.
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

Spec: [The shared UI kit](../decisions/2026-08-22-shared-ui-kit-design.md)

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

Spec: [Markdown as a rendered document representation](../decisions/2026-08-31-markdown-document-representation-design.md)

## Screens

The catalog is a list of one level: a click opens what can be read and walks into
what cannot, a tick box picks a node out without opening it, the way back is the
first row, and the path above it starts at a home button and ends at a compact
copy button at the right edge. The copy button appears while the path is hovered
or contains keyboard focus; its space stays reserved so the path does not move.
What it copies is the level's own id written from the
root — for a file source, `/reports/2026`: the trail is labels for a reader,
and the id is the string that names the place. The root itself is `/` and is
copied like any other level; the server is never named, because what is copied
begins where the connection does, and `/` is also what its owner would type
into the folder of a connection. One menu in the head
carries everything the source can do, live for what is ticked and greyed out for
the rest — standing in a folder is not choosing it. What that menu offers comes
from the server; see D9 in [sources/actions.md](sources/actions.md).

A level's rows share one set of columns: the tick box, the icon, the name, the
grouping a row came from, where a search found it, and what it measures. A row
takes those columns rather than laying itself out again, so a name stands under
a name and a count under a count. The exception is a report: its caption is the
sentence the source wrote about what its statement answers, and in the shared
column that sentence would set the column's width for every row in the list. So
a report lays itself out, and ends its sentence where the other rows end their
measurements: beside the name it read as a second half of the name, and a line
about what a report answers is an aside, not part of what the row is called.
It gives that room up before the name does, so a narrow panel cuts the aside.
The scrolling list reserves a scrollbar gutter and a small trailing inset so
its final column stays readable beside classic and overlay scrollbars.

The icon of a row is also where its name is copied from: under the pointer, or
while the button has focus, it gives way to a copy button of exactly its size.
A gesture wanted only on the row being looked at costs no column, and nothing
on the line moves when the pointer arrives.

A kind is said by the icon and never also in words, so a materialized view is
drawn as the table it keeps rather than labelled. What a relation measures is
always said: a table with an estimate says it, and a table nobody has analysed
and a view, which stores no rows to count, both say `N/A` with a hint saying
which of the two reasons applies. A column filled on some rows and blank on
others reads as one somebody forgot rather than as a count nobody has.

The catalog's filter and search field keeps the ten most recent distinct,
non-empty queries per account and connector in this browser's local storage.
Enter, a search, or leaving an edited field remembers its trimmed text; merely
typing does not add partial queries. Reusing a query moves it to the front.
Focusing or clicking the field opens the saved text directly below it, with a
removal cross beside each entry. The popup leaves keyboard focus in the field
so typing can continue; Escape, Tab, or clicking outside closes it. An empty
history shows no popup. Selecting one returns to the current level and applies
the text as a filter; recursive and content searches still require their usual explicit
gesture. Removing an entry leaves the current filter alone and does not
restore it on blur unless the text is edited again. History stays local to
the session if browser storage cannot be written.

A connection is a row of two things: the icon of its type, with the dot of the
last check standing on it, and its name. Everything else about it lives in the
window that icon opens.

The catalog's **Connect folder** action opens that same form for a new
connection, with the folder name and path supplied by the source. These are
editable initial values, not a saved connector or unsaved user changes.
Cancel leaves the connector list and files alone; Save or Apply follows the
ordinary creation flow, including the tab color and access settings.

The name field in the connection window has a rainbow color picker. Its
optional tab color is connector metadata, saved by the owner with Apply or OK;
Reset color clears it. A draft choice stays in the form until saved. Every
workspace tab belonging to that connection reads the current saved color,
including catalogs, data, query consoles and captured results. Text uses
whichever of black or white has higher contrast. A tab is the same shape either
way: filled, one font weight, and a line under the one being read. A connection
with no color of its own is filled with `--dp-panel-plain`, so whether somebody
chose a color is not something the size or form of a tab says.

The connections column carries the same color. A row whose catalog is being
read is marked in it whole, and one merely open somewhere in a wash of it. A
connection with no color is marked just the same, in `--dp-panel-plain` — the
same fill its tabs carry, so the default is a color rather than the absence of
one — and in `--dp-panel-plain-quiet`, which is half a step from that fill
towards the surface rather than a wash of it, because the plain fill is already
close to the surface it is laid on. The pointer over a row lays the hover wash
on top of whatever fills it instead of replacing it, so arriving at a row does
not take its color away. The strip a collapsed column leaves behind marks its
icons the same way.

The catalog carries the color for one mark only: the outline that points at a
row after the icon of a table's tab was pressed. That mark is the far end of a
gesture whose near end is a tab, so it is drawn in whatever that tab is drawn
in — the connection's color, or `--dp-panel-plain` where none was chosen.
Everything else in a catalog — a ticked row, a row under the pointer — keeps
the theme's, because a tick is about an action and not about which connection
this is. `connectorColorOf` reads the color out of the list of connections by
id, so saving or resetting one reaches a catalog already open.

Known deviation: with no color chosen the outline is that plain fill, which is
a step from the surface it is drawn on and so barely visible — asked for
deliberately, so that the mark says nothing the tab does not.
`shared/ui/panelColor.ts` turns one chosen color into the fill, the text color
that stays readable on it, and the wash, so nothing mixes a color of its own.

### Taking the connection colors back out

Everything above that carries a connection's color beyond its own tabs — the
marked rows in the connections column and in the strip a collapsed column
leaves behind, the plain fill that stands in where nobody chose a color, and
the outline that points at a row in a catalog — is one commit, "Mark a
connection in its own colour where it is listed" (`git log --grep "in its own
colour"`). Reverting it puts the screens back and leaves the tabs and the color
picker untouched. It is one commit for that reason and not because it was
written in one sitting.

By hand, if only part of it is to go, each place falls back to what the theme
already had:

| Place | What to take out | What it falls back to |
| --- | --- | --- |
| `shared/ui/theme.css` | `--dp-panel-plain` and `--dp-panel-plain-quiet`, from both the light and the dark block | — |
| `shared/workspace/WorkspaceLeaf.vue` | the plain fill in `.workspace-leaf__tab` | `var(--dp-surface)`, which is what it was |
| `features/connectors/ConnectorList.vue` | the `panelColorStyle` binding on the row, and the color in the two marks | `var(--dp-selected-quiet)` and `var(--dp-selected)` |
| `features/workspace/panels/ConnectorRail.vue` | the same two | the same two |
| `features/catalog/CatalogList.vue` | the color in `.catalog-list__row--revealed` | `var(--dp-focus-border)` |
| `features/workspace/panels/CatalogPanel.vue` | `color`, its query and the style it binds | nothing; the list stops carrying a color |
| `features/connectors/api.ts` | `connectorColorOf`, and its case in the spec | — |
| `shared/ui/panelColor.ts` | `--dp-panel-quiet`, and its column in the spec | — |

Two things are deliberately not on that list, because they are not about color.
The hover wash in the connections column is laid over the row as an inset
shadow rather than as a background; a row is filled by whichever mark it
carries, so that stays whatever the row is filled with. And a tab is filled
whether or not a color was chosen, one weight, marked by a line under it — that
is the shape of a tab (in the commit before this one), not the color of one.

Tests to drop with it: the color assertions in `frontend/tests/connectors.spec.ts`
and the cases named above in the two unit specs.

**What a screen may offer, it is told.** A connection carries `access`, so the
window of one that belongs to somebody else shows its options disabled, names
who shared it, and drops Apply, Delete and Share; sharing is offered only to
the owner. Nothing below that is decided here — a page that may not be edited
arrives with its columns marked uneditable, and a relation whose shape is not
the caller's arrives saying so, both through the fields those screens already
read. The one comparison the client makes is `atLeast` in
`features/connectors/access.ts`, and its scale is read off the generated client
rather than written out again. See D33 in [backend.md](backend.md).

Administering the installation is a page of its own at `/admin/<section>`,
opened from the header's user menu, where Admin appears only for an
administrator. It is a list of sections beside what one of them shows, and
there is one section today: accounts. The shape says so honestly — what comes next arrives as an
entry in `features/admin/sections.ts` and a line in the page's table, rather
than as a rearrangement of a screen built around exactly one thing. The
section is in the address, so a link into one is a link; an address naming
none opens the first, and `/users` still redirects to where accounts moved.

The accounts section creates people, switches them off and removes them, and
it decides nothing about data (D34). The form rules — a password required when
there is no account and optional when there is — are plain functions in
`features/admin/users.ts`.

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
- **The name of a row loses to the columns beside it in a narrow panel.** The
  grouping and the measurement each take the width of the widest of them in the
  level, and the name is what shrinks, down to five characters. With
  `information_schema` among the groupings on, that costs a name a third of the
  column. Resizable columns are the only answer today.
- **Every row carries the copy button, drawn or not.** The list is not
  virtualised, so a schema of five thousand tables mounts five thousand
  buttons and their tooltips beside the five thousand tick boxes it already
  mounted. Drawing one button and moving it to the row under the pointer would
  cost the keyboard its way to the gesture; virtualising the list would cost
  neither, and is the answer when the list gets one.
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

The table designer follows the
[Variant B reference](../decisions/assets/2026-09-06-table-designer/variant-b.html)
for its arrangement: a narrow object navigation, an inspector, and an SQL
preview beside them, with creation review replacing the definition. The
breakpoints follow the floating window's width through a container query. Its
appearance is the application's own — the kit's controls as they come, colours
from the theme tokens, no type sizes of its own — because a visual pass over
the whole application comes after its behaviour is finished.

Conditions appear as read-only fields and expand into the typed editor on click
or Enter. The labels are presentation only and are never submitted as SQL.
Tablespace and owner retain their places from the reference but are disabled:
the creation API currently accepts neither option.
