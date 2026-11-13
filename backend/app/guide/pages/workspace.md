# The workspace

The **Data** space is where connections are opened and their contents read.
What the other spaces are is on [DataPlayer at a glance](overview.md).

## Three columns

- **Connections**, on the left: every connection you own or that was shared
  with you. Pressing one opens its catalog. See [Connections](connections.md).
- **Catalogs**, in the middle: what each opened connection holds, level by
  level. The filter at the top narrows the level by name; its search button
  looks for a name everywhere below. **Duplicate catalog beside this one**
  opens a second copy of the same catalog.
- **Work**, on the right: the tables, files, queries, structures and charts
  opened from a catalog, each in a tab. While it is empty it says what to do
  next.

Columns are resized by dragging the line between them. The layout you leave is
the one you find next time.

## Tabs

- A tab is dragged like a browser tab: dropped on the tabs of another column it
  joins them; dropped in the body of a column it divides that column in two. A
  tab can only go to a column that takes its kind.
- **Show in catalog** finds the node of a tab in its catalog.
- **Open in a window** lifts a tab out into a floating window, and
  **Open as a tab** puts it back.
- **Close the other tabs**, a button at the end of a column's tabs, closes
  all but the one shown.
- The mark beside a reload button says **Live** while what is shown has just
  been read from the source, and a clock when it is a kept answer. Pointing at
  it says how old it is.

A section of the layout can be put aside: it leaves the screen and waits as a
button in **Sections put aside** at the foot, which brings it back.

## Tab groups

The tabs open in Data and how the columns are laid out can be saved under a
name.

- **Save group**, on the top right rail, saves what is open now.
- **Saved tab groups**, beside it, lists them. Opening one replaces the tabs
  that are open, and asks first.
- **Manage group** renames a group, deletes it, or updates it from the layout
  open now. Deleting a group closes no tabs.

## Floating windows

A connection's settings, forms, questions and lifted-out tabs open in floating
windows, and several can be open at once. Nothing in DataPlayer blocks the rest
of the screen.

- A window is moved by its bar, resized by its edges, and has **Minimize**,
  **Maximize** and **Close window**.
- A window holding a form closes only by its cross, so a press of Esc never
  loses what was typed. A question closes on Esc as well.
- A minimized window waits in **Open windows** at the foot of the screen.

## Two connections side by side

**Pair with another connection**, in a catalog's head, puts the catalogs of two
connections in one window, to move things between them: it says what can go
from one to the other, and **Swap sides** reverses the direction. **Forget this
pair** closes it.

## Activity and notifications

The activity bell at the bottom right opens **Activity**, in three sections:

- **Needs you**: what waits for your answer — an agent's question, somebody
  asking for access to your connection, a connection that stopped answering, a
  job that failed;
- **Working**: what the server is doing for you — copies, backups, pipeline
  runs, starting services, searches inside files. Long work can be paused or
  stopped here where it allows it;
- **Recent**: what was said lately. **Clear all** empties it.

Short notices appear as cards at the bottom right and go into **Recent**.
**Do not disturb** stops the cards; everything is still in Activity.
