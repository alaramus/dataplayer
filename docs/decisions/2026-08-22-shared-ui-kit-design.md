# Shared set of UI components

Date: 2026-08-22
Status: agreed
Subproject: 7-preparation

## Goal

Subprojects 7+ are ahead — realtime, AI, the data grid. That is a lot of new
screens. The task is for them to be assembled from ready-made bricks rather
than drawn from scratch each time, and for the frontend to stay manageable
once there are many windows.

Along the way, the duplication that already exists is removed.

## What is duplicated today

Eight screens, and in them:

- **The dialog shell** — `q-dialog > q-card`, inline width (460, 520, 900px),
  a `text-h6` heading, `q-card-actions align="right"` with a flat Cancel and a
  primary: three times almost verbatim (`ActionDialog`, `CatalogDialog`,
  `ConnectorDialog`).
- **The error banner** `q-banner dense class="bg-negative text-white"` — four
  times, plus a positive/negative variant in `ConnectionCheck`.
- **`messageOf(cause)`** — unpacking an `AxiosError` into a message — copied
  verbatim three times; `serverErrorsFrom` / `fieldErrorsFrom` — twice.
- **An icon button with a tooltip** — four in `ConnectorTable`, two without a
  tooltip in `RowGrid`.
- **`destructive ? 'negative' : 'primary'`** — in `ActionBar` and `ActionDialog`.
- Empty states ("Nothing to show", "No rows", "No connections yet"), a
  spinner, `quasar.notify` with a hand-written `type`.

Colours are already gathered in `src/quasar-variables.sass`. Sizes, spacing
and density are not.

## Decisions

### R1. The kit is a layer of meaning over Quasar, not a facade over it

Features may still use `q-*` directly where the kit has no replacement. A full
facade — a wrapper over every Quasar component — is rejected: the cost of
passing through the whole API surface does not pay off, and replacing the UI
library is not among the goals.

The boundary runs like this: **the kit owns whatever has a choice of
appearance.**

Wrapped: `q-dialog`, `q-card`, `q-card-section`, `q-card-actions`,
`q-btn`, `q-tooltip`, `q-banner`, `q-input`, `q-select`, `q-toggle`, `q-file`,
`q-table`, `q-badge`, `q-spinner`.

Not wrapped, and this is not an oversight:

- `q-layout`, `q-header`, `q-toolbar`, `q-page` — live inside `AppLayout`,
  one consumer, a wrapper around a wrapper.
- `q-tree` — one consumer, and in subproject 7 it will probably be replaced by
  a tree of our own.
- `q-icon`, `q-separator`, `q-td`, `q-th`, `q-form` — primitives with no
  choice of style; there is nothing to wrap.

### R2. A semantic API plus pass-through attrs

A screen says **what** something is, not **how** it looks:

```vue
<AppButton variant="danger" label="Delete" :loading="…" @click="…" />
```

`flat`, `dense`, `color` disappear from features. The mapping
`variant → q-props` lives as a pure function in `tokens.ts` and is tested
without mounting — the same way as `treeNodes.ts` and `rows.ts`.

All other attributes pass through. This is a valve: a rare case must not break
the kit or require editing a wrapper in the middle of a task.

Two exceptions, found during execution. `AppDialog` sends attributes to the
card: QDialog renders through a teleport, and an attribute on it lands on no
element that can be addressed. `AppSection` has two roots when it draws a
separator, and Vue cannot guess the root; attributes go to the section. Both
declare `inheritAttrs: false` and bind `$attrs` explicitly.

**`data-testid` is not declared as a prop** and goes through `$attrs`. The
reason is not convenience: Quasar moves an undeclared attribute onto the
`<input>` itself rather than the field's root, and the tests already rely on
this. A declared prop would break the move.

A closed API (`inheritAttrs: false`, declared props only) is rejected: it
turns every rare case into an edit of the kit.

### R3. The rule is held by a linter, not by memory

`vue/no-restricted-html-elements` compares `node.rawName` and lets through
everything in the HTML namespace — `<q-btn>` falls into it, so the rule works
on components despite its name. It is enabled for all of `src` except
`src/shared/ui/**` and the generated `src/client/**`: `SchemaForm` lives
outside `features`, but it is screen code all the same. Each forbidden element
has its own message naming the replacement.

The rule has a hole: it compares the raw name, so `<QBtn>` gets past it. The
first plan was to close it with `vue/component-name-in-template-casing` in
kebab-case, but that rule demands kebab-case from our own components too
(`<ActionDialog>`, `<SchemaFields>`), that is, it forbids the Vue convention
together with the hole. Instead the list names **both spellings** of each
element: `q-btn` and `QBtn`. Verified by attempting the bypass.

The second rule is `no-restricted-imports` on `useQuasar` in screens: it is
needed there only for `notify` and `dialog`, and those are now `useToast` and
`useConfirm`.

### R4. The showcase lives in the application and cannot fall behind

