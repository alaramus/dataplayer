# Theme, the window layer and three corrections to the screen

Date: 2026-08-23
Status: done
Subproject: corrections following work in the browser

## For someone starting from a clean session

Read in this order: [AGENTS.md](../../AGENTS.md), decisions R11 (component
kit), R12 (workspace), R14 (floating window);
[ENGINEERING.md](../../ENGINEERING.md), sections "Frontend" and "Tests".

There is not a single line of backend here. Everything that changes lives in
`frontend/src`, and no change touches the API contract — the client does not
need to be regenerated.

What already exists and what we build on:

- The screen is three columns, each of which collapses
  (`shared/workspace/WorkspaceLeaf.vue`); a collapsed one shows what the
  feature considered worthy of forty pixels (`collapsedOf` in
  `features/workspace/panels.ts` → `ConnectorRail.vue`).
- A connection is edited in a floating window (`shared/windows/`,
  `features/connectors/ConnectorWindow.vue`).
- The catalog is one level: a header with the source icon, the path and the
  actions menu, below it filters and the list (`panels/CatalogPanel.vue`).
- Every screen is assembled from `shared/ui`, and reaching for `q-*` past the
  kit is a linter error.

One command that will be needed right away:

```bash
cd frontend && bun run dev
```

## Goal

Four things noticed while working with the screen, not while reading the code.

1. The collapsed connections column loses the "plus": a connection cannot be
   added from it, although a catalog can be opened.
2. A window slides under the blue header and under the sticky column headings
   of a table, and from under the header there is nothing left to grab it by.
3. The schema selection in the catalog stands on a separate line, although for
   a file source the path stands in exactly that place of the line.
4. There is no dark theme at all.

## What is not here

- **A third theme state.** Only light and dark; "as in the system" takes part
  once — when no choice has been made yet. A three-item menu for the sake of
  returning to a value that is the default anyway is a state screen for the
  sake of a state screen.
- **A theme that follows the system live.** Once the choice is made, it is
  made; `matchMedia` is not listened to.
- **Resizing the window.** It still only moves — R14.
- **Moving the filter line.** Only the schema selection is raised into the
  catalog header: the text filter is something one types into, and it needs
  width.
- **A theme for `/ui-kit` and `/workspace-demo`.** They are assembled from the
  same components and will darken along with them; they get no separate check.

## Decisions

### T1. The collapsed column offers the same action, not a lesser one

`ConnectorRail.vue` gets an `add` button as its first row, above the source
icons. It calls `workspace.editConnector(null)` — exactly the call that
`ConnectorsPanel` makes, not its own copy of its meaning.

The `data-testid` stays the same — `add-connector`. The rail and the panel
stand under `v-if`/`v-else` in `WorkspaceLeaf.vue` and never exist together,
and a second identifier would claim these are two different controls. It is one
action shown at two widths.

### T2. The window is a layer above the application chrome but below menus

`.app-window` currently has no `z-index` at all. Hence both halves of the
complaint at once: the sticky `<th>` is declared with `z-index: 1`, the Quasar
header with `2000`, and a positioned element with a positive `z-index` is
painted over any positioned one with `auto`, however late in the tree that one
is.

The window is assigned `3000`: above the header and footer (`2000`), below
`q-menu` and `q-dialog` (`6000`). The lower bound is not decoration: a dropdown
in the connection form, the actions menu and a confirmation dialog open *from*
the window and must lie on top of it.

`geometry.ts` does not change. `clamp` already keeps `y ≥ 0`, so the title bar
never left the screen — it was invisible, not unreachable. It was the layer
that needed fixing, not the rule.

A second option was considered and rejected: treat the area between header and
footer as the field for windows and make `clamp` stop at it. It describes the
screen more honestly, but requires the window engine to learn the height of the
application chrome — and `shared/windows` does not know and must not know that
there is an `AppLayout` above it. The cost of the accepted option is named in
"Known deviations".

### T3. The catalog header holds what this level is chosen by

The schema selection moves from a separate line into `catalog-panel__bar` —
into the very gap between the connection icon and the actions menu where a file
source has its breadcrumbs.

This is not alignment for the sake of symmetry. The header line answers one
question: where we are inside the source. For a file source the answer is a
path, for PostgreSQL it is the set of selected schemas. One place for one
question; what form the answer takes follows from which nodes the level holds,
and never from the source type — the same rule by which the path is shown only
below the first level.

Both can be drawn at once, if a source with both a path and groupings ever
appears: the crumbs come first, the selection after them, the menu is still
pressed to the right.

### T4. A colour is a meaning, and it is translated in one file

`shared/ui/theme.css` declares on `:root` every value the application paints
itself with, and redeclares them under `body.body--dark`. Names are by meaning,
not by value: `--dp-surface`, `--dp-surface-raised`, `--dp-border`,
`--dp-hover`, `--dp-selected`, `--dp-text-muted`, `--dp-text-faint`,
`--dp-shadow`, `--dp-accent-soft`.

