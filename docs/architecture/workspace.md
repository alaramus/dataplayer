# The screen: sections and tabs

The panel engine, the three columns built on it, the drag gesture that moves a
tab, the bar at the foot of the screen and the card above it. Floating windows
are in [windows.md](windows.md); the component kit and the screens themselves
are in [frontend.md](frontend.md).

Decisions here: D12, D69, D94, D112, D143.

## What exists today

One screen of three columns: the connections; the catalog of every connection
that was opened, where the same words filter a level and, on a button, search
everything below it; and the work opened from a node, in tabs beside each other.
The connections head can temporarily become a full-width name filter; closing
it clears the filter and restores the head commands.
Work may be rows, editable source, bounded media, read-only SQL, relation
structure, what a node is, or a chart. Columns are resizable and bounded by the
window so each scrolls inside itself, and the layout a user arrives at is the
one they left. A column appears together with what goes in it; the right-hand
one, while empty, says what to do next and offers the button that does it.

The workspace sits inside one inset frame between a compact application toolbar
and a status line. Its panels spend the same surface, border, tab height,
spacing and radius tokens, and separators keep a wide pointer target around a
one-pixel line, so the chrome reads as one tool rather than a row of unrelated
cards. The tokens are the stable part; the final polish is not settled.

A tab is carried the way a browser carries one: it leaves its strip and follows
the pointer, joins the tabs of another column by being dropped on their head,
and divides a column by being dropped in its body. It can only be taken to a
column that takes its kind. Each closable tab exposes a separately named close
control in the Tab sequence, where Enter and Space request closing through the
panel's close guard without activating or dragging the tab.

**Tool rails.** Four narrow rails flank the columns, a top and a bottom half of
each side. They hold what hangs off no panel — the space switch, the query
library, services, saving and opening tab groups — as icon-only blocks, and a
block is dragged elsewhere in its rail or onto another rail. Where each stands is
kept per browser; a block the stored arrangement does not name takes its home, or
its place beside the block it belongs with. The blocks are one registry,
`toolBlocks.ts`: a new one is an entry there and nothing else. The Services block
switches a tool in the panel at the foot of the screen (D143).

```
frontend/src/shared/workspace/
              the panel engine: a layout tree, tabs, drag and drop, sections
              that carry a role, admit what matches it and outlive their panels.
              tree.ts, dropZone.ts, placement.ts, shares.ts, visibility.ts and
              persist.ts are pure; the components see one injected context

frontend/src/features/workspace/
              the panels, the registry that names them and the role that puts
              each in one of the three columns; the scene that stands in the
              empty one. scene.ts, activeCatalog.ts and toolRails.ts are pure
```

## D12. The screen is a workspace of sections, and the engine knows nothing about the application

A layout is a tree of sections; every change to it is a pure function; a section
is a list of panels with one active, and that is the only notion of a tab in the
application. What a panel is belongs to `features/workspace`, which hands the
engine a component and a look per panel.

The look may carry a `color`, read from the connector's saved `tab_color` in the
query cache rather than copied into each panel, so saving or resetting a colour
updates every open tab of that connection. Query and result panels carry their
connector identity for the lookup; older layouts stay readable without it, and an
old query panel acquires it when its document loads. The engine applies the look
to tabs, drag previews, floating title bars and minimized windows without knowing
what a connector is.

Consequences:

- **A column is a role, not a place something was dragged to.** A section carries
  `accepts`, the role of panel that lands in it, and `pinned`, which keeps it on
  screen when the last thing in it closes; the engine compares the role and never
  reads it. That makes the screen three columns that are always there while
  leaving the engine ignorant of what a column means, and makes a source type
  that brings its own view a new kind with an existing role rather than a change
  to the layout.
- **Two views of one node are two panels.** A JSON content panel and its explicit
  table projection share a source node but not an identity, request contract or
  component. Both use the existing `work` role, so native content changed the
  feature registry and not the engine. Opening one again activates its own tab;
  asking for the alternative leaves the first view beside it.
- **A role is also what a section will take.** A panel may only be dragged into a
  section whose role matches. A section split off another inherits its role — or
  the first split would make a corner of the screen that takes nothing — but not
  `pinned`, which belongs to a column rather than to every section. A side that
  would leave the target holding nothing is offered as its centre instead: one
  rule covering both the only tab dragged to its own edge and anything dragged to
  the edge of an empty section. Where a drop is refused, nothing is highlighted.
