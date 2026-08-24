# The screen: sections, tabs and windows

The panel engine, the three columns built on it, the drag gesture that moves a
tab, and the floating windows that edit a connection. The component kit and the
screens themselves are in [frontend.md](frontend.md).

Decisions here: D12, D14.

## What exists today

One screen of three columns: the connections, the catalog of every connection
that was opened, and the rows of a node in tabs beside each other. Columns are
resizable and bounded by the window so each scrolls inside itself, and the layout
a user arrives at is the one they left. A column appears together with what goes
in it; the right-hand one, while it is empty, says what to do next and offers the
button that does it.

A tab is carried the way a browser carries one: it leaves its strip and follows
the pointer, joins the tabs of another column by being dropped on their head, and
divides a column by being dropped in its body. It can only be taken to a column
that takes its kind.

A connection is edited in a floating window, and several are open at once.

```
frontend/src/shared/
├── windows/     floating windows: geometry.ts is pure, the frame and the host
│                see one injected context
└── workspace/   the panel engine: a layout tree, tabs, drag and drop, sections
                 that carry a role, admit what matches it and outlive their
                 panels; tree.ts, dropZone.ts, placement.ts, shares.ts,
                 visibility.ts and persist.ts are pure, the components see one
                 injected context

frontend/src/features/workspace/
              the panels, the registry that names them and the role that puts
              each in one of the three columns; the scene that stands in the
              empty one, and scene.ts and activeCatalog.ts, which are pure
```

## D12. The screen is a workspace of sections, and the engine knows nothing about the application

A layout is a tree of sections; every change to it is a pure function; a section
is a list of panels with one active, and that is the only notion of a tab in the
application. What a panel is belongs to `features/workspace`, which hands the
engine a component and a look per panel.

The old application had such an engine and it grew to 2438 lines: nodes were
mutated in place and carried parent back-pointers, so undoing anything needed a
history of layouts and a command language of nine verbs, and a node it could not
remove had to be left in place marked `fake`.

Consequences:

- **A column is a role, not a place something was dragged to.** A section carries
  `accepts`, the role of panel that lands in it, and `pinned`, which keeps it on
  screen when the last thing in it is closed; the engine compares the role and
  never reads it. That is what makes the screen three columns that are always
  there while leaving the engine ignorant of what a column means, and what makes
  a source type that brings its own view a new kind with an existing role rather
  than a change to the layout.
- **A role is also what a section will take.** A panel may only be dragged into a
  section whose role matches it. A section split off another inherits its role, or
  the first split would make a corner of the screen that takes nothing; it does
  not inherit `pinned`, which belongs to a column rather than to every section. A
  side that would leave the target holding nothing is offered as its centre
  instead — one rule covering both the only tab dragged to its own edge and
  anything dragged to the edge of an empty section. Where a drop is refused,
  nothing is highlighted.
- **A column appears together with what goes in it.** A pinned section holding
  nothing, for which the feature has no empty view, is not rendered, and its share
  of the row goes whole to the next column that is — `sizes` in the tree are
  untouched, so the width comes back exactly as the user left it. `pinned` keeps a
  role on the screen rather than one particular section, so a column left empty
  while the section split off it holds the work goes too. The head of a column is
  one height whatever it holds, or the line under two columns reads as a broken
  layout rather than an empty one. Only the right-hand column has an empty view:
  the scene, which derives its stage from the list of connections and the catalog
  being read.
- **There are as many catalogs as were opened.** A connection opens its catalog
  once, because a panel is identified by what it shows; which catalog is being
  read is asked of the tree — the sections that take `navigate`, the focused one
  first, its active tab — rather than kept beside it. The list of connections has
  two states, open and being read, said with two strengths of the same highlight.
- **A tab is carried, and where it is dropped says what it means.** Pressing a tab
  does nothing until the pointer has moved far enough to mean it; from then the
  tab is gone from its strip and a copy of it follows the pointer. A section is
  two targets: its strip is the one way to put a panel beside the ones already
  there, its body is the one way to divide it, and in the body the nearest edge
  wins with nothing neutral in the middle. The highlight shows where the panel
  will end up — the strip, the half it will occupy, or the whole of a section that
  holds nothing — rather than which zone the pointer is in.
