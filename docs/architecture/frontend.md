# Frontend

How a screen is built, where state lives, and what the component kit is. The
panel engine, the layout and floating windows are in
[workspace.md](workspace.md); the grid, its downloads and its charts are in
[grid.md](grid.md); 2D and 3D graph viewers are in [graphs.md](graphs.md).

Decisions here: D6, D7, D11, D50, D99, D131.

## D131. Window forms use neutral surfaces and restrained borders

Agreed direction; implementation pending. Use grey surfaces, a distinct title
bar, compact fields with persistent left-aligned labels, and spacing rather
than nested cards to group content. Borders belong mainly to inputs and the
window; quiet separators distinguish major regions. Avoid blue-tinted chrome
and decorative accent stripes. Reflow labels above fields at narrow widths.
Shared UI tokens and components own the appearance; Quasar remains the base.
The spec includes the accepted visual example and rejected directions.

Spec: [Neutral window design and stable sizing](../decisions/2026-09-13-window-design-and-sizing.md)

## What exists today

Vue 3, TypeScript, Quasar, Vite, TanStack Query, Pinia. What the application
already does is recorded by the spec index and by git; this file keeps what
shapes the code of a screen.

```
frontend/public/icons/services/   the logo of a source type, one SVG per type

frontend/src/
├── client/              generated from OpenAPI, never edited by hand
├── shared/
│   ├── ui/              the component kit; tokens.ts, theme.css, metrics.css
│   │                    and layers.css turn meaning into props, colours,
│   │                    geometry and stacking; index.ts is the one import path
│   ├── api/             client setup, and one reading of an API error
│   ├── auth/            the current account and session, watched across tabs
│   ├── SchemaForm/      JSON Schema to form, framework-independent core
│   ├── windows/         floating windows — see workspace.md
│   ├── workspace/       the panel engine — see workspace.md
│   └── testing/         helpers for tests, not shipped by any screen
├── stores/              Pinia: client-side state only
└── features/
    ├── admin/           the administration page; users.ts is the account form
    ├── auth/
    ├── preferences/     what an account chose; checks.ts words a server-owned set
    ├── catalog/         the list of one level and the menu of what ticked nodes
    │                    admit; nodes.ts says what a kind of node does
    ├── charts/          line, bar and pie views over one bounded page
    ├── content/         source editing, rendered documents, verified viewers
    ├── grid/            the data explorer — see grid.md
    ├── structure/       a relation's columns, constraints and indexes
    ├── connectors/      the list of sources, source types, the connection window
    ├── shares/          links and access requests — see sharing.md
    ├── workspace/       panels and their roles; panels.ts is that table
    ├── dashboards/      the space that covers the workspace — see dashboards.md
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
The server must allow the frontend origin through CORS.

Spec: [Choosing a DataPlayer server](../decisions/2026-09-04-server-profiles-design.md)

## D6. Server state lives in vue-query; Pinia holds only client state

The old frontend spread server data across Pinia stores, each with its own cache
and its own invalidation, and that is where its desynchronisation bugs came from.

Enforced by ESLint: `src/stores/**` may not import the generated client or any
feature.

A failed query is asked again only when asking again could answer differently.
vue-query's three growing retries suit a request that never arrived, not a 4xx
the server read and will refuse again — minus the two codes that are about the
moment. Opening a `.dump` in a file source once waited five seconds for that.
A source failure is a 502 whatever it was, so its kind decides: `auth`,
`config` and `locked` are settled, and a locked SSH key once held a spinner
over its own unlock button for seven seconds.

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

- **A colour is spent in `theme.css`.** A screen carries `var(--dp-hover)`,
  never `rgba(0, 0, 0, 0.04)`. Light values sit on `:root` and are redeclared
  under `body.body--dark`, which a Sass variable, settled at build time, could
  not do. `stores/theme.ts` is the only caller of Quasar's Dark plugin.
- **A layer is spent in `layers.css`.** A screen carries
  `var(--dp-layer-overlay)`, never `2`: two numbers decided alone cannot be
  compared, which is how a sticky table heading declaring `1` painted over a
  floating window and then over the workspace drop zone. Quasar's header and
  footer sit at 2000 and its menus and dialogs at 6000, so anything that must
  clear the first and stay under the second is placed between them.
- **Density and geometry are spent in `metrics.css`**: header, status line, tab
  strip, insets, spacing and radii. A feature arranges its own content but does
  not invent another toolbar height or panel corner. A button beside a kit field
  goes in its `after` slot, which aligns it with the control rather than with the
  line reserved for a validation message. `AppSelect` clips its append area so
  the rotating arrow cannot widen a scrollable toolbar; its teleported options
  stay outside the clip.
- **A card is one look.** A Data section, the dashboards rail and dashboard,
  a widget, the chats and a chat are `AppCardFrame` with an `AppCardHead`:
  one frame, and a head of the tab strip's height on `--dp-card-head` in
  every state, empty or loading included. A collapsed rail keeps the head with
  its plus alone in it — the connections, the dashboards, the chats — so the
  strip runs unbroken across the screen. `WorkspaceLeaf` draws the same frame and
  head from the same tokens, because its root is the engine's.
- **Button layout belongs to the kit.** `toolbar` keeps an icon and label on one
  line, `navigation` aligns an entry to the left, and `AppTree` owns the full-row
  selection mark. Screens size fields through their own classes on kit
  components, never by selecting Quasar internals.
- **Flat action text has theme colours of its own.** `secondary` and
  `danger-quiet`, icon buttons included, use `--dp-action-secondary` and
  `--dp-action-danger`, lighter in the dark theme than the filled `primary` and
  `danger`.
- **Shadows and paper are theme tokens too.** Activity sheets and notification
  cards use the soft shadow, PDF pages the strong one; PDF paper and selection
  colours are the same in both themes, because the document does not change
  palette with the application.
- **The rule is a lint rule, not a habit.** `vue/no-restricted-html-elements`
  forbids, outside `shared/ui`, exactly those `q-*` that have a replacement, in
  both spellings Vue accepts — matching only `q-btn` would let `<QBtn>` walk
  past. `useQuasar` is forbidden in screens; `useToast` and `useConfirm` replace
  it.
- **An icon button's tooltip is its accessible name** in every state, unless the
  caller passes its own `aria-label`.
- **The kit documents itself at `/ui-kit`**, a route registered only under
  `import.meta.env.DEV`. It renders the real components, and a test compares the
  page against the files in `shared/ui`, so a component cannot be added without
  a demonstration.
- **Reading an API error is one function**, `shared/api/errors.ts`.

A test reads every `.vue` under `src` and fails on a `z-index` that is not a
`--dp-layer-…` name. A `.css` file cannot be read from a unit test — Vite hands
back its name and an empty string — so the scale's own order is checked by a
Playwright scenario.

Known deviations:

- **Part of the kit has one consumer or none** (`AppBadge`, `AppFileInput`,
  `AppSpinner`, `AppTooltip`; `AppTree` since the catalog became a list). A
  knowing departure from "generalise on the second use": the kit is built as an
  alphabet, for predictability as screens grow.
- **Attribute fall-through is a way around the kit.** Nothing stops a screen
  passing `color="purple"` to the Quasar component underneath; only review does.
- **`AppTree` wraps `q-tree`.** Its node and lazy-load types are read off
  Quasar's props, so replacing the tree would change what a screen passes it.
- **The theme is chosen once per browser.** Light, Dark or System; System is
  what nothing stored means and follows the operating system as it changes.
  The choice does not follow a user elsewhere.
- **The dark palette was picked by eye**, against Quasar's dark colours; nothing
  measures contrast against WCAG.

Spec: [The shared UI kit](../decisions/2026-08-22-shared-ui-kit-design.md)

## Checking the types at all

`vue-tsc` has two ways of checking nothing while looking clean. Under the bun
runtime it fails to register the `.vue` extension, so every component drops out
of the program (4 files under Node, 0 under bun); on Windows the `.cmd` shim
invokes Node and hides it. And `vue-tsc --noEmit` against `tsconfig.json`, which
lists project references and `"files": []`, reads no file and exits 0.
`type-check` therefore runs `vue-tsc -b --force`, under Node.

## D50. Markdown is rendered in the browser, and everything that becomes DOM is sanitised twice

`.md` and `.markdown` declare two representations under D47 — `markdown` first,
`text` second — so a document opens rendered and its source is one click away.
The server sends the text and nothing else: no HTML crosses the API boundary and
nothing is stored rendered. The ceiling is 1 MB, because a rendered document is
parsed and turned into DOM in the browser; above it the panel says it shows the
first megabyte.

The document is split at fence boundaries first, so a `mermaid`, `echarts` or
`svg` fence never reaches the Markdown parser. Prose is rendered by
`markdown-it` with KaTeX and task lists and sanitised at two levels that are not
duplicates: author-written raw HTML goes through DOMPurify at token level with
`style` forbidden, and the assembled result goes through it again, keeping
inline `style` only inside `.katex`. An `http(s)`, `mailto` or `tel` link opens
in a new window with `rel="noopener noreferrer"`, because following it in place
would take the application with it; an anchor is left alone; anything else
loses its `href` or `src` and is resolved against the source after mounting.
Images are lazy and send no referrer; `iframe`, `object`, `embed`, `form` and
`button` cannot appear. SVG, including Mermaid's under `securityLevel:
"strict"`, goes through the SVG profile with `script` and `foreignObject`
forbidden.

**Remote resources are blocked by default and the block is visible.** A document
can arrive from somebody else's connection through a read grant (D33), and a
remote image in it is a read receipt for whoever hosts it.

Rich blocks are bounded and lazy: a fence over 250 000 characters is refused, and
diagrams, charts, SVG and code mount through an `IntersectionObserver`. Code
fences reuse the editor's CodeMirror read-only and its `language.ts`, and both
take colours from `highlight.ts`, whose palette is theme tokens — CodeMirror's
default put dark purple keywords on a near-black ground. A fence named
`summary`, `warning`, `decision`, `risk`, `file`, `verification`, `command`,
`result` or `question` (optionally prefixed `callout:`) is a card with its kind,
an icon and a field list from leading `Key: value` lines; anywhere else it stays
an ordinary code block. `BlockChrome` gives every rich block one header: what it
is on the left, copy and save on the right, through `shared/clipboard.ts` and
`shared/download.ts`.

Traps found by reading real documents:

- **Mermaid is not re-entrant.** It renders through one shared element and
  re-reads global configuration on every call, so ids and a queue live in module
  scope in `mermaid.ts`.
- **Mermaid writes labels into a `foreignObject`** unless `htmlLabels` is off,
  and that element is forbidden here. Without HTML labels it boxes every edge
  label in `rect.background`, which CSS scoped to the diagram hides.
- **ECharts draws an empty box for a series this bundle lacks**, so the option is
  asked first and the series is named in the block. Title and legend both default
  to the top; `normalizeLayout` stacks them and fills in only what was unsaid.

The renderer takes its ideas — two-stage sanitisation, fence splitting,
remote-resource gating, block ceilings — from `rich-md-viewer`, a standalone
application by the same author; its tabs, share links and i18n are not ported.

Relative document references do not weaken D21. The client never joins a path
to an id: it walks every segment from the open node's source-issued path through
the one-level catalog read and copies the node it finds. A link opens that
node's preferred representation; an image must also declare `image` and travels
through D49's verified preview ticket. HTML/PDF export embeds every local image,
removes viewer controls and exports no script. Progressive rendering and embeds
remain out, and an allowed remote image stays an external reference in an
export.

Spec: [Markdown as a rendered document representation](../decisions/2026-08-31-markdown-document-representation-design.md)

## Screens

Behaviour a screen owns and a later change could quietly undo.

**Application shell.** The header, footer and narrow side rails share one
chrome background, including the gaps between workspace panels. The header
carries no application name: it opens with the page's own leading control —
on the workspace, one button that collapses the first panel of the space
being shown (the leftmost data column, the dashboards rail, or the
chat-history rail), each of which owns its collapsed state. That first
section keeps no chevron of its own; the rest keep theirs. Workspace
panels meet the shell directly with their own rounded corners: no enclosing
border or outer padding surrounds the collection. Ordinary pages retain a
rounded surface and document scrolling; filling workspaces scroll internally.
Rail width and corner radii live in `metrics.css`; the rails contain no commands.

**Catalog.** A list of one level: a click opens what can be read and walks into
what cannot, a tick box picks a node without opening it, the first row goes back,
and the path above starts at a home button. The path's copy button copies the
level's own id from the root (`/reports/2026`; the root is `/`), never the
server. One menu in the head carries everything the source can do, live for what
is ticked and greyed for the rest; see D9 in [sources/actions.md](sources/actions.md).
Download and every other action come from there — no screen has an
adapter-specific button. A destructive action asks one plain question naming its
target.

Rows share one set of columns — tick box, icon, name, grouping, search location,
measurement — so a name stands under a name. A report is the exception: its
caption would set the column width for every row, so it lays itself out and
gives its room up before the name does. A row's icon turns into a copy button of
the same size under the pointer or focus. A kind is said by the icon and never in
words; a Timescale hypertable or continuous aggregate carries the extension's
mark. What a relation measures is always said: an estimate, or `N/A` with a hint
saying whether nobody analysed the table or it is a view.

The catalog opens on the grouping the source named; otherwise on all of the
source's own groupings while there are few, and on the first while there are
many (`DEFAULT_GROUP_CEILING` in `useCatalogLevel.ts`). What groupings are called
is a table keyed by node kind in `nodes.ts`, so no screen asks which source type
it is looking at. Detected frameworks appear below the filter as labels from
schema metadata, so filtering rows does not hide them
([D98](sources/contract.md#d98-framework-detection-belongs-to-the-schemas-catalog-metadata)).

The filter keeps the ten most recent distinct queries per account and connector
in local storage, remembered on Enter, search or leaving an edited field, never
while typing. Focus opens them under the field without taking focus from it;
choosing one returns to the current level and filters; removing one leaves the
current filter alone.

**Files.** Upload stages what was chosen and sends it only from the action's own
button, one request per file; a name conflict offers Replace and Keep both, the
latter under the source-issued numbered name. Rename hides a file extension while
editing, keeps it when none is typed and confirms a change. **Connect folder**
opens the connection form with editable values the source supplied.

**Connections.** A connection is a row of its type's icon, carrying the dot of
the last check, and its name; everything else lives in the window the icon opens.
A connection that belongs to somebody else arrives with `access`, so its window
shows options disabled, names who shared it and drops Apply, Delete and Share.
The one comparison the client makes is `atLeast` in `features/connectors/access.ts`,
whose scale is read off the generated client (D33 in [backend.md](backend.md)).

A connection's optional tab colour is saved by its owner. Every tab of that
connection is filled with it, text in whichever of black or white contrasts more;
a connection without one uses `--dp-panel-plain`, so a tab's shape never says
whether a colour was chosen. The connections column marks the row being read in
that colour whole and an open one in a wash of it; the hover wash is laid over
the fill, not instead of it. In a catalog the colour marks only the outline
pointing at a row after a table tab's icon was pressed. `connectorColorOf` reads
the colour from the connector list, and `shared/ui/panelColor.ts` is the only
place a colour becomes a fill, text and wash. Everything beyond the tabs is one
commit, "Mark a connection in its own colour where it is listed", so reverting it
takes the marks away and leaves tabs and the picker alone.

**Accounts and preferences.** Administration is `/admin/<section>`, from the user
menu and only for an administrator; sections are entries in
`features/admin/sections.ts`, and `/users` redirects to accounts. Accounts are
created, switched off and removed, and nothing about data is decided there (D34).
The account form asks for no autofill and marks Password `new-password`, with
persistent labels so filled values cannot overlap them. Sign-in reports missing
fields before sending and never trims a password. `/preferences` is for everybody:
one row per preference, saved as it changes. Connection check frequency is the
first (D19); `features/preferences/checks.ts` holds only the wording of the
server's closed set, as a complete record, so a new choice is a type error.

**Forms.** A field is drawn from what its schema says: `x-ui-multiline` asks for a
box, `description` is the sentence under it, and `examples` is shown inside the
empty control. A field with an example keeps its label above the box, because
Quasar hides a placeholder until the label floats, exactly where the example
would be.

**Structure.** A value the source does not allow changing stays readable text
with its reason in a tooltip, so a missing capability does not dim the schema.

**Table designer.** Arranged after the
[Variant B reference](../decisions/assets/2026-09-06-table-designer/variant-b.html):
object navigation, inspector and SQL preview, with creation review replacing the
definition and breakpoints from a container query. Conditions expand into the
typed editor on click or Enter; tablespace and owner are shown disabled because
the creation API accepts neither.

Known deviations:

- **The ceiling on opened groupings is a number, not a measurement.** Nobody has
  looked at a database with six schemas.
- **Where one was in a catalog is not remembered.** A reload is back at the root.
- **The name of a row loses to the columns beside it in a narrow panel**, down to
  five characters; resizable columns are the only answer today.
- **Every row mounts its copy button.** The list is not virtualised, so five
  thousand tables mount five thousand buttons and tooltips; virtualising is the
  answer when the list gets it.
- **The two states of the connections column agree by arithmetic.** The wide head
  pads four pixels because that centres a 32-pixel button in a 40-pixel strip,
  and both leave four under the head; a scenario measures both and fails when
  they drift.
- **A row of the connections list carries four marks**: the icon, the name, the
  state dot and the open highlight. With several catalogs open the column gets
  busy, and nobody has measured it.
- **A revoked grant is noticed when something is asked.** The row stays until the
  list is read again; every route refuses in the meantime.
- **With no colour chosen the catalog outline barely shows**, deliberately: the
  mark says nothing the tab does not.
