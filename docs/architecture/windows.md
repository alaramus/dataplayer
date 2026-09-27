# Floating windows

The window engine, the forms that open in it, and how a window is put aside,
maximized or detached from the workspace. The panel engine and the columns are
in [workspace.md](workspace.md); the component kit is in
[frontend.md](frontend.md).

Decisions here: D14, D92, D93, D132, D155, D167.

## What exists today

A connection is edited in a floating window, and several are open at once. The
same application-level host owns every transient form and question: catalog
actions, row and column editing, full cell values, the download form, sharing,
the accounts form, the source-type catalog that begins **New connection**, and
confirmations. Nothing in the application is modal, and the modal dialog was
removed from the component kit rather than left in it — a rule nobody can reach
for is one that holds itself up.

On opening, the front window takes keyboard focus on its named frame unless its
content has already focused a field; background and minimized windows do not
take focus while mounting. Closing returns the keyboard to the control that
opened the window, which used to be left on the page body (U12) — but only when
the window being taken away is where the keyboard still was. The control is lit
only for the keyboard: after a mouse click Quasar's focus wash stayed on it until
somebody clicked elsewhere, so theme.css holds the wash back until
`:focus-visible`.

A window is closed by the cross in its bar, and no window holding a form closes
on Escape: one gesture for the connection window and for a form is worth more
than matching what a modal used to do. A question is the exception, added after
an audit found it. It holds nothing a press could lose, so a window says for
itself whether Escape may dismiss it, the question presets say yes, and Escape
then asks to close exactly as the cross does.

```
frontend/src/shared/windows/   geometry.ts is pure; the frame and the host see
                               one injected context
```

## D14. Work opens in floating windows, and there may be several

Not modal, and that is the requirement rather than a detail: the reason for the
window is to read one connection while filling in another. What modality would
have given — that an unfinished form cannot be walked away from — is replaced by
asking before a window with unsaved changes is closed. `shared/windows` knows
nothing about connections, the same split that keeps `shared/workspace` free of
any knowledge about panels.

Inside, the layout follows a database tool: the name on top, host and port on
one line because the options model says they are one address, and the
server-composed connection string pinned above Test Connection and
OK / Cancel / Apply. A new connection opens named after its type and addressed
to localhost. A stored secret shows as `<hidden>`, empties the moment the field
is entered and comes back if it is left untyped-in. A connection check shows
its result in a small popup anchored above Test Connection, leaving the form's
layout intact. Clicking outside or pressing Escape dismisses it.

Three things the old application's window engine got wrong are inverted here: a
z-index counter that only ever grew is now a position in a list; geometry
mutated in place is now pure functions whose result is assigned; and no clamping
at all — a window dragged past an edge could not be recovered — is now a rule
applied on every move and again when the viewport shrinks.

Consequences:

- **A window is identified by what it shows**, so asking for a connection that
  is already open brings that window forward. Two windows of one row are two
  unsaved edits of it, and whichever is saved second wins silently. Drafts have
  no row to overwrite, so any number may be open.
- **An action's form is a window of its own.** A second action from the catalog
  menu opens a second window rather than replacing the first one's contents. The
  pair — the action and the nodes it was opened on — identifies it, so the same
  line pressed twice brings nothing new, and each form keeps its target while
  the ticks below move on.
- **What a window is is not what it is addressed by.** Saving a draft renames
  the window to the connection it created, so a second Apply updates rather than
  duplicates; the list is keyed by a separate immutable key. Keyed by the address
  instead, the window was destroyed at that moment and rebuilt: the form reset
  itself, and the close that followed the save reached an instance that no
  longer existed.
- **A new window opens in the middle of the screen.** At a corner it lands on
  the column it was opened from and covers the control that opens the next one.
- **The server says how the form is laid out.** `layout()` on a field names its
  tab and the row it shares. Left to the screen, the rule that a host and a port
  are one address would be inferred from a port being a number, in a component
  that knows nothing about addresses.

Known deviations:

- **The original D14 spec describes an inline connection check panel.** The
  result now opens in an anchored popup so it remains readable without
  moving the connection form.