- **A column pushed aside may keep something on screen.** The engine knows the
  section is narrow and asks the feature what is worth that width, the way it asks
  what stands in an empty one; only the connections answer, with their icons and
  their state dots. Closing every tab but the active one is the engine's too — it
  is a layout operation — and it leaves a panel the feature says has no cross.
- **A tab that is not showing is kept, not destroyed.** Switching away and back is
  no reason to re-read a catalog or to lose the page a grid was on, so the section
  wraps the active panel in `<KeepAlive>`. That puts one requirement on the
  feature: `component(panel)` must answer with the same component for the same
  panel. A wrapper built afresh on each call is a different component each time,
  and a functional wrapper cannot be kept alive at all.
- **A tab offers what the feature named, and the engine calls it back.** Three
  handles have this shape now: `iconTooltip` with `onIconClick`, which is how a
  catalog tab opens the window of its connection, and `reloadTooltip` with
  `onReload`, which is how a tab is re-read. The engine draws the button when
  the feature named it and calls back with the panel id; what re-reading means
  belongs to the panel — the connections list asks vue-query again, the catalog
  re-reads the level it is standing on, the grid re-runs the page it is showing
  — so panels register their own answer in a small registry and the engine
  never learns what a catalog is. Instance refs held by the engine would have
  been the other way to reach a panel, and that is the coupling this decision
  exists to prevent.
- **The icon of a tab does what that tab has no other way to do.** From a
  catalog that is the connection itself; from a table it is the catalog the
  table came from, which is reachable nowhere else — while editing a connection
  has two other ways in. What used to stand beside the title of a data tab, the
  name of its connection, is in the tooltip instead: the column is a fifth of
  the screen and the node is what the eye looks for.
- **Being pointed at is not being ticked.** A tick means an action will be done
  to a row; arriving from the tab of a table means "here it is". Two meanings,
  so an outline rather than a fill — and it takes itself off after three
  seconds, because an outline held indefinitely stops saying "here it is" and
  starts reading as a state the row is in. It fades rather than blinks: every
  row carries the outline transparent, since a colour cannot be transitioned
  out of a rule that is no longer applied. The pointing travels as a piece of
  state the panel takes, not as a call: the panel may have been opened by the
  very press that asked for it and not be mounted yet.
- **A node that is not on the level shown is not found for you.** Walking to its
  level would mean taking its id apart on the client, and how an id is built is
  the source's own business. The catalog is opened and nothing is marked. The
  honest fix is a capability that answers with the path to a node.
- **A panel that never mounted has nothing to re-read.** Only the active tab of
  a section is mounted, and `<KeepAlive>` keeps the ones that have been shown —
  so a tab restored from storage and never opened has registered nothing.
  Pressing its reload shows it instead, because reading a panel that never read
  anything is showing it.
- **Walking a catalog is not logic of a screen.** `useCatalogTree` holds it, and
  it invalidates the branch it re-reads rather than trusting whoever changed it to
  have done so.

Known deviations:

- **A refusal is visible only as the absence of a highlight.** Why a tab may not
  be brought here is not explained.
- **A hidden column is still in the tree.** It shows in localStorage and in a
  layout test although it is not on the screen. That is what brings its width
  back, but "what I see" and "what is written" differ here.
- **The freed share goes to the neighbour on one side, not by meaning.** Right for
  a row of three columns, arbitrary for a split from top to bottom, where "the
  next one along" means "the one below".
- **The connection named on a data tab is written when it is opened.** Rename the
  connection and the tab lags until it is opened again — already true of the title
  of a catalog tab.
- **The stored layout was discarded once**, on the move to version 3, because a
  data tab now carries the connection it came from.
- **The scene knows three stages and no more.** A source that cannot be browsed
  never reaches it: the middle column simply does not appear, and there is nothing
  that says so in words.
- **The bar at the bottom of the screen is empty.** It closes the layout and holds
  the room for a status line.
- **Tabs cannot be reordered inside a strip.** A tab dropped on a strip is added
  at the end, and no caret is drawn between tabs; dropped on its own strip it does
  nothing. A position in a strip would put an index into every tree operation.