A `/ui-kit` route, registered only under `import.meta.env.DEV`: every
component with all its variants, ready to be poked. Zero new dependencies, and
the page breaks together with the component. It requires no login — there is
no server data on it, so it opens without a running backend.

Storybook is rejected: a heavy dependency, its own build and one more line in
"What holds it up" that would have to be fixed.

The page breaks together with the component, but **forgetting to add a new
component to it is easy, and nobody would notice.** So a unit test compares the
list of `.vue` files in `shared/ui` (through `import.meta.glob`) with the
registry the page renders. A new component without a demonstration fails
`bun run test:unit`.

### R5. API error parsing goes there too, although it is not UI

`shared/api/errors.ts` with `messageOf(cause)` and `fieldErrorsFrom(cause)`.
Formally not UI, but it is the same duplication (three files and two) and is
cured by the same move.

## Contents

```
src/shared/ui/
├── AppLayout.vue        already exists, stays
├── AppPageHeader.vue    heading + actions slot
├── AppCard.vue          a card outside a dialog
├── AppDialog.vue        q-dialog + q-card + header + footer
├── AppSection.vue       q-card-section, with a separator and scrolling
├── AppActions.vue       q-card-actions
├── AppBanner.vue        tone: error | success | warning | info
├── AppButton.vue        variant: primary | secondary | danger |
│                        danger-quiet | quiet
├── AppIconButton.vue    icon + mandatory tooltip
├── AppTooltip.vue
├── AppInput.vue  AppNumberInput.vue  AppSelect.vue  AppToggle.vue
├── AppFileInput.vue
├── AppTable.vue         flat/bordered defaults + emptyText
├── AppBadge.vue  AppSpinner.vue  AppEmptyState.vue
├── tokens.ts            panel sizes, pure functions variant → q-props
├── useConfirm.ts        wrapper over Quasar Dialog → Promise<boolean>
├── useToast.ts          success / error / info
└── index.ts             the single import point
```

Plus `src/shared/api/errors.ts` and `src/features/dev/UiKitPage.vue`.

Imports are explicit from `@/shared/ui`, with no global registration: it is
visible where a component comes from, and types work. Slots are passed through
by enumeration — except in `AppTable`: cell slots are named after columns, so
their names are unknown to the kit, and enumerating them would mean knowing
every screen. This is the only place with a loop over `$slots`, and a comment
there says so.

Four decisions made along the way:

- **Five button variants, not four.** The action bar lists destructive actions
  next to ordinary ones, and solid red buttons there would shout. So a
  destructive action has both a prominent form (`danger`) and a restrained one
  (`danger-quiet`).
- **Panel sizes are shared by the dialog and the card** (`xs`…`lg`): it is the
  same task — a panel of a chosen width.
- **`AppSection` and `AppActions` were added.** Without them a screen that
  needs three sections with separators (the catalog) would write
  `q-card-section` by hand, that is, past the kit.
- **`AppNumberInput` is separate from `AppInput`.** One component cannot
  report both a string and a number: `string | number | null` would have to be
  kept in the state of every caller. As a side effect an emptied number field
  is now `null`, not `0` — a port nobody filled in is absent, not zero.

## Migration

First the kit with tests, then the screens one at a time, each in a separate
commit with an e2e run:

`LoginPage` → `ConnectionCheck` → `ActionBar` → `ConnectorTable` →
`ConnectorsPage` → `SchemaFields` → `ActionDialog` → `RowGrid` →
`CatalogDialog`.

**Acceptance criterion: not a single line in `tests/` changes.** Thirty-five
selectors are written out in advance; if a wrapper breaks something, the
wrapper is what breaks, not the test.

## What checks it

| Command | What it catches |
| --- | --- |
| `bun run test:unit` | `tokens.ts`, `errors.ts`, every kit component, completeness of the showcase |
| `bun run lint` | `q-*` with a replacement outside `shared/ui`; the PascalCase bypass; importing `quasar` in features |
| `bun run type-check` | types of props and slots |
| `bunx playwright test` | that the screens work as before after migration |

Both lint rules are verified by deliberate breakage: a rule that has never
gone red proves nothing.

`/ui-kit` is looked at in the browser — a green unit test does not mean the
user sees it.

## Known trade-offs

- **Part of the kit has one consumer** (`AppBadge`, `AppFileInput`,
  `AppSpinner`, `AppTooltip`). A direct departure from "Generalise on the second or
  third use" in ENGINEERING.md, taken deliberately: the goal of the subproject
  is predictability as it grows, not the smallest diff today.
- **Pass-through attrs are a workaround.** Through them one can pass
  `color="purple"` and get around the semantic API. No machine catches this.
- **`q-tree` is outside the kit.** In subproject 7 the tree will have to be
  decided anew.
- **No dark theme.** Tokens stay build-time sass variables; switching on the
  fly would need CSS variables and a separate task.
