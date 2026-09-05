# The commands of a panel belong to the panel

## Problem

Three things a panel offers were drawn by the chrome around it rather than by
the panel.

**The icon of a tab was a button.** `WorkspaceLeaf` drew the icon as a pressable
element wherever the look carried an `iconTooltip`, and pressing it called
`onIconClick` in `WorkspacePage`. That function handled some kinds and not
others, so `chart`, `relationships`, `query` and `result` had a tooltip, the
hover state of a button, and nothing at all behind the press. The handover note
of 2026-09-05 recorded this and named the two ways out: give every kind an
action, or let the look say that an icon is not a button.

Nothing sensible was available for the first way. A chart is drawn from a page
of rows and is not a view of a node. A diagram is drawn from several nodes at
once, so there is no one node to be shown. A console is written against a
connection. A captured result outlives the query that made it and names no node
of any source. Four kinds had nowhere to go because they are genuinely not
views of a catalog node.

**The reload was a second button on the tab.** A tab is small, and two
pressable things inside one — plus the cross — put three targets in a strip
where the ordinary gesture is to press the tab itself.

**A detached panel grew a strip of its own.** `WorkspaceFloatingPanel` drew
"Return to panel", the panel's icon and a reload above the panel — a second row
of buttons over a panel that already draws one, and one of those buttons was
the dead press described above, now with a label.

## The rule

Everything a panel offers about what it is showing lives in the panel's own row
of commands. The tab says what the panel is; it does not act on it.

That gives each of the three a place:

- **Reload** — first of the three, saying in the panel's own words what
  re-reading means: "Re-read this table", "Re-read this level", "Reload the
  list of connections". First so that the freshness badge has a fixed place
  against it; see the last section.
- **Show in catalog** — a crosshair, for a panel that is a view of one node. A
  panel that is a view of no node draws no button rather than one that does
  nothing. Which panels those are is decided by whether they can name a
  connection and a node, not by a list of kinds.
- **Return to panel** — only while the panel is in a window of its own. Last of
  the three, so tearing a panel off and putting it back does not move the
  buttons beside it.

The one thing left on a tab is the icon of a catalog, which opens the connection
behind it. It stays because it is not a command about what the panel shows: the
connection is not reachable from the catalog's own row, while every other tab's
icon led somewhere that row now reaches.

## What holds it apart

`PanelLook` used to say "this icon is a button" and "this is its hover text"
with one field, which is exactly how a tooltip came to imply a press. The two
are now separate: `iconTooltip` is hover text, and `iconCommand` says the icon
acts. A tab that carries text and no command is an icon with a tooltip, and a
kind cannot acquire a dead button by gaining a tooltip.

The engine lost `onReload` altogether. It draws no reload button anywhere, so
knowing how to reload is no longer its business; the registry in
`features/workspace/reloadable.ts` — which panels already register into — is
now also what presses. The button and the answer are on the same side.

`PanelCommands` is one component, dropped at the end of whatever row a panel
already draws. Where a panel had no row — structure, details, a row view, a
chart, a diagram — it gains a thin one. Where a panel had a grid, the row is the
grid's, reached through a forwarded slot for the same reason the pager's row is
forwarded: what a panel offers about itself is not the grid's business.

Mounted outside a workspace, `PanelCommands` draws nothing. Every panel has a
unit test that mounts it alone, and there is no tab to return to and no look to
read in that setting; drawing none of itself is honest, drawing half of it is
not.

## Consequences

Two buttons that had claimed a command and answered nothing now answer it: a
row view and a captured result say how they are re-read, which they never did.

One behaviour is gone rather than moved. A tab restored from storage and never
opened had a reload button on its tab, and pressing it showed the tab, because
a panel that has never mounted has registered nothing. The button is inside the
panel now, so a tab that has not been shown has no button — showing it is what
reads it, and there is nothing left to press first.

## The clock and the reload

The freshness badge of D105 was the reload as well: one control answering "is
this stale?" and doing something about it, because a badge that only reported
left somebody hunting for the button. That reasoning held while there was no
button. Once every panel gained a reload of its own, a source with a cache had
two controls that both re-read it — a badge saying the rows were four minutes
old and a refresh beside it — and the badge was a smaller shape than everything
else in the row, so it read as debris rather than as a command.

The report is now a mark riding above the reload: the word "Live" while the
answer is the read, a small clock once it is one that was kept. Where the
source keeps nothing there is no mark, because nothing it shows could be older
than the read.

**It stands beside the button, not over it.** Three arrangements were tried
before this one, and each failed for a reason worth keeping:

- a badge of its own in the row — a second control doing the same thing, in a
  smaller shape than every button around it;
- the age written on the reload as a label — a command whose width follows the
  age of a page, so the row moves while it is being read;
- a mark floated over the button's corner — drawn on top of the arrow, and
  pushed far enough out to clear it, on top of the next button.

So the mark takes room of its own, beside the button and raised to its top
edge, with one width in both states. Nothing is drawn over anything, and
nothing in the row moves when a read stops being live.

**The age is not drawn.** The mark answers one question at a glance — may this
be stale — and how stale is a question, answered by hovering the mark. The
button beside it adds what pressing it does. Whether this may be stale is a
glance; how stale is a question.

The mark is a label and not a control: it presses to nothing and never looks as
though it would. "Live" lasts five seconds instead of one, because a mark this
small is caught out of the corner of an eye.

Where the freshness comes from is the only new plumbing. A catalog panel owns
its level and hands its own answer over. A grid owns the query — which page,
which filters — so it owns the answer, and the tab owns the row of commands: the
grid exposes what it read and the panel passes it on. Neither asks a second
time, because a second read is a second cache to fall out of step with the
first.