- **An empty column is not rendered.** A pinned section with no panels and no
  empty view leaves the row. Its `sizes` entry stays in the tree, so its width
  returns exactly as the user left it. Its share goes to the sections after it,
  in proportion to their current widths — forward, so the narrow connections list
  keeps its width when the catalog beside it goes; in proportion rather than
  whole to the next column, because same-direction splits are flattened into one
  and that column would then be a single work card holding room freed by somebody
  else, which could never be dragged narrower. The fixed pixels it frees, its gap
  and the two edges of its card, go to the first section after it as a fixed part
  of that section's width, so what is left to divide is the same either way and
  the columns in front do not move. `pinned` holds a role, not a section: a column
  left empty while the section split off it holds the work goes too. Column heads
  are one height whatever they hold, or the line under two columns reads as a
  broken layout rather than an empty one. Only the right-hand column has an empty
  view, the scene, which derives its stage from the connections list and the
  catalog being read.
- **There are as many catalogs as were opened.** A connection's ordinary catalog
  opens once; its Duplicate command creates another panel immediately to its
  right, starting at the same level. Each copy has its own navigation, filter
  and selection. The pair borrows width from the work column when there is
  room, so both folders remain readable. A source action refreshes the other
  open catalogs of that connection, so moving a file updates both visible
  folders. Which catalog is being
  read is asked of the tree — the sections that take `navigate`, the focused one
  first, its active tab — rather than kept beside it. The list of connections has
  two states, open and being read, said with two strengths of one highlight.
- **A tab is carried, and where it is dropped says what it means.** Pressing a
  tab does nothing until the pointer has moved far enough to mean it; from then
  the tab is gone from its strip and a copy follows the pointer. A section is two
  targets: its strip puts a panel beside the ones already there, its body divides
  it, and in the body the nearest edge wins with nothing neutral in the middle.
  The highlight shows where the panel will end up — the strip, the half it will
  occupy, or the whole of an empty section — rather than which zone the pointer
  is in.
- **A column pushed aside may keep something on screen.** The engine knows the
  section is narrow and asks the feature what is worth that width, the way it
  asks what stands in an empty one; only the connections answer, with their icons
  and state dots. Closing every tab but the active one is the engine's too — it is
  a layout operation — and it leaves a panel the feature says has no cross.
- **A panel alone in its column by design may take the head instead of a tab.**
  The engine asks the feature what a section holding only that panel shows in its
  head; only the connections answer, with making one on the left and re-reading
  the list at the end. Their column takes no other role and the panel can be
  neither closed nor carried, so the tab named the column and gave nothing to
  press. The rail of the collapsed column wears the same head, so pushing it aside
  still moves nothing.
- **A column with nothing worth that width leaves the screen instead.** The same
  answer picks which of two gestures a section head offers: something worth forty
  pixels narrows to them, nothing worth them goes whole to the bar at the foot of
  the screen (D69), where the feature's name for its role stands for it and leads
  back. A column holding nothing offers neither — it is on screen to say what can
  be opened in it. A section on the bar keeps its panels, its active tab and its
  share of the row, and the engine reads it as holding nothing. Anything opened
  into a section brings it back, or opening a table into a column on the bar would
  do nothing anybody could see.
- **Every section is a card**: its own ground, edge and corners, and between two
  of them the space that is also the handle that resizes them. One frame around
  the lot with hairlines inside it made three columns read as one table. The gap
  is the width of the inset the workspace already sits in, so the distance between
  the cards and the distance around them are one number.
- **A tab that is not showing is kept, not destroyed.** Switching away and back is
  no reason to re-read a catalog or lose the page a grid was on, so the workspace
  keeps each panel in its own `<KeepAlive>` and moves its rendered contents
  between section and window targets (D93). One requirement on the feature:
  `component(panel, key)` must answer with the same component for the same key. A
  wrapper built afresh on each call is a different component every time, and a
  functional wrapper cannot be kept alive at all. The cache of them is made with
  the workspace, because keys start again when it is mounted again — kept for the
  module, it showed one tab's panel under another's after a trip to Preferences.
- **A panel is not addressed by what it is.** A panel id may change: a console
  that is kept becomes a document and is addressed by that document. So the engine
  hands out a key of its own that survives the rename, and `replace` writes the new
  fields into the panel object rather than putting another object in its place.
  Keyed by the id, being kept rebuilt the panel — the results in it and a
  half-answered parameter went with it. Windows have the same rule.
