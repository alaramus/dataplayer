# Design system

What the component kit is, what a size of text, a height, an icon and a colour
of text are worth, and which one a role spends. Read this before adding to
`shared/ui`, giving anything on screen a size, a weight, an icon size or a text
colour of its own, or before changing a theme. How screens are built is in
[frontend.md](frontend.md); the neutral window forms are D131 there.

Decisions here: D11, D185, D186, D187, D196.

```
frontend/src/
├── quasar-variables.sass     the scale said again for Quasar's own components
├── main.ts                   ships Inter with the bundle
└── shared/ui/
    ├── metrics.css           sizes: type, lines, icons, controls, scrollbars, rows, spacing, corners
    ├── typography.css        roles: overline, helper, meta, section and page titles; tag resets
    ├── theme.css             colours, the text colours and the focus ring among them
    ├── contrast.spec.ts      fails on a theme below a contrast floor (D196)
    └── typography.spec.ts    fails on a size or a weight spent past the scale
```

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
  stay outside the clip. Select options use the same neutral focus colour in
  toolbars and forms.
- **A card is one look.** A Data section, the dashboards rail and dashboard,
  a widget, the chats and a chat are `AppCardFrame` with an `AppCardHead`:
  one frame, and a head of the tab strip's height on `--dp-card-head` in
  every state, empty or loading included. A collapsed rail keeps the head with
  its plus alone in it — the connections, the dashboards, the chats — so the
  strip runs unbroken across the screen. `WorkspaceLeaf` draws the same frame and
  head from the same tokens, because its root is the engine's. The head is a
  middle tone between the outer chrome and the card's working surface; neutral
  tabs keep a distinct fill on that tone.
- **Button layout belongs to the kit.** `toolbar` keeps an icon and label on one
  line, `navigation` aligns an entry to the left and keeps it to one line — a
  long name ends in an ellipsis and is given whole on hover — and `AppTree`
  owns the full-row selection mark. Screens size fields through their own classes on kit
  components, never by selecting Quasar internals.
- **Button icon names live in `shared/ui/icons.ts`.** A screen chooses a named
  action from `appIcons`; its ligatures use Material Symbols Outlined, including
  the application's replacements for older names absent from that font.
  Quasar's built-in controls use the same icon set. A source-provided icon
  remains part of its source contract, and the UI kit shows every named icon.
- **Flat action text has theme colours of its own.** `secondary` and
  `danger-quiet`, icon buttons included, use `--dp-action-secondary` and
  `--dp-action-danger`, lighter in the dark theme than the filled `primary` and
  `danger`.
- **The one you are in is `chosen`, not `secondary`.** The space you are in, the
  view a window shows, a toggle that is on: written as `secondary`, it was a
  grey dimmer than the quiet buttons beside it in the dark theme, so it stood
  out least. `chosen` is filled like `primary` until the visual pass gives it a
  look of its own.
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
  caller passes its own `aria-label`. A button drawn as an icon alone keeps the
  label it does not draw and speaks it instead: a narrow rail is a reason to
  show less, not to be called nothing, and four commands that dropped their
  label to fit one were announced as unnamed buttons (U04).
- **A command that is off is still a command.** Disabled, an icon button is out
  of the tab order, which left its reason on hover and nowhere else; the
  wrapper that already carried the tooltip takes the button's place in the tab
  order and its name — label and reason together — and the button inside is
  hidden from a reader so the pair is announced once. A disabled menu line says
  the same way that it is a line of the menu, that it is off and why, because
  Quasar otherwise draws it as loose text (U14). The tab stop there is Quasar's
  to give, and it gives a disabled item none.
- **The kit documents itself at `/ui-kit`**, a route registered only under
  `import.meta.env.DEV`. It renders the real components, and a test compares the
  page against the files in `shared/ui`, so a component cannot be added without
  a demonstration.
- **Reading an API error is one function**, `shared/api/errors.ts`.

Three tests read every `.vue` under `src` and fail on a `z-index` that is not a
`--dp-layer-…` name, on a gap, padding, margin or radius written as pixels, and
on a colour reached for past the theme — written as a number, as
`var(--q-negative)`, or as one of Quasar's colour classes outside the kit. The
colour test reads the `.ts` modules too, because a class name is as often built
there.