- **Windows do not survive a reload.** The workspace layout does; a window does
  not, because a half-filled form restored without its secrets would promise
  more than it holds.
- **A window can cover the application's header**, lying over Sign out until it
  is moved away. The price of the window engine not knowing the height of the
  chrome above it; it cannot be lost, which is what the layer was changed for.
- **The tab strip inside a window has never been seen.** Both source types put
  everything in one group, and one tab is not a choice, so the strip does not
  render — that half of D14 is unproven in a browser.
- **A window reopened does not return to where it was.** It joins the cascade
  again.

Spec: [The connection window: floating windows and form layout](../decisions/2026-08-23-connector-window-design.md)

## D92. A window can be put aside without losing its contents

Every window offers Minimize, Maximize or Restore size, and Close;
double-clicking the title bar also toggles maximization. Maximization fills the
viewport above the application footer — an application window state, not the
browser's fullscreen mode. The layout reports its measured footer height to the
window manager, so the engine knows an inset rather than what the footer holds.
Minimization hides the frame and keeps the component mounted.

The footer lists every open window, not only the ones put aside, in one
horizontally scrollable row beside the status commands rather than in a second
row of its own: it is a desktop taskbar, and a bar that appears and disappears
as windows are minimized moves the rest of the footer under the pointer. A
window is on it by its current title and icon from the moment it opens, in the
order the windows were opened — the manager's own list is in stacking order and
rearranges as one window is focused after another. The window being looked at is
marked; its button puts it aside, any other brings it to the front, as does
opening its existing id again. Each button also closes its window, through the
same question the cross asks. A minimized maximized window returns maximized,
and hidden windows never claim to be the front window.

The normal rectangle and the automatic fitting preference survive both
operations. Hidden and maximized windows accept no dragging, resizing or content
fitting; restoring normal size makes the saved rectangle reachable in the current
viewport. Maximized geometry follows browser and footer resizing without
overwriting that rectangle. All of it is held in memory until the window closes
or the page reloads, and the close confirmation still applies.

Spec: [Minimizing and maximizing floating windows](../decisions/2026-09-04-window-states-design.md)

## D93. Detaching moves the live panel into an application window

**Open in a window** is the last button of a panel's own row of commands, after
reload and Show in catalog (D112): pressing it removes the tab from its section
and opens it in the window manager. In the window the same button reads
**Return to panel**, so the way back is where the way out was. The fixed
connections panel stays in the workspace and draws no such button, as D112 draws
no Show in catalog where there is no node; a tab that could leave but cannot
right now has it greyed, with the reason.

Carrying a tab to the application header used to be the gesture, with a window
outline to drop on. It was removed: nothing on screen said the header would take
a tab, so the command was found only by somebody who already knew it. A tab
carried out of every section now simply goes back.

Panel instances belong to the workspace, with one `<KeepAlive>` per panel and a
`<Teleport>` to the active section or window target, so moving between targets
preserves the editor, grid state and registered close and reload callbacks.
Hidden panels stay cached but deactivated, minimized detached panels included.
Closing removes the instance through the panel's close guard.

A floating panel offers Return to panel beside its reload and icon actions.
Return restores its original section and position when it can, otherwise a
section accepting the same role; if that role has no section left, one is added.
Reopening a detached panel raises its existing window, and catalog focus follows
a floating catalog as well as a docked one.

Detachment and window geometry last for the page session. The persisted layout
holds the detached panels docked back into their return destinations, so
reloading preserves open tabs without restoring transient windows.

Spec: [Detaching a tab into a floating window](../decisions/2026-09-04-detached-tabs-design.md)

## D132. Changing content does not resize a stable window

`sizing: "stable"` distinguishes a stable window from a content-sized simple
form; omitting it keeps content fitting. A stable window opens at a preferred
size bounded by the viewport, and tab changes, loaded data and validation
neither resize nor recentre it: excess content scrolls inside the body while
title, tabs and footer stay reachable. Manual geometry survives tab changes and
maximize/restore, and manual resizing ends content fitting under either policy.
A viewport that shrinks constrains a stable rectangle again. Nothing is
persisted across sessions.