- **A tab offers what the feature named, and the engine calls it back.**
  `iconTooltip` with `onIconClick` is how a catalog tab opens the window of its
  connection; `reloadTooltip` with `onReload` is how a tab is re-read. The engine
  draws the button when the feature named it and calls back with the panel id.
  What re-reading means belongs to the panel — the connections list asks vue-query
  again, the catalog re-reads the level it stands on, the grid re-runs the page it
  shows — so panels register their own answer in a small registry and the engine
  never learns what a catalog is. Instance refs held by the engine are the
  coupling this prevents.
- **A strip of tabs says that it is one.** The engine draws a `tablist` whose tabs
  say which of them is showing, and the arrows walk it. As a row of buttons it
  said nothing about what it was, nothing about which tab the screen was showing,
  and Tab walked through every tab and every close button to get past it (U09).
  Only the tab being shown is in the tab order, and the controls inside a tab —
  its icon, its cross — travel with it, so the strip is one stop rather than
  twenty. Walking is not choosing: Enter and Space open the tab walked to, because
  a panel reads its relation when it is shown and arrowing past four of them would
  ask the server for all four.
- **The cross asks the panel before it takes it away.** Closing is a request, not
  a command: the engine calls the same kind of registered answer as re-reading,
  and a panel with nothing to say is closed at once. Only a person's gesture asks
  — a layout operation the application performs itself, replacing a renamed panel
  or clearing a strip, closes directly, because it is not somebody changing their
  mind. The reason is a query console holding an open transaction, which would
  otherwise be rolled back by a lease five minutes after its tab disappeared
  (D66).
- **The icon of a tab does what that tab has no other way to do.** From a catalog
  that is the connection itself; from a table it is the catalog the table came
  from, reachable nowhere else — while editing a connection has two other ways in.
  The name of a data tab's connection is in the tooltip instead: the column is a
  fifth of the screen and the node is what the eye looks for.
- **Being pointed at is not being ticked.** A tick selects a row for an action;
  arriving from a table's tab only points at one. So an outline rather than a fill,
  cleared after three seconds, because one held indefinitely reads as a row state.
  Every row carries the outline transparent so it can fade: a colour cannot be
  transitioned out of a rule that no longer applies. The pointing travels as state
  the panel takes, not as a call — the panel may have been opened by the very press
  that asked for it and not be mounted yet.
- **A node is found wherever it lives, and the source says where.** The catalog
  asks for the path to the node and stands where the answer puts it — walking into
  the directory it is in, or ticking the schema it belongs to. Which of the two is
  read off the role of each node on the path, so nothing here takes an id apart;
  see D21. A source that cannot walk back up answers 501 and the catalog opens as
  before, marking the node only if it happens to be in view.
- **A panel that never mounted has nothing to re-read.** Only the active tab of a
  section is mounted, and `<KeepAlive>` keeps the ones that have been shown, so a
  tab restored from storage and never opened has registered nothing. Pressing its
  reload shows it instead, because reading a panel that never read anything is
  showing it.
- **Walking a catalog is not logic of a screen.** `useCatalogTree` holds it, and
  it invalidates the branch it re-reads rather than trusting whoever changed it to
  have done so.

Known deviations:

- **A refusal is visible only as the absence of a highlight.** Why a tab may not
  be brought here is not explained.
- **A hidden column is still in the tree**, showing in localStorage and in a
  layout test although it is not on the screen. That is what brings its width
  back, but "what I see" and "what is written" differ here.
- **A column off the screen with nothing after it leaves its room whole** to the
  one section before it, which then cannot be dragged narrower than that room. Out
  of reach in practice — it takes dragging the last border nearly across the
  screen — but it is the defect the rule above exists to avoid.
- **The connection named on a data tab is written when it is opened.** Rename the
  connection and the tab lags until it is opened again, as a catalog tab's title
  already did.
- **The scene knows three stages and no more.** A source that cannot be browsed
  never reaches it: the middle column does not appear, and nothing says so in
  words.
- **Tabs cannot be reordered inside a strip.** A tab dropped on a strip is added
  at the end, no caret is drawn between tabs, and dropped on its own strip it does
  nothing. A position in a strip would put an index into every tree operation.
- **The target that merges is a strip thirty-one pixels tall**, harder to hit than
  half a panel and narrow on a narrow column.
- **A collapsed column is still a target.** Its strip is forty pixels of handles,
  and a tab dropped there goes where it cannot be seen until the column is brought
  back.
- **What is in the hand shows only what a tab shows.** No picture of the panel:
  two tabs of one node from different connections are told apart by the source
  icon and, once hovered, by its tooltip.
