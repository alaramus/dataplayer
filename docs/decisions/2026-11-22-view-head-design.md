# A view's head

Decision D424. The head of a document view (D419) was a row of labelled
buttons — **As JSON**, **Logs**, **Processes** — beside the panel's icons, and
its JSON replaced the view in the same tab. A container's lifecycle was a
catalog menu away from the overview that showed its state.

## What changes

- **Icons, names on hover.** Every command in the head is an icon whose title
  is its tooltip and accessible name, like the rest of the workspace's
  toolbars. A page's picture is named by the source (`ViewPage.icon`), so the
  client keeps no table of Docker's pages. Docker's Logs and Processes take the
  pictures of the workspace's logs and services: `receipt_long` and `dns`.
- **The node's actions over its view.** An action may declare `in_view`. The
  view asks `readActions` for its one node and draws, by icon, every applicable
  action that declares it. Choosing one opens the window the catalog would
  open — form, preview, confirmation, job, terminal — or the connection form
  for **Open as connection**. The catalog menu keeps the same actions, since a
  set of ticked containers is acted on there.
- **Afterwards.** The catalog is told of the change and the view reads its
  node again. A node that now answers 404 — a removed container — closes its
  tab.
- **The JSON in a tab of its own,** named `<node> — As JSON`, as a page is;
  `switchRepresentation` and the JSON tree's way back are removed. One binding
  still draws a view or a tree, so a tab stored before this opens as saved.
- **The scrollbar on the card's edge.** The view's body and the tree's body
  take `dp-panel-scroll`, as every other scrolling tab does.

## Docker

A container's Start, Stop, Restart, Pause, Unpause, Kill, Remove container,
Commit to an image, Terminal and Open as connection declare `in_view` and an
icon. The lifecycle verbs keep applying to a Compose project, which has no
view. Images, volumes and networks put nothing over their views yet.

## Rejected

- **Moving the actions out of the catalog.** It would end stopping or removing
  several ticked containers at once.
- **A new `offered_in` value.** `offered_in` says where an action is drawn
  instead of the menu; this is in addition to it.
