# The second UI audit and its corrections

Date: 2026-09-29. Decision: D187.

## The problem

The audit of 2026-09-28 (D185, D186) set one scale and taught Quasar most of
it. The second audit looked at every screen the first had not — the catalog's
windows, the grid's editors, Structure, the table designer, query results,
content, graphs, pipelines, dashboards, the AI space, services, pairs of
catalogs and the states of all of them — with the same method: a browser at
twice the pixel density, each window's computed styles read out, both themes.

What the static checks of D185 hold was held: no screen wrote a size, a
weight, a colour or a spacing past the scale. The drift was in what Quasar
draws by itself, which no `.vue` file of ours writes and no unit test reads:

- A dense QBanner writes its message in Quasar's body2 — 14px spaced by .25px
  — beside a 28px icon, the one message in a window a size larger than the
  rest. An error banner was filled red, and the transaction bar placed a muted
  countdown and a quiet Roll back on that red at 1.6:1.
- A QTable paints its card #000, and everything Quasar draws dark `.q-dark`
  paints #fff: Structure, a record and a file's preview read harder than every
  word beside them.
- The messages under a field keep Quasar's line of 1, whatever
  `$field-bottom-line-height` says, so a wrapped hint stood with its lines
  touching; its colour is Quasar's .54 and .7 rather than the muted text.
- A compact field's height was stated under `:where()`, which counted none of
  the three classes Quasar uses to keep a dense select 40px: every toolbar
  field stood 40px beside its 32px buttons.
- A disabled main action was Quasar's .6 of #343434, a mid grey under white
  letters — a button of another colour rather than one that is off.
- The kit's `chosen` was the filled main action, so the view a window showed
  ("Tree", "DBML", "2D") read the same as "Run" beside it.
- A bare `<code>` fell to the browser's monospace, Courier New on Windows.
- The label column of a form, 108px, broke "New literal value" and "Link to
  this dashboard" onto two lines.
- A toggle kept 12px of hit area to the left of its track and stood 40px tall.
- A window's subtitle stood directly on the row the scrolled content cut, and
  read as drawn over it.

## D187. What Quasar draws on its own is on the scale too

**Every banner is a wash.** Error and success join warning and info: a light
ground of the tone under the body's text, the icon in the tone's colour, 13px
on a 20px line, a 20px icon. In a form the banner has no ground; the icon
carries the tone and an error keeps its words red, as a field's error does.
Rejected: keeping the filled error and giving what stands on it colours of its
own — every screen that put a control in a banner would have to know which
ground it was on.

**A badge in a row is washed too.** PK, FK, Administrator and "connected" are
words about a row; filled, a column of keys was the loudest thing on the
screen. A count on a button's corner asks to be seen and stays filled.

**Quasar's own text colours are the theme's.** `.q-table__card` and
`.q-dark` take `--dp-text`; the bottom of a field takes `--dp-text-muted` and
its messages the 16px line; an error keeps Quasar's red.

**Every scrolling surface shares one thumb.** Native overflow uses a transparent
track and corner with a thin, theme-coloured thumb; WebKit draws it at
`--dp-scrollbar-size`, and `AppScrollArea` uses that size and the same theme
tokens for its overlay bar. Each surface keeps its native scrolling behavior,
which matters to grids, editors and terminal controls.

**A compact field reads its height from `--dp-field-height`**, the control's
32px unless what holds it says otherwise: a card head sets its strip less its
line. The rule is written three classes deep so it outweighs Quasar's, and the
variable replaces the fight over specificity with the heads that clamp it.

**A disabled filled button is drawn off**: the ground of an unfilled control
and the colour of marks that are not read, at full opacity.

**`current` is the view being shown** — a dialect, a plan's view, 2D or 3D, a
toggle that is on — drawn as a current tab is (D186). `chosen` keeps the
filled look for the space you are in on a rail, where the mark has to be found
among icons on the chrome's grey; drawn as a tab there, it all but vanished.

**Code in the chrome is the application's monospace**, at the mono size.

**The label column is 152px**, room for three words at 13px. **A toggle is
dense**: its track starts where the label above it starts and the row is a
line, not 40px. **A window's subtitle** keeps 4px below its words and draws a
line under them once the content is scrolled.

## The screens

The kit's rules are only as good as the screens that spend them; the second
half of the correction went through the screens the audit had flagged.

- **Structure** held its row commands outside its panel at 1440: the table of
  columns was 726px in 662. The column of commands is held at the right edge
  while the rest scrolls under it, and a default — which can be a whole
  expression — is cut at 200px with the whole of it on hover.
- **Five ways of drawing "current"** that D186 had not reached are the current
  tab's ground: the run list beside a result (a blue line, which the statement
  and Messages carried at once), the operation a plan's details describe (in
  the cost bars' own blue), a workbook's sheet, the section of a document on
  screen (blue text) and the run a pipeline's canvas shows.
- **An error is said where it is about.** The value a cell editor could not
  store is the field's error, not a banner over the form; the reason Declare
  as table cannot be saved stands beside Save. A connection's form no longer
  prints zod's "Too small: expected string to have >=1 characters".
- **A reason something is off** is told beside a menu rather than over its
  next line, and in a pair of catalogs after a dash, smaller than the command.
- **Folded parts** of the table designer turn a chevron (`dp-disclosure`);
  **the query's command row** shows where it scrolls on, as the grid's does,
  from one class.
- **The column manager** is an even grid of columns with the header's pin, not
  a wrapped row of boxes each saying "Pin left"; sorting says what no sort
  means; the chart's choices are a form with their names above them.
- **Smaller things**: a catalog says "Reading…" rather than "0 items" while it
  reads, a grid the same rather than "Rows 0"; a search result's size keeps its
  column; a narrow connections head gives its title up whole; a restore is
  decided in its confirmation rather than in red on every row; a diagram opens
  readable and Fit still shows it whole; a new window is lifted back rather
  than opened with its foot off screen; a record's null is the grid's; the window's minimize is the
  workspace's centred dash.

Left as they are, by earlier decisions: a stable window keeps its size when
its content changes (D132), so the viewer of a short value and a form with one
field open at their preferred size; the connection window and questions keep
their size controls (windows.md).

## What was checked

`tests/kit-scale.spec.ts` reads, on the kit's showcase in both themes, what the
browser paints: the banner's size, spacing and icon; a table cell's colour; a
hint's line and colour; every compact field at 32px; a disabled main action's
ground and opacity; a toggle's track against its row; the face of `<code>`.
It was run against the kit as it stood before the change and failed there.
The unit suite, the type check, lint, the build, the documentation check and
the whole Playwright suite were run after each half.
