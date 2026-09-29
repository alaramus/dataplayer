# The UI audit and its corrections

Date: 2026-09-28. Decisions: D185, D186.

## The problem

A visual audit of the whole frontend — every CSS rule of 238 components read
by a script, and every screen measured in a browser in both themes at 1440,
1024, 768 and 390 pixels — found the spacing, the corners in CSS, the colours
and the layers already on tokens. The drift was elsewhere, and most of it had
one cause: the kit had never told Quasar what the application's scale was.

- The chrome was 13px; every button, every field value and every floating
  label was Quasar's 14px or 16px. A form row carried three sizes and three
  colours of text.
- A button was 36px beside a 32px field, a toolbar field 40px, and a button's
  corner 3px beside every other corner's 4px.
- Quasar styles `h1`–`h6` as a document's headings. Eighteen headings of the
  chrome set their own size and kept Quasar's line: DRAFTS in the queries
  panel stood in a line of 50px, and the scene's title in one of 96px.
- `--dp-font-ui` named Inter, which was never shipped; the application drew in
  Segoe UI on Windows and in something else elsewhere, and Inter is about ten
  per cent wider, so widths tuned on one machine did not hold on the next.
- Twelve literal sizes of text, from 9px to 24px; fifteen overlines in three
  sizes and five letter spacings; eight sizes for three levels of heading;
  weights of 400, 500, 600 and 700 without roles.
- Nine icon sizes, with Quasar's 24px glyph in every 32px button on a 13px
  line; a compact button of 18px whose icon was 13.7px.
- Monospace at 12px in the editor, 13px in the grid and 14px in the log.
- Body text #000, a field's value at .87 and a colour called strong at .7,
  weaker than both; muted text written with `opacity` in one window; the faint
  colour, 2.4:1 on white, used for text a person had to read.
- A focus ring in four colours by three mechanisms.

## D185. Type, geometry and icons are one scale, and Quasar is told it

**The scale lives in metrics.css and is said again in quasar-variables.sass.**
`$button-font-size`, `$input-font-size`, the field label and hint sizes and
`$badge-font-size` take the scale's values; `$button-border-radius` takes the
control corner; `$button-line-height` is 1.5385em and `$button-dense-padding`
.4615em, which at 13px are a 20px icon and 6px of padding — a dense button is
32px, and a compact one shrinks with its font. A button's floor of 2.572em is
replaced by the control height. Rejected: overriding Quasar's classes screen by
screen, which is how the drift arose, and swapping Quasar's CSS for our own,
which would mean maintaining it.

**Roles, not sizes, in screens.** The sizes are tokens, and the roles text
plays most often — the overline, help beside a control, a count or caption,
a section title, a page title — are classes in `typography.css`, so a screen
says which role a piece of text has. A component that restates a size in
pixels fails `typography.spec.ts`. Rejected: a component per role, because
the overlines stand in `h3`, `dt`, `span` and `div` alike and carry buttons
after them; a class is the smaller change.

**Lines in pixels.** The body's line is 20px and is inherited as a length, so
a row of 11px text is as tall as a row of 13px text and lands on whole pixels;
the old 1.5 made a catalog row 23.8px. Text that wraps at a small size takes
the 16px line of its role.

**Inter is shipped** from `@fontsource-variable/inter`, the weight axis and its
italic, subset by Unicode range so only the scripts on screen are fetched.
Rejected: dropping Inter for the system face — the drawn look would still
differ between systems, which is the problem.

**Three text colours.** `--dp-text` at .87 is the colour of everything read,
the body, a field, a heading, a tooltip and code alike; muted rises from .54
to .6, 5.5:1 on the grey heads of cards where .54 was 4.4:1; faint stays for
marks that are not text. The strong token is removed: it was the weakest of
the three, and a grid's column names were lighter than the values under them.

**Current and resting tabs.** The tab being read is filled with its
connection's colour and the others carry the colour's quiet half, the one
`panelColor.ts` already mixes for the connections list. Filled alike, the two
tabs of one connection differed by a 3px line in the colour of the panel
under them.

## D186. A state and a pattern are drawn one way

Beside the scale, the audit found the same state drawn several ways: the main
action first in one window's footer and last in the next; six ways to show the
current item of a list — a connection's colour, a 3px line, grey, dark, blue
and a blue text; secondary and quiet buttons a shade apart; a red bin on every
row of some lists and a neutral one in others; two kinds of card; menus and
tooltips drawn by two systems; an editable type in a table heavier than the
column name beside it; a command row cut at its edge with no sign of more; a
chip and a count drawn over each other in a narrow catalog.

Each is one rule now (the architecture file lists them). Two readings were
weighed and set aside:

- **Removing Minimize and Maximize from questions.** Every window has them by
  design, and a question put aside to look at what it asks about is the reason
  nothing is modal. The audit's point was noise; the answer is smaller window
  controls, which D185 gives.
- **A brighter border for the window in front in the dark theme.** D131 marks
  the front window by its shadow and names a brighter border as the rejected
  alternative; the audit's weaker separation on dark is recorded as a known
  deviation rather than reversed here.

The grid's row of commands keeps the rule that nothing folds away: it scrolls,
and now says so with a shadow at the edge. An overflow menu was rejected for
the reason the rule gives — every command keeps the place it was given.

## What was checked

The audit's measurements were taken again after the change: buttons and fields
13px, 32px high, corners 4px; icons 20px in controls and 16px in rows; no
heading with a line past its role; the face measured as Inter. The unit suite,
the type check, lint, the build and the Playwright scenarios that measure
layouts were run.