- **The ghost hangs from the pointer, not from where the tab was grabbed.**
- **The threshold is three pixels for everyone** — the number the border between
  two columns uses, never measured against a touch screen or an unsteady hand.
- **The layout is one per browser.** It lives in localStorage, so it does not
  follow a user to another machine and is not shared between two windows.
- **A panel of a deleted connector stays until it is closed**, showing the error
  the server gave, because the panel cannot tell a deleted connector from a failed
  request.
- **A closed panel's component definition is still held.** The map of bound
  components in `features/workspace/panels.ts` keeps definitions for the page's
  lifetime; the workspace releases the component instance on close.

Spec: [The workspace and the panel engine](../decisions/2026-08-22-workspace-design.md)

## D69. The bar at the foot of the screen holds what hangs off nothing else

Almost every button hangs off the thing it acts on: a table's commands are in its
grid, a node's are in the catalog's menu, a connection's form opens from its row
or from the icon of its tab. A few have no such thing — a query console is written
against a connection and belongs to a person, so there is no node whose toolbar it
could live in. Those go in the bar at the foot of the screen.

Consequences:

- **One rule, in one place.** A command is enabled while a connection is being
  read and that connection can do the thing; otherwise it stays in the bar, greyed
  out, its tooltip naming which of the two is missing.
  `features/workspace/commands.ts` is that rule as plain functions, tested without
  mounting anything; `CommandBar.vue` only renders it.
- **Shape before content.** Hiding what does not apply would make the bar change
  as somebody walks about, which is a bar they have to read every time. The same
  reason the catalog's action menu greys out rather than shortens.
- **The bar does not repeat which connection it is about.** Two places already say
  it — the marked row in the connections column and the tab of the catalog being
  read — so a third copy only took room from the commands. Each tooltip names the
  connection instead, answering the doubt at the moment a button is aimed at.
  Which connection is read is `activeConnectorId`, derived from the layout tree
  rather than kept beside it.
- **What is open and not on the screen is on this bar too.** A window put aside
  (D92) and a column put aside are the same fact about the screen, so they are
  drawn as one shape, `AppTaskbarItem`, in one row. A column is named by its role
  rather than by its active tab: it is part of the window and not a document, and
  a button whose word changed as the tab behind it changed could not be aimed at
  twice. The words — "Navigation", "Data" — and the icon beside each are
  `sectionLook` in `features/workspace/panels.ts`, the one table to edit to rename
  a column; the engine only asks it, and a role it does not name is a column that
  cannot be put aside at all.
- **Whether a command applies is the source's own answer**, never a branch on the
  adapter type (D62). Copying a database out is the example: a driver that can name
  a program to dump it declares the capability, and one that cannot does not.
- **What acts on the open connection sits in that connection's menu.** Copying a
  database out is a line there, last of the client's own, drawn only for a source
  that declares the capability and greyed out with the server's reason when the
  machine cannot run a dump (D87). It is not in this bar, which holds what belongs
  to the person and to the server.
- **One button in that row is not a connection's.** The library of queries belongs
  to a person and outlives the connections in it (D65), so it is never greyed out
  with the rest: what it says changes — which connection it would open against, or
  simply what it holds — and pressing it always opens. It sits with them because
  that is where a person looks for it.
- **"Not asked yet" is not "no".** Three states rather than two, because half a
  second of "this source does not run queries" about a PostgreSQL connection is a
  worse answer than saying nothing.
- **The library opens filtered to the connection it was opened from.** The filter
  travels as state the panel takes, the way `revealTarget` and `followTarget` do:
  there is one library panel however often it is opened, and a panel's props are
  bound when it is first drawn.
- **What is about the machine stands at the other end of the bar.** The services
  this server runs belong to the person rather than to whatever is open, so their
  button sits apart from the connection's commands. It opens them in the panel at
  the foot of the screen (D143), empty or not, and while a job is working it says
  the step: once the window that asked for a service has closed, this is the only
  place a start is visible.

Known deviations:

- **The right half holds only the services.** What a status line is usually also
  for — what the last request cost — is still not said anywhere.
- **A disabled command explains itself only on hover.** The tooltip hangs off the
  slot around the button, because a disabled Quasar button takes no pointer events;
  on a touch screen there is no hover and therefore no reason.

Spec: [The bar at the foot of the screen](../decisions/2026-09-02-connection-command-bar-design.md)

## D94. Named tab groups restore a saved workspace layout