The same relationship as `tokens.ts` has: a component names a meaning, one file
turns it into a value. Forty-odd literals in twelve `.vue` files are replaced by
`var(--dp-*)`.

Why CSS properties and not Sass variables: Sass is computed at build time, and
the theme is switched in the browser. This is exactly what "Known deviations"
said — and why there was no dark theme until now.

### T5. The theme choice is client state, and Quasar learns of it in one place

`stores/theme.ts`, Pinia: the server knows nothing about the theme, and by R6
this is exactly where it belongs.

- The first value: what is written in `localStorage`; if that is empty —
  `prefers-color-scheme`. The system answers once, on the first visit.
- Switching writes the choice back to `localStorage`.
- `Dark.set` from Quasar is called only from here. The plugin puts the class
  `body--dark` on `<body>`, by which the properties from T4 switch — so the
  application's own colours and Quasar's colours switch with one event, not
  two.

It is applied in `main.ts` after `.use(Quasar, …)` and before `.mount()`. Both
bounds are needed: the Dark plugin's `install()` writes the theme to the
document itself, so a choice applied earlier is overwritten; one applied later
does not make it in time for the first frame, and the dark theme starts with a
flash of light. Found in the browser, not by tests — see "What turned out
differently".

### T6. The toggle is a kit component

`shared/ui/AppThemeToggle.vue`: an `AppIconButton` with the `dark_mode` icon in
the light theme and `light_mode` in the dark one. In the kit, because it has a
choice of appearance; in the barrel and in `/ui-kit`, because `kit.spec.ts`
requires that of every file in `shared/ui`.

`AppLayout.vue` puts it next to "Sign out". In the same place as signing out:
these are two things about the session, not about what is on screen.

## What changes

### Component kit

- `shared/ui/theme.css` — new: light theme properties and their redeclaration
  under `body.body--dark`.
- `shared/ui/AppThemeToggle.vue` — new.
- `shared/ui/index.ts` — export of the toggle.
- `shared/ui/AppLayout.vue` — the toggle in the bar.
- `shared/ui/AppTable.vue` — `#fff` on the sticky header → `var(--dp-surface)`.

### State

- `stores/theme.ts` — new.
- `stores/theme.spec.ts` — new.

### Windows

- `shared/windows/WindowFrame.vue` — `z-index: 3000`; colours → variables.

### Screen

- `features/workspace/panels/ConnectorRail.vue` — "plus" on top; colours.
- `features/workspace/panels/CatalogPanel.vue` — schema selection into the
  header; colours.
- `features/catalog/CatalogList.vue`,
  `features/connectors/{AdapterCatalogDialog,AdapterDetailPanel,AdapterTile,
  ConnectionCheck,ConnectorDot,ConnectorList,ConnectorWindow}.vue`,
  `shared/workspace/{WorkspaceLeaf,WorkspaceSeparator}.vue`,
  `features/dev/WorkspaceDemoPage.vue` — colours.
- `shared/workspace/WorkspaceLeaf.vue` — `color: inherit` for the tab and the
  arrow buttons: see "What turned out differently".

### Build

- `main.ts` — import of `theme.css`, applying the choice before `mount`.
- `features/dev/UiKitPage.vue` — showing the toggle.

### Documents

- `AGENTS.md` — "There is no dark theme" leaves "Known deviations"; what is
  named below arrives.

## Order of work

1. T1: the "plus" in the collapsed column. A Playwright scenario for it — first.
2. T2: the window layer. Scenario: a window raised to the top edge stays
   visible and can be grabbed by the title bar.
3. T3: schema selection into the header. The existing `catalog-groups` is not
   renamed, so the catalog scenarios must stay green without edits.
4. T5: the theme store and its spec — before any CSS.
5. T4: the properties and the replacement of literals, file by file.
6. T6: the toggle, the barrel, `/ui-kit`, `AppLayout`, `main.ts`.
7. A Playwright scenario for the theme: switch, check `body--dark`, reload,
   check again.
8. `AGENTS.md`.

## What holds it up

| Command | What it checks |
| --- | --- |
| `bun run test:unit` | the theme store; `kit.spec` — that the toggle is in the barrel and in `/ui-kit` |
| `bun run lint` | that no screen reached into `q-*` past the kit |
| `bun run type-check` | types |
| `bunx playwright test` | the "plus" in the rail (`workspace.spec.ts`), the window layer (`connector-windows.spec.ts`), the theme and tab legibility (`theme.spec.ts`) |

The rule "a green unit test is not the same as what the user sees" is
especially apt here: three of the four changes are about what is visible on
screen, and none of them is proven by anything but the browser.

## Known deviations this will add

- **A window can cover the application header.** Dragged up, it lies over
  "Sign out" until moved aside. The cost of the window engine not knowing the
  height of the chrome above it; the window cannot get lost because of this —
  T2.
- **The theme does not follow the system.** Asked once on the first visit,
  after that the user's choice.