- **The target that merges is a strip thirty-one pixels tall.** Harder to hit than
  half a panel, and on a narrow column it is narrow.
- **A collapsed column is still a target.** Its strip is forty pixels of handles,
  and a tab dropped there goes where it cannot be seen until the column is brought
  back.
- **What is in the hand shows only what a tab shows.** No picture of the panel:
  two tabs of one node from different connections are told apart by the icon of
  the source and, once hovered, by the tooltip on it.
- **The ghost hangs from the pointer, not from where the tab was grabbed.**
- **A drag cannot be cancelled from the keyboard.** Escape does nothing; releasing
  over no target is the only way to change one's mind.
- **The threshold is three pixels for everyone.** The same number the border
  between two columns uses; nobody has measured it against a touch screen or an
  unsteady hand.
- **The layout is one per browser.** It lives in localStorage, so it does not
  follow a user to another machine and is not shared between two windows.
- **A panel of a connector that was deleted stays until it is closed.** It shows
  the error the server gave rather than disappearing, because the panel cannot
  tell a deleted connector from a failed request.
- **A closed panel is still held.** Both the map of bound components in
  `features/workspace/panels.ts` and the cache inside `<KeepAlive>` keep what they
  were given for as long as the page lives. Bounded by how many distinct panels
  one session opens.

## D14. A connection is edited in a floating window, and there may be several

Not modal, and that is the requirement rather than a detail: the reason for the
window is to read one connection while filling in another. What modality would
have given — that you cannot walk away from an unfinished form — is replaced by
asking before a window with unsaved changes is closed. `shared/windows` knows
nothing about connections, the same split that keeps `shared/workspace` free of
any knowledge about panels.

Inside, the layout follows a database tool: the name on top, host and port on one
line because the options model says they are one address, and the connection
string the server composed pinned above Test Connection and OK / Cancel / Apply.
A new connection opens named after its type and addressed to localhost; a stored
secret shows as `<hidden>`, empties the moment the field is entered and comes back
if it is left untyped-in; what a check said appears in a panel over the button
that ran it rather than as a line that moves the form about.

The old application had such an engine. Three things it got wrong are inverted
here: a z-index counter that only ever grew is now a position in a list; geometry
mutated in place inside the manager is now pure functions whose result is
assigned; and no clamping at all — a window dragged past an edge could not be
recovered — is now a rule applied on every move and again when the viewport
shrinks.

Consequences:

- **A window is identified by what it shows**, so asking for a connection that is
  already open brings that window forward. Two windows of one row are two unsaved
  edits of it, and whichever is saved second silently wins. Drafts have no row to
  overwrite, so any number of them may be open.
- **What a window is is not what it is addressed by.** Saving a draft renames the
  window to the connection it created — so a second Apply updates rather than
  duplicating — and the list is keyed by a separate immutable key. Keying it by
  the address instead destroyed the window at that moment and built a fresh one:
  the form reset itself, and the close that followed the save was delivered to an
  instance that no longer existed.
- **A new window opens in the middle of the screen**, not at a corner. At a corner
  it lands on the column it was opened from and covers the control that opens the
  next one.
- **The server says how the form is laid out.** `layout()` on a field names its
  tab and the row it shares. Left to the screen, the rule that a host and a port
  are one address would be inferred from a port being a number, in a component
  that knows nothing about addresses.

Known deviations:

- **Windows do not survive a reload.** The workspace layout does; a window does
  not, because a half-filled form restored without its secrets would promise more
  than it holds.
- **A window cannot be resized**, only moved. Its width is decided by what it is.
- **A window can cover the application's header.** Dragged to the top it lies over
  Sign out until it is moved away. The price of the window engine not knowing the
  height of the chrome above it; it cannot be lost, which is what the layer was
  changed for.
- **The tab strip inside a window has never been seen.** Both source types put
  everything in one group, and one tab is not a choice, so the strip does not
  render — that half of D14 is unproven in a browser.
- **Nothing minimises or maximises.** The old engine had both; a window here is a
  thing you do and then close, not a place you live in.
- **A window reopened does not return to where it was.** It joins the cascade
  again.
