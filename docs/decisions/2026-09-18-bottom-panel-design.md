# The panel at the foot of the workspace

Date: 2026-09-18. Decision: D143.

Status: implemented with this specification.

## What was asked

The user wanted a second kind of card, one that always opens at the bottom of
the screen, the way PyCharm opens its terminal: a tool window along the foot of
the editor, switched from a button on the side bar. Services come first, and
the button that shows them must be pressable whether or not anything runs — an
empty tool says it is empty. Terminals and other tools are expected to follow.

## Where services were before

The Services button on the left bottom rail opened a floating window (D69).
Before that the list stood above the connections, and was moved out because
that column is where every connection goes. The button was greyed out while
the server ran nothing, so a person with no services had no way to find out
where they would appear.

## Options

1. **Keep the window.** A floating window is a piece of work: it covers the
   columns and has to be moved off them to watch a start while doing something
   else. Services, and terminals more so, are watched beside the work.
2. **A panel kind in a workspace column.** A column is a role (D12) and a place
   panels are dragged to; a service list is not a node's view, and it would
   exist only in Data while the spaces covering Data would lose it.
3. **A card at the foot of the screen, between the rails, under every space.**
   What an IDE does, which is the reference the user named, and a place that
   neither covers the work nor takes part in its layout.

The third was chosen.

## Decision

- One card below whatever space is shown — Data, Dashboards or AI — spanning
  the room between the left and right tool rails. It is `AppCardFrame` with an
  `AppCardHead`, like every other card: the head names the tool and carries a
  button that hides the panel.
- One tool at a time. The rail button of a tool shows it, replacing another
  one, and hides the panel when pressed again. It is drawn pressed while its
  tool is shown, the way the space switch marks the current space.
- The Services button is always enabled. Its tooltip still says how many
  services there are, or the step one of them has reached (D81); the list says
  "This server is not running anything for you" when that is the case.
- The height is dragged by the gap above the card, the same separator that
  resizes columns. It has a floor of 120 px, and the columns above keep at
  least 160 px whatever height is stored, so a panel made tall in a large
  window does not bury the work in a small one. A drag starts from the height
  the card is drawn at, not the stored one.
- Which tool is open and the height are kept per browser, like the arrangement
  of the rails. A stored tool that no longer exists is no tool.
- The tools are one registry, `features/workspace/bottomTools.ts`. The state
  is pure functions in `bottomPanel.ts` and one shared state in
  `useBottomPanel.ts`, because the button stands on a rail and the card under
  the columns, and neither owns the other.

## Not decided here

- Several tools shown at once, or tabs inside one tool (several terminals).
  The head has room for them after the title; they arrive with terminals.
- Dragging a tool's button between the rails already works, since it is a rail
  block; moving the panel itself to a side is not offered.
- Floating windows still keep clear of the footer only; they may cover the
  panel, as they cover the columns.

## Tests

- `bottomPanel.spec.ts`: what a stored state comes to, the toggle, the floor.
- `commands.spec.ts`: the Services button is enabled with nothing running.
- `tests/bottom-panel.spec.ts`: the button opens the panel with nothing
  running, the panel stays under another space, it hides from its head and
  from the button, and it comes back after a reload.
- `tests/services.spec.ts`: the service lifecycle, now watched in the panel.