- **The theme is per browser.** `localStorage`, like the layout: it does not
  move to another machine and is not kept consistent between two windows.
- **The dark palette is picked, not derived.** The values under
  `body.body--dark` were picked by eye to match Quasar's colours; WCAG contrast
  is not computed by anyone.
- **The toggle is binary, while the theme could have had three states.** Once
  a choice is made, there is no way back to "as in the system" — only by
  clearing `localStorage`.

## What turned out differently than planned

Two things that were not in the plan and were found only in the browser. Both
are about a green unit test not being what the user sees.

### Order of applying the theme: not "before `mount`" but "after Quasar and before `mount`"

T5 says "applied before `mount`". That is not enough. The Dark plugin's
`install()` writes the theme to the document itself — light, since nothing
configures it — so a choice applied one line above is overwritten on the next.
Meanwhile the store answered `dark: true`, and `<body>` had `body--light`: six
unit tests were green, and the application opened in the wrong theme.

`main.ts` now calls `apply()` between `.use(Quasar, …)` and `.mount()`, and
both bounds of this interval are named in a comment on the spot.

### A native button does not inherit colour

The section tab and the collapse arrows in `WorkspaceLeaf.vue` are real
`<button>`s. Their colour is given by the browser, and it is black;
`font: inherit` does not carry colour with it. In the light theme black on
white — as intended; in the dark one black on `#121212` — the tab is invisible.

It is cured by a single `color: inherit`, but it could only be found by looking
at `getComputedStyle`. Hence the third scenario in `tests/theme.spec.ts`: it
checks not a variable but the colour the tab is actually drawn in.

### The actions menu in the catalog header is not always there

T3 speaks of the gap "between the connection icon and the actions menu".
PostgreSQL has no menu at all — `CatalogActions` draws anything only if the
source has declared at least one action — so for it the line is the icon and
the schema selection. The behaviour is unchanged and correct; the wording
should be read as "to the end of the line".

### Quasar gives a table its own card

Noticed by the user on screen, not by a check: the right column differed in
black from the middle one. `q-table` draws itself a card — white in the light
theme and `#1d1d1d` in the dark one — and it lay over the panel, which is
`--dp-surface`. Plus our sticky header on top: three different colours in one
column, and the header came out as a stripe across the table it heads.

A table that fills a panel is not a card: it takes the surface it was put on.
`background: var(--dp-surface)` now stands both on the table and on its header
— as one value, because they must not diverge by definition: the header exists
to hide the rows sliding under it.

A trap inside the trap: the class `app-table--sticky` lands on *the same*
element that Quasar calls `q-table__container`, so the first version of the fix
was a nested selector and matched nothing. A scenario caught this, not the eye.

### The label above the field and the strip below it

Noticed by the user: above the selected schema stood the word "Schemas", and
because of it the header was two lines tall. Quasar raises the label from the
field upwards exactly when the field is filled — that is, the extra line
appeared exactly in the case where it is least useful: the chip already names
the schema.

The label is now set only when the selection is empty, where it plays the role
of a hint and stands inside the line. The control's name is not lost:
Quasar forwards `aria-label` to the `combobox` itself, as it forwards
`data-testid`.

Below the field another twenty pixels were found: `q-field` reserves space for
an error message whether or not there is one. `compact` was already declared as
"a field in a panel, not in a form", and now also means `hide-bottom-space`. An
error still colours the field; only its text has nowhere to go, so `compact` is
for a panel where nothing is validated. Header strip: 61 → 41px.

### The catalog header is one height, not whatever comes out

Noticed by the user: for a file source the header is 76px, for PostgreSQL 85,
and when moving between connections the list below it jumped. The cause is not
in the sources: the icon and the menu are 32px, the field is 40, and nobody
declared the height of the strip, so it was the height of the tallest thing put
into it.

Now `height: 40px` is stated on the strip itself, and everything in it is
centred. The rule is about the panel, not the source — and only such a rule
cannot be broken by a source type added later: what it brings will fit inside
the line rather than set it.

This cannot be checked by eye for every new adapter, so the symmetry is a
scenario: `tests/catalog.spec.ts` measures the header in four states (a
database with no schema selected, a database with one selected, a storage at
the root, a storage inside a folder) and requires one number. Without the rule
it gives 85 against 76.

## How it was actually verified

Each of the three new scenarios was verified in reverse: the change was rolled
back, the test was run and failed.

| What was rolled back | What went red |
| --- | --- |
| `z-index: 3000` on `.app-window` | «a window is painted over the chrome and over a grid it covers» |
| the "plus" in `ConnectorRail.vue` | «a pushed-aside column of sources still opens one of them» |
| `color: inherit` on the tab | «a tab is legible in the dark theme» |
| the background on `.app-table--sticky` | «a column of the workspace is one colour, grid included» |
| `height` on `.catalog-panel__bar` | «the head of a catalog is one height across source types» |

Result: 51 Playwright scenarios, 385 unit tests, `lint` and `type-check` clean.
