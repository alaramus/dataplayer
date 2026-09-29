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

## What was checked

`tests/kit-scale.spec.ts` reads, on the kit's showcase in both themes, what the
browser paints: the banner's size, spacing and icon; a table cell's colour; a
hint's line and colour; every compact field at 32px; a disabled main action's
ground and opacity; a toggle's track against its row; the face of `<code>`.
It was run against the kit as it stood before the change and failed there.