A fourth asks not what a value looks like but whether it exists.
`var(--dp-radius)` in a dialog and `var(--dp-danger-text, #d32f2f)` in the
highlighter both named a token nobody had declared — the first dropped in silence
by the browser, the second a literal colour wearing a token's name — and the
graph asked for `--dp-muted` where the theme declares `--dp-text-muted`, so its
captions were never muted. Vite hands a test an empty string for a `.css` file,
whatever the query, so this one reads the three token files from the disk; it is
the single source file typed by `tsconfig.node.json` rather than by the
application's browser-only config, which is why Node stays out of the
application's types. What actually paints over what remains a browser question,
answered by a Playwright scenario.

Two exceptions are written into the tests rather than left to review.
`panelColor.ts` computes the colours a person chose for a connection, which are
data and not a palette; `tokens.ts` says `color="negative"` because it is the
one place meaning becomes a Quasar prop. A `1px` border keeps its pixel: it is a
hairline, not a space.

Known deviations:

- **Part of the kit has one consumer or none** (`AppBadge`, `AppFileInput`,
  `AppSpinner`, `AppTooltip`; `AppTree` since the catalog became a list). A
  knowing departure from "generalise on the second use": the kit is built as an
  alphabet, for predictability as screens grow.
- **Attribute fall-through is a way around the kit.** Nothing stops a screen
  passing `color="purple"` to the Quasar component underneath; only review does.
- **`AppTree` wraps `q-tree`.** Its node and lazy-load types are read off
  Quasar's props, so replacing the tree would change what a screen passes it.
- **The theme is chosen once per browser.** Light, Paper light, Dark, Paper
  dark, Midnight, Dark blue, Dark purple or System, listed once in
  `stores/theme.ts`; System is what nothing stored means and follows the
  operating system between Light and Dark as it changes. The named ones carry
  their own grounds, selected by a marker beside the dark class; Paper light
  carries it without the dark class. The choice does not follow a user
  elsewhere.
- **Every theme is measured** against contrast floors and one order of
  grounds by `contrast.spec.ts` (D196).

Spec: [The shared UI kit](../decisions/2026-08-22-shared-ui-kit-design.md)

## D185. Type, geometry and icons are one scale, and Quasar is told it

The kit owns the look of text and controls; Quasar's own components are
configured from the same numbers rather than left at their defaults. The
audit of 2026-09-28 found the chrome at 13px and every button and field at
Quasar's 14px, a button 36px beside a 32px field, a button's corner 3px beside
a field's 4px, and Quasar's document heading styles leaking a 50px line into
every `<h3>` of the chrome.

- **One face, shipped.** Inter comes with the bundle (`@fontsource-variable/inter`,
  weight axis, normal and italic). Declared and not shipped, it had fallen
  through to Segoe UI on Windows and to whatever else elsewhere.
- **Seven sizes, each a role**: `xs` 11px for a count, a caption, an overline
  and a badge; `sm` 12px for help under a control, an error, a tooltip and a
  toast; 13px for the chrome, controls included; `lg` 15px for the title of a
  panel about one thing; `page` 20px; `display` 24px for a number that is a
  whole widget; `mono` 12px for the editor, a log and a value read character
  by character. Prose keeps its own 15/14px and heading sizes. Lines are
  pixels — 20px for the body, 16px for the small sizes when they wrap, 28px
  for a page title, 18px for mono — so a row lands on whole pixels.
- **Three weights**: 400 text, 500 a title of a card or window, the current
  tab and a button, 600 a section, an overline and a table heading. A
  browser's bold is 700 and is reset to 600 for `b`, `strong` and `th`.
- **Roles are classes** in `typography.css`: `dp-overline`, `dp-helper`,
  `dp-meta`, `dp-section-title`, `dp-page-title`. A screen carries the role
  rather than restating its size, weight and spacing. `h1`–`h6` are reset to
  inherit everything; their look is the class they carry.
- **One control height, 32px**, for a field, a button, an icon button and a
  toolbar field alike; 20px for a control inside a dense row. A toolbar field
  names itself beside it or by its placeholder, never by a label floated over
  its value. A select standing among other controls — the AI composer, a
  catalog's choice of groupings — is `framed`: a form field's box at the
  toolbar's height. Rows are 24px dense or 32px ordinary; both kinds of tab
  are 26px.
