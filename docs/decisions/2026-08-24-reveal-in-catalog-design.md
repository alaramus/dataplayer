# From a table tab to its catalog

Date: 2026-08-24
Status: agreed
Round: 7c

## Goal

Remove the connection name from the table tab and give that tab a way to the
catalog of the connection the table belongs to: the catalog opens if it was
not open, comes to the front if it was, and the node in it is highlighted.

There is no new decision: this is the same place in the tab contract as T5 —
the icon calls what the application provided. Only what it calls for a table
tab changes.

## What is lost and where it goes

The connection name is not in the tab for decoration. The right column holds
tables from different connections at once, and two `users` from two databases
are indistinguishable without it. So it does not disappear but moves into the
icon's tooltip: `prod-db · Show in catalog`. A tooltip is needed anyway — the
icon now does something other than before.

## Decisions

### R1. The table tab's icon leads to the catalog

`lookOf` for `rows` loses `subtitle` and gets a tooltip with the connection
name. The catalog tab's icon still opens the edit window.

Rejected: a third button next to reload: the tab already has an icon, a title,
reload and a cross, and the connection's edit window is reachable two more
ways — the catalog tab's icon and the list of connections. "To this table's
catalog" is the only move that exists nowhere else, and a source icon leading
to the source's catalog reads by itself.

Rejected: a double click on the tab: the gesture is invisible, and a touch
screen does not have it.

### R2. Showing means opening or coming to the front, plus marking

`revealInCatalog(connectorId, nodeId)` in the workspace actions:

1. find the connection in the list; none — nothing (it was deleted); disabled —
   the same refusal as for an ordinary open;
2. `openCatalog(connector)` — the engine itself brings an already open panel to
   the front, so "open or go to" is one and the same action;
3. put the target `{ connectorId, nodeId }` into screen state.

`CatalogPanel` sees the target, recognises its own connection in it,
highlights the node if it is on the shown level, and clears the target. A
target rather than a direct call to the panel: the panel may not be mounted
yet — it has only just been opened.

Rejected: a second registry next to the reload registry: highlighting is not a
panel command but screen state, and a watch on it survives mounting, which a
call would not survive.

### R3. The highlight is an outline, and it fades by itself

The catalog already has marks — checkboxes, and they mean "an action will be
taken on this". The highlight means "here it is", which is something else, and
as a fill it would be confused with a mark.

The outline lasts three seconds and fades. The first wording said "until the
level changes" — that is wrong: an outline that lasts indefinitely stops
meaning "here it is" and starts reading as a row state, that is, as a second
kind of mark next to the checkboxes. Three seconds are enough to catch the eye.
Leaving the level clears it early if one leaves sooner.

It fades smoothly: the outline is declared transparent on every row, and the
class changes only its colour — a colour cannot transition from a rule that has
already been removed. The outline takes no space, so it costs nothing for rows
without the mark.

The fading itself is `useFadingMark`, a separate composable: time is checked
with fake timers and without mounting.

### R4. What we cannot do and do not pretend to

Only a node that is on the shown level can be highlighted. Usually it is there —
that is where it was opened from. But if one has gone into another folder or
reloaded the page, jumping to the node's level is impossible without parsing
its id on the client, and parsing server strings on the client is what the
project does not do. Then the catalog simply opens, and there is no highlight.

The right solution is an adapter capability "path to a node": the source knows
how its own ids are built, the client does not and must not. That is a separate
round.

## How it is checked

- `lookOf` for `rows`: no subtitle, the tooltip names the connection;
- `CatalogList`: the row with the given id carries the mark, the others do not;
- `useFadingMark`: shows at once, clears when the time is up, a second show
  restarts the countdown, removes the timer together with the scope;
- Playwright: with a table tab open, a click on its icon brings the catalog of
  the same connection to the front and highlights the row, and after a few
  seconds the highlight goes away; with the catalog closed — opens it; for a
  disabled connection — refuses the same way an ordinary open does.

## What this round does not include

- going to the level of a node that is not visible;
- highlighting in the other direction — from the catalog to an open table tab;
- remembering the highlight across page reloads.
