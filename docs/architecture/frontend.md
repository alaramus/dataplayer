# Frontend

How a screen is built, where state lives, and what the component kit is. The
panel engine, the layout and floating windows are in
[workspace.md](workspace.md).

Decisions here: D6, D7, D11.

## What exists today

Vue 3, TypeScript, Quasar, Vite, TanStack Query, Pinia. Sign in, a catalog of
source types, a form generated from the adapter's own schema, the list of
connections, the catalog of a connection as a list of one level, and a paged row
grid. Light and dark themes, switched by a button beside Sign out and remembered.

```
frontend/public/
└── icons/services/      the logo of a source type, one SVG per type

frontend/src/
├── client/              generated from OpenAPI, never edited by hand
├── shared/
│   ├── ui/              the component kit every screen is built from;
│   │                    tokens.ts turns meaning into Quasar props,
│   │                    theme.css turns meaning into colours in both themes,
│   │                    layers.css turns meaning into stacking order,
│   │                    useToast and useConfirm replace $q,
│   │                    index.ts is the one import path
│   ├── api/             client setup, and one reading of an API error
│   ├── auth/            the session, watched across tabs
│   ├── SchemaForm/      JSON Schema to form, framework-independent core;
│   │                    a field says which tab and which row it belongs to,
│   │                    and readSchema tells a plain schema from a union
│   ├── windows/         floating windows — see workspace.md
│   ├── workspace/       the panel engine — see workspace.md
│   └── testing/         helpers for tests, not shipped by any screen
├── stores/              Pinia: client-side state only — the session, the theme,
│                        and what the last connection check said
└── features/
    ├── auth/
    ├── catalog/         the list of one level, the row grid, and the menu of
    │                    what the ticked nodes admit; nodes.ts, rows.ts and
    │                    actions.ts are pure mappers, and nodes.ts holds the
    │                    table that says what a kind of node does;
    │                    useCatalogLevel.ts walks a catalog outside any component
    ├── structure/       a relation model in its own tab: columns, ordered
    │                    constraints and indexes; model.ts maps them to badges
    ├── connectors/      the list of sources, the catalog of source types that
    │                    starts a new one, and the window that registers one;
    │                    adapterSearch.ts is a pure mapper
    ├── workspace/       the panels and their roles — see workspace.md
    └── dev/             /ui-kit and /workspace-demo, dev builds only
```

## D6. Server state lives in vue-query; Pinia holds only client state

The old frontend spread server data across Pinia stores, each with its own cache
and its own invalidation, and that is where its desynchronisation bugs come from.

Enforced by ESLint: `src/stores/**` may not import the generated client or any
feature.

## D7. The frontend is Vue 3 with Quasar

The value of the rewrite is backend architecture and end-to-end typing; the UI
kit was never the problem. The typed client generated from OpenAPI is kept — it
does not depend on the framework.

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

## Screens

The catalog is a list of one level: a click opens what can be read and walks into
what cannot, a tick box picks a node out without opening it, the way back is the
first row, and the path above it starts at a home button. One menu in the head
carries everything the source can do, live for what is ticked and greyed out for
the rest — standing in a folder is not choosing it. What that menu offers comes
from the server; see D9 in [adapters.md](adapters.md).

A connection is a row of two things: the icon of its type, with the dot of the
last check standing on it, and its name. Everything else about it lives in the
window that icon opens.

Known deviations:

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
- **The state dot only knows about this session.** A connection shows grey until
  the user checks it; nothing checks in the background, because that would mean
  opening a connection to every source on every load. The record is not
  persisted: a dot restored from yesterday would claim more than it knows.