- **Three icon sizes**: 16px inside a line of text, 20px for a control of its
  own, 24px for a source's logo and an empty panel; 32px only for the logo
  heading a panel about one source and an empty conversation. Quasar's button
  icon follows the button's line (1.5385em), so a compact button shrinks its
  icon with it.
- **Three text colours**: `--dp-text` (.87) for everything read, `--dp-text-muted`
  (.6) for secondary text and as the floor for anything a person must read,
  `--dp-text-faint` for marks that are not text. The token that had been
  called strong was the weakest of the three and is gone.
- **One focus ring**: 2px of `--dp-focus-border` just outside the control.

Enforced by `typography.spec.ts`, which fails on a `font-size` in a component
that is not a type or icon token, on a weight other than 400/500/600, and on a
pixel size handed to an element from a script. Verified by breaking each.

Known deviations:

- **The terminal is 13px.** xterm takes a number, and a terminal is read as a
  screen of cells rather than as code in the chrome.

Spec: [The UI audit and its corrections](../decisions/2026-09-28-ui-audit-design.md)

## D186. A state and a pattern are drawn one way

The audit found each of them drawn several ways, a little differently in each
place; each is now one rule, and the kit holds it where it can.

- **The main action is last** in every footer, after Cancel and any secondary
  action: `Cancel / Apply / OK`, `Cancel / Save to my files / Download`. The
  right-hand group is one element, so a narrow window wraps it whole instead
  of parting OK from Cancel.
- **Current is not selected.** What is being shown — a tab, a section of a
  page, the chat on screen, the category of a list, an open dashboard with no
  colour — stands on `--dp-tab-current` at 500, a tab with a line in its
  text's colour under it. What is ticked for an action is washed in
  `--dp-selected` and edged with `--dp-selected-edge` (D196). A connection's own colour marks its own
  things: the tab being read is filled with it and the others carry its quiet
  half, as its row in the list does.
- **Flat actions are neutral text.** Secondary and quiet are one colour; their
  difference is where they stand, not a shade of grey too small to read.
- **A destructive command in a toolbar or a row is neutral** and turns red
  under the pointer or the keyboard (`AppIconButton` with `danger-quiet`). It
  is red where it is decided: a menu line, a confirmation, a form's Delete.
- **One card, one popover.** `AppCard` is the workspace's bordered card with
  the panel corner and no shadow, on the chrome's ground. Menus, select lists
  and tooltips are one floating surface: raised ground, a hairline, the soft
  shadow, the control corner.
- **A value that edits itself reads as the value** — `AppButton` with
  `layout="inline"`: the cell's weight, its text in line with the cells that
  are not buttons.
- **What does not fit gives way in order.** A row of commands that scrolls
  shows a shadow at the edge it continues past; a narrow catalog drops the
  schema chip, then the count, before it cuts a name; a narrow catalog head
  keeps the choice of schemas and drops the two commands that open a second
  catalog.
- **The lower half of a rail keeps its buttons at its foot**, beside the bar
  at the bottom of the screen.

Known deviations:

- **A question keeps Minimize and Maximize.** Every window offers them
  ([windows.md](windows.md)), a confirmation included: nothing is modal, and
  a question can be put aside to look at what it is about.
- **The window in front is marked by its shadow only** (D131), which reads
  less on the dark theme's ground than on the light one's.

Spec: [The UI audit and its corrections](../decisions/2026-09-28-ui-audit-design.md)

## D187. What Quasar draws on its own is on the scale too

D185 told Quasar the scale through its variables; some of what it draws takes
none of them. Each of these is now said once, in the kit or in `theme.css`.

- **Every banner is a wash**: a light ground of the tone under the body's
  text, the icon in the tone's colour, 13px, a 20px icon. In a form it has no
  ground; the icon carries the tone and an error keeps its words red.
- **A badge in a row is washed**; a count on a button's corner stays filled.
- **Quasar's own text colours are the theme's**: a table's cells and anything
  Quasar paints dark read `--dp-text`; the line under a field is
  `--dp-text-muted` on a 16px line, an error still red.
