# Design system

What a size of text, a height, an icon and a colour of text are worth, and
which one a role spends. Read this before giving anything on screen a size, a
weight, an icon size or a text colour of its own. How screens are built and
what the kit is, is in [frontend.md](frontend.md); the neutral window forms
are D131 there.

Decisions here: D185, D186, D187.

```
frontend/src/
├── quasar-variables.sass     the scale said again for Quasar's own components
├── main.ts                   ships Inter with the bundle
└── shared/ui/
    ├── metrics.css           sizes: type, lines, icons, controls, scrollbars, rows, spacing, corners
    ├── typography.css        roles: overline, helper, meta, section and page titles; tag resets
    ├── theme.css             colours, the text colours and the focus ring among them
    └── typography.spec.ts    fails on a size or a weight spent past the scale
```

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
  its value. Rows are 24px dense or 32px ordinary; both kinds of tab are 26px.
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
  colour — stands on `--dp-tab-current` at 500. What is ticked for an action
  is washed in `--dp-selected`. A connection's own colour marks its own
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
