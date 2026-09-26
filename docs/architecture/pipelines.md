# Pipelines

Read this before changing the pipelines space, a pipeline's cards, or the
answer of what a person's connections can give each other.

Decisions here: D174, D175.

## D174. What the connections can give each other is one answer

- **`GET /interactions/map`** answers, for every ordered pair of the person's
  switched-on connections, the paste kinds of the registry (D164) whose
  `serves` holds, and whether the person's standing on both ends meets what
  each requires. No source is opened: adapters are built and asked by
  capability, and one whose options no longer read serves nothing. More than
  300 connections are refused rather than answered in part.
- **It claims what two connections can do**, never what a selection will:
  that stays the pair window's answer. An operation the person cannot use
  names what it needs.
- It was drawn as a space of its own, the connections map, until D175 took
  that place on the rail. What it answers by connection is the first filter
  of D176's hint of possible links.

Known deviations:

- **Nothing on screen asks it until the hint does.** The screen went with
  D175, and the route stays for the hint rather than being removed and
  written again.

Spec: [A map of what the connections can do to each other](../decisions/2026-09-26-interaction-map-design.md)

## D175. A pipeline is a named canvas of cards, kept on the server

`features/pipelines` over D97's 2D canvas, and `app.pipelines` behind it.

- **"Pipelines" is a space of the rail's switch**, beside Data, Dashboards and
  AI, covering the data workspace by D125's contract. On the left the
  person's connections, which the header's button pushes aside to icons; on
  the right the canvas of the pipeline chosen in the head's switcher, with
  Fit, Rename, Delete and New beside it.
- **A connection dropped on the canvas, or pressed in the list,** opens a
  window of its catalog with ticks. Groupings are levels walked into there
  rather than D75's filter, so a schema is tickable as a place; the top of a
  connection is tickable where it holds no groupings, as personal storage's
  does. Ticks outlive the level they were made on. Nothing ticked, nothing
  placed.
- **What was ticked is a card**: the connection in its head, a row per node
  with its kind's icon and where it lives. A drop places it under the
  pointer; a press places it at the nearest spot clear of other cards. The
  head's settings, or a double click, open the window again on what the card
  holds; its cross takes the card off after a confirmation. A connection may
  be several cards. Cards move by hand; nothing is laid out for the person,
  and a selection fades nothing.
- **A pipeline is the person's own**: a name, its cards — connection, the
  node ids ticked with the labels they had and where they were, a position —
  kept as one JSON body saved whole with a version, as a dashboard is (D129).
  Anybody else is told there is no such pipeline. A save adding a card for a
  connection the person cannot read is refused; a card already there stays
  whatever became of its connection.
- **A card names nodes, it does not hold them.** Each card drawn asks
  `GET /pipelines/{id}/cards/{card}/state` of the card as stored: a connection
  gone, not shared any more or switched off makes the card dashed and says
  so, and a node the source no longer has is struck out as "not found".
- **Bounds**: 100 pipelines a person, 50 cards a pipeline, 100 rows a card.
  The screen stops the fifty-first card and the hundred-and-first tick rather
  than have the save refused.

Known deviations:

- **Labels are kept as they were ticked.** A table renamed since keeps its
  old name on the card until the window is opened again — and a renamed node
  is usually a node with another id, so it is also struck out.
- **A card is checked row by row.** Up to a hundred calls to the source one
  after another, since an adapter is not promised to take concurrent calls. A
  source that cannot say where a node lives is not asked, and its rows are
  never struck out.

Spec: [Pipelines: connections laid out on a canvas, and links run between them](../decisions/2026-09-26-pipelines-design.md)