- **Every scrolling surface shares one thumb.** Native overflow uses a
  transparent track and corner with a thin, theme-coloured scrollbar; WebKit
  draws it at `--dp-scrollbar-size`, and `AppScrollArea` uses that size and the
  same thumb and hover tokens for its overlay bar. The browser keeps each
  surface's native scrolling behavior, including grids and editors.
- **A compact field is `--dp-field-height` tall** — a control's 32px unless
  what holds it sets less, as a card head does for its strip.
- **A disabled filled button is drawn off**: `--dp-disabled-fill` under
  `--dp-text-faint`, at full opacity.
- **`current` is the view being shown** (a dialect, a plan's view, 2D or 3D,
  a toggle that is on), drawn as a current tab; **`chosen`** stays filled for
  the space you are in on a rail, where a tab's grey would vanish on the
  chrome's.
- **Code in the chrome is the application's monospace**, at the mono size.
- **The label column of a form is 152px**; **a toggle is dense**, its track
  under the label above it; **a window's subtitle** draws a line under itself
  once the content is scrolled.
- **Screens follow suit.** A value the source refused is said under its field,
  as any field's error is, not in a banner above the form; a validation message
  is a sentence about the field, never the validator's own. A part of a form
  folded away is `dp-disclosure` — a chevron that turns. A row of commands that
  scrolls wears `dp-scroll-edges`. What a panel shows among its neighbours — a
  run, an operation of a plan, a sheet, a section of a document, a pipeline's
  run — stands on the current tab's ground (D186), and a reason something is
  off is told beside it: a menu's to the right of the menu, a pair's after a
  dash in the smaller size.

- **Monitors only.** The application is drawn for a monitor, 1024px being the
  narrowest workspace it is laid out for; there is no telephone's mode. A
  window still fits a small browser window, which is a window's rule (D132).
- **Charts speak the scale**: ECharts' axes and legends at the caption size in
  the application's face, their series in `--dp-chart-*`. **A question's
  window carries no icon**; an icon names the kind of thing a window holds.

Enforced by `tests/kit-scale.spec.ts`, which reads what the browser paints on
the kit's showcase in both themes; it failed against the kit before the
change.

Spec: [The second UI audit and its corrections](../decisions/2026-09-29-ui-audit-2-design.md)

## D196. Every theme is measured, and holds the same order

The audit of 2026-10-02 read the seven palettes as one system. Light and Dark
held; the named themes, partial overrides checked by eye, did not: a link at
3.9:1, tab captions at 4.2:1, a field's error at 2.9:1 on every dark ground,
field borders under 2:1 everywhere, info drawn in a bronze or a pink beside
the warning or the error it was meant to differ from, and three themes whose
frame sat below the surface and whose card head was the brightest thing on
the screen.

- **Floors, not taste.** Text and secondary text 4.5:1 on every ground a card
  is built of; a link, the accent and a note 4.5:1 on the surface, a window
  and a head; the focus ring, a field's border, a faint mark and a drop
  target 3:1. A chosen row 1.1:1 from a hovered one, a banner 1.08:1 from the
  page.
- **One order of grounds.** From the surface towards the middle: the frame,
  the card's head, and the tabs on it beyond the head; a window's bar beyond
  its frame. The window bar is `--dp-chrome` and the head `--dp-card-head`,
  so neither is bought with the other.
- **Info is a tone, not the accent.** `--dp-info` is its own token, at least
  60° of hue from the warning and the error; a theme's accent is its
  character and may be any colour.
- **A named theme declares its character.** Its grounds, its accent family and
  its note are written in its own rule; text, borders and the other tones may
  come from the theme beneath it.
- **A chosen row has an edge.** `--dp-selected-edge`, the accent along its
  leading side, beside the wash: a wash alone was 1.04:1 from a hover.
- **Quasar follows.** Its negative is `--dp-danger-fill`, and inside a field in
  error the error text; its dark grounds are the theme's.
- **The theme is on the page before the first paint**, set by `index.html`
  from the same choice the store reads; the toggle returns to the last light
  or dark theme chosen.

Enforced by `contrast.spec.ts`, which resolves each theme from `theme.css` as
the browser does, and by `theme.spec.ts` for the themes `index.html` knows.
Each assertion was broken once and failed.

Spec: [The theme audit and its corrections](../decisions/2026-10-02-theme-audit-design.md)