A content-sized window opens at a content-measured height and follows content
that appears or disappears inside it, bounded by the viewport, and can be
resized from every edge and corner. Repeated questions use presets in
`shared/windows` rather than restating deletion and question geometry in each
feature.

The connection editor is the first stable participant, keeping its preferred
560 by 660 rectangle with the name and tabs outside the scrolling body.
`WindowDialog` also accepts `sizing`: SSH key creation and import use its `form`
preset, 560 by 580, stable, with a scrolling body above footer actions, while
unlocking stays content-sized.

Known deviations:

- **Other variable-content forms still use their existing policy.** The saved
  example demonstrates appearance, not stable geometry.

Spec: [Neutral window design and stable sizing](../decisions/2026-09-13-window-design-and-sizing.md)

## D155. A window whose contents can live as a workspace tab says so in its bar

Some windows hold something worth keeping beside the work rather than a form
being filled in. Such a window declares the move with one preset,
`openAsTabAction` in `shared/windows`, in the `actions` slot D112 added: the
engine draws the icon and calls what it is given, and the feature's `run`
opens the panel through the workspace and closes the window — a move, not a
copy. `WindowDialog` takes the same `actions` prop, so a dialog declares it
the way a hand-built window does, and shows the command only where a workspace
is provided to receive the tab.

Two panel kinds hold what moves, both in the column of work. A `widget` panel
carries the whole widget with the range and interval of the moment the window
was opened: the tab keeps the window's snapshot semantics, so a widget changed
or removed on the dashboard does not reach it, and two windows of one widget
are two tabs, the id carrying a fresh suffix. A `service-logs` panel carries
the service's id and name and reads the output again whenever it is shown; the
question has one answer, so the tab is one per service and asking again brings
it forward. The first participants are the detached dashboard widget and the
service output dialog.

Spec: [A window whose contents can live as a workspace tab](../decisions/2026-09-22-window-to-tab-design.md)

## D167. Two catalogs of two connections share a window with what goes between them

A pair is made in two steps, by a catalog's own **Pair** command. The first
press only remembers the catalog — a waiting pair in the header, with the
connection's name, a list of the other connections and a cross — and the
catalog stays where it was. The second catalog's Pair, or a connection chosen
from that list, opens the pair window. The button says what pressing it would
do: pair with the waiting one, or wait. Another catalog of the waiting
connection has its Pair greyed with the reason; a new first press from another
connection replaces the waiting one; closing the waiting catalog forgets it.
Carrying a catalog tab to a Pair target in the header was the first way and is
gone with D93's header target.

- **The engine knows a group, not a pair.** `detach(panelId, group)` tears a
  panel off into a group whose window the feature draws; the engine's own
  floating windows skip grouped panels, and docking and persistence treat them
  as any detached panel. `WorkspaceRoot` has a `windows` slot inside the panel
  host, where the feature's windows register their panel targets.
- **The window** holds the two catalog panels, alive, and swaps them from its
  bar. A paired catalog hides its actions menu and ×2: what is done in a pair
  is done from the pair's bar. Closing the window docks both where D93 would. A catalog that leaves by any
  other way — closed with its connection — takes the pair apart. Asking for a
  paired catalog brings its window forward. Pairs last for the page session.
- **The bar** is one, and always runs left to right; Swap sides is how the
  other direction is reached. It asks `POST /connectors/pair/offers` with the
  left side as the source and the right as the destination — place and ticks,
  published by each catalog panel — and lists D164's offers in both verbs: the
  left ticks into the right place, or its one tick. With nothing ticked on the
  left, each kind that goes that way is listed with what to tick, in the
  kind's own words. A button opens the windows a Paste of the same offer
  opens and runs `/paste`; the catalogs of both connections re-read
  afterwards.
- **No dragging between the two catalogs.** It was planned as the next step
  and dropped: the bar, turned round by Swap sides, is the one way to act in
  a pair, and a drop would be a second, less visible route to the same offers.

Spec: [Two connections side by side](../decisions/2026-09-25-paired-catalogs-design.md)

