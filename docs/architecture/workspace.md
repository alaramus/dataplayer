# The screen: sections, tabs and windows

The panel engine, the three columns built on it, the drag gesture that moves a
tab, and the floating windows that edit a connection. The component kit and the
screens themselves are in [frontend.md](frontend.md).

Decisions here: D12, D14, D69.

## What exists today

One screen of three columns: the connections, the catalog of every connection
that was opened, and the work opened from a node in tabs beside each other. Work
may be rows, editable source, bounded media, read-only SQL, relation structure
or a chart. Columns are
resizable and bounded by the window so each scrolls inside itself, and the
layout a user arrives at is the one they left. A column appears together with
what goes in it; the right-hand one, while it is empty, says what to do next and
offers the button that does it.

The whole workspace sits inside one inset frame between a compact application
toolbar and status line. Its panels spend the same surface, border, tab height,
spacing and radius tokens, while separators keep a wide pointer target around a
one-pixel visual line. The chrome therefore reads as one tool rather than a row
of unrelated cards; the tokens are the stable part, while individual features
can continue to arrive without settling the final polish.

A tab is carried the way a browser carries one: it leaves its strip and follows
the pointer, joins the tabs of another column by being dropped on their head, and
divides a column by being dropped in its body. It can only be taken to a column
that takes its kind.

A connection is edited in a floating window, and several are open at once.
The same application-level host owns every transient form and question:
catalog actions, row and column editing, full cell values, the download form,
sharing, the accounts form, the source-type catalog that begins **New
connection**, and confirmations. Nothing in the application is modal any more,
and the modal dialog has been removed from the component kit rather than left
in it — a rule nobody can reach for is one that holds itself up.

The cost is stated rather than discovered: a window is closed by the cross in
its bar, and no window in this application closes on Escape. One gesture for
the connection window and for a form is worth more than matching what a modal
used to do.

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
- **Two views of one node are two panels.** A JSON content panel and its explicit
  table projection share a source node but not an identity, request contract or
  component. Both use the existing `work` role, so adding native content changed
  the feature registry and not the engine. Opening one again activates its own
  tab; asking for the alternative leaves the first view intact beside it.
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
- **The cross asks the panel before it takes it away.** Closing is a request,
  not a command: the engine calls the same kind of registered answer as
  re-reading, and a panel that has nothing to say is closed at once. Only a
  person's gesture asks — a layout operation the application performs itself,
  replacing a renamed panel or clearing a strip, closes directly, because it is
  not somebody changing their mind. The reason this exists is a query console
  holding an open transaction, which would otherwise be rolled back by a lease
  five minutes after the tab it belonged to disappeared (D66).
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
- **A node is found wherever it lives, and the source is what says where.** The
  catalog asks for the path to the node and stands where the answer puts it —
  walking into the directory it is in, or ticking the schema it belongs to. Which
  of the two is read off the role of each node on the path, so nothing here takes
  an id apart; see D21. A source that cannot walk back up answers 501 and the
  catalog opens as before, marking the node only if it happens to be in view.
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

Spec: [The workspace and the panel engine](../superpowers/specs/2026-08-22-workspace-design.md)

## D69. The bar at the foot of the screen holds the commands of a connection

Almost every button hangs off the thing it acts on: a table's commands are in
its grid, a node's are in the catalog's menu, a connection's form opens from
its row or from the icon of its tab. A few have no such thing. A query console
is written against a connection and belongs to a person, so there is no node
whose toolbar it could live in, and it stood beside the plus in the connections
column — where new connections are made, and where nothing else of its kind
would have fitted.

The room at the foot of the screen was reserved when the workspace was built
and stayed empty. This is what it is for.

Consequences:

- **One rule, in one place.** A command is enabled while a connection is being
  read and that connection can do the thing; otherwise it stays in the bar,
  greyed out, and its tooltip says which of the two is missing.
  `features/workspace/commands.ts` is that rule as plain functions, tested
  without mounting anything; `CommandBar.vue` only renders it.
- **Shape before content.** Hiding what does not apply would make the bar
  change as somebody walks about, which is a bar they have to read every time.
  The same reason the catalog's action menu greys out rather than shortens.
- **The bar says which connection it is about.** A row of buttons whose subject
  is somewhere else on the screen is a row nobody trusts. Which connection is
  read is `activeConnectorId`, already derived from the layout tree rather than
  kept beside it; nothing new is stored.
- **Whether a command applies is the source's own answer**, never a branch on
  the adapter type (D62). For Queries it is the query profile: a source that
  does not run queries has no profile and answers 501.
- **"Not asked yet" is not "no".** Three states rather than two, because half a
  second of "this source does not run queries" about a PostgreSQL connection is
  a worse answer than saying nothing.
- **The library opens filtered to the connection it was opened from.** The
  filter travels as a piece of state the panel takes, the way `revealTarget`
  and `followTarget` do: there is one library panel however often it is opened,
  and a panel's props are bound when it is first drawn.

Known deviations:

- **The query library is unreachable while no connection is open.** It is a
  person's own library and outlives the connections in it (D65), but the way
  in is now a command of a connection. Opening any source that runs queries
  gets there, and the filter inside the panel still lists everything.
- **The bar holds one command.** It is a place, and the rest of what belongs in
  it arrives with the slices that implement them.
- **The right half is empty.** What a status line is usually for — what is
  running, what the last request cost — is still not said anywhere.
- **A disabled command explains itself only on hover.** The tooltip hangs off
  the slot around the button, because a disabled Quasar button takes no pointer
  events; on a touch screen there is no hover and therefore no reason.

Spec: [The bar at the foot of the screen](../superpowers/specs/2026-09-02-connection-command-bar-design.md)

## D14. Work opens in floating windows, and there may be several

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

Every window opens at a content-measured height and continues to follow content
that appears or disappears inside it, bounded by the viewport. It can be
resized from every edge or corner; manual resizing ends automatic fitting for
that window, so a later validation message does not undo the user's chosen
geometry. Repeated questions use presets in `shared/windows` rather than
restating deletion and ordinary-question geometry in each feature.

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

Spec: [The connection window: floating windows and form layout](../superpowers/specs/2026-08-23-connector-window-design.md)