A group is an explicitly saved copy of the layout and panel descriptors:
sections, sizes, collapsed states, tab order and active tabs. Saving one and the
list of saved ones are two blocks on the tool rails. Opening or closing tabs
afterwards does not change the group; Update from current layout replaces its
saved copy. Saving and updating require an open tab beyond the permanent
connections panel; their commands are disabled when the workspace has none.
Groups can be renamed and deleted, and are stored per signed-in user
in this browser's localStorage. They hold no fetched rows or editor text and do
not copy per-table filters or other independently persisted feature state.

Opening a group replaces the current layout. A warning explains that the current
tabs will disappear and offers Don't show again; only accepting with the checkbox
selected persists that preference, and cancelling does not. The preference never
disables panel close guards: guards are asked before any panel is removed, and
refusal leaves the layout in place. Panels in both layouts keep their live
instances, tabs absent from the group close, and a changed set of panels during
confirmation cancels the restore.

Detached tabs are saved in their docked positions using D93's return rule, so
restoring closes their frames and places the panels back in the workspace.
Unrelated floating forms stay open. Saved data is versioned and validated before
use, including unique section and panel identities and role compatibility.
Storage failures are reported without pretending a group was saved.

Spec: [Saved tab groups](../decisions/2026-09-04-tab-groups-design.md)

## D112. What a panel offers about itself lives in the panel's row of commands

A tab says what a panel is; it does not act on it. Showing the panel's node in
the catalog and re-reading the panel are commands about what the panel shows, so
both stand at the end of the row of buttons the panel already draws. A panel with
no such row gains a thin one; a panel whose row belongs to a grid receives them
through a forwarded slot.

Reload comes first and says in the panel's own words what re-reading means. Show
in catalog follows, drawn only for a panel that is a view of one node and absent —
not disabled — everywhere else: a chart is drawn from a page of rows, a diagram
from several nodes at once, a console is written against a connection, and a
captured result names no node of any source.

Returning a detached panel is not one of them. It is about the frame rather than
what the frame holds, so it stands in the window's own bar beside minimize,
maximize and close. A window may declare commands of its own for exactly this;
the window engine knows the icon, the words and what to call, and nothing about
panels.

A small mark rides above the reload where there is anything to report: "Live"
while the answer is the read, a clock once it is one that was kept (D105). It
stands in room of its own beside the button, one width in both states, so the
arrow is never drawn on and the row never moves. The age is not drawn — a control
whose width follows the age of a page moves while the row is being read — and is
answered by hovering. The mark is a label rather than a control: it presses to
nothing and never looks as though it would. A panel whose source keeps nothing
shows the reload alone.

One icon on a tab is still a button: a catalog's, which opens the connection
behind it. It is not a command about what the panel shows, and the connection is
reachable from nowhere else on that panel.

`PanelLook` separates with two fields what it used to say with one: `iconTooltip`
is hover text and `iconCommand` says the icon acts. An icon was previously drawn
as a button wherever it had a tooltip, so four kinds offered a press with nothing
behind it. The engine no longer knows how to reload anything: it draws no reload
button, and the registry panels register into is also what presses.

Two consequences are deliberate. A row view and a captured result now answer the
reload they had always claimed. A tab restored from storage and never shown has no
reload button at all — the button is inside the panel, and showing the tab is what
reads it.

Spec: [The commands of a panel belong to the panel](../decisions/2026-09-05-panel-commands-design.md)

## D143. What is watched beside the work opens in a card at the foot of the screen

Some tools are watched while working rather than worked in: what the server runs,
and terminals ([D149](terminals.md)). A window covers the work and has to be
moved off it, and a column is a role panels are dragged to. So, as in an IDE, they
open in one card along the foot of the screen, between the rails and under
whichever space is shown.

Consequences:

- **One tool at a time, switched by its rail button.** Pressing it shows the tool,
  replacing another; pressing it again hides the panel, as does the button in the
  card's head. The rail button is drawn pressed meanwhile.
- **The button is always pressable.** An empty tool says it is empty; a greyed-out
  Services button left nobody able to learn where services live.
- **The height is dragged by the gap above**, like a column's width, and kept per
  browser with the open tool. The columns keep 160 px whatever was stored.
- **The tools are one registry**, `bottomTools.ts`; the state is `bottomPanel.ts`,
  pure, and `useBottomPanel`, shared by the button and the card.

Spec: [The panel at the foot of the workspace](../decisions/2026-09-18-bottom-panel-design.md)
