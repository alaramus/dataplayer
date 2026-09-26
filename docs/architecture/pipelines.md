# Pipelines

Read this before changing the pipelines space, a pipeline's cards or links,
or the answer of what a person's connections can give each other.

Decisions here: D174, D175, D176.

## D174. What two connections can give each other is asked of no node

- **`open_kinds`** in the paste registry (D164) answers, for two connections,
  the kinds whose `serves` holds and whose requirements the person's standing
  on both ends meets. Nothing is read from either source: it is asked of what
  the adapters are.
- **It claims what two connections can do**, never what a selection will:
  that is each kind's offer, asked of the nodes.
- It was first drawn for every pair of the person's connections at once, as a
  space of its own with a route of its own. The space went with D175 and the
  route with D176, whose hint asks it pair by pair as its first filter.

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
  pointer; a press places it at the nearest spot clear of the others,
  beside them before below, and pans the view just enough to show it. The
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

## D176. A link is drawn row to row, set in a panel below, and run from it

- **A row dragged onto a row of another card** asks the pair window's
  question with one tick each side (D167): the target row stands for the
  place and for the target, and each kind's offer takes the one it
  understands. None usable — available, or held back only by a taken name —
  draws nothing and says the first reason. Both ends in one connection, or a
  start at the top of a connection, are refused before anything is asked.
- **A link is part of the pipeline's body**: its ends, its kind, the title
  it was chosen by, and the choices Paste asks — a file name, what to do with
  a taken name, the columns of a new table or the pairing into a ticked one.
  The server refuses a link whose ends are not rows of the pipeline's cards,
  two links between the same rows, and more than 200 links.
- **The panel below the canvas** is the selected link's: what it does in one
  sentence, a choice of operation when several fit, the operation's own
  choices, and its last run. A new table's columns and a pairing are chosen
  in the windows Paste opens for them, started from what the link kept; they
  keep the choice rather than run.
- **Run saves the draft first, then runs what was saved.**
  `POST /pipelines/{id}/links/{link}/run` builds the paste from the stored
  link and goes through `transfers/run.py`, the door Paste uses: access and
  what the kind serves are checked again, a transfer becomes a job (D168), a
  row paste runs in the request. A refusal is the run's outcome, not the
  route's.
- **The last run stays with the link** in a row of its own, so a run never
  raises the version the next save is checked against. A transfer's outcome
  is read from its job; the screen reads the runs again when a job it
  started ends. A link taken away takes its run with it.
- **The hint** — a button in the head — draws dashed every link that could be
  made among the rows kept on the pipeline, labelled by what it would do. It
  asks each pair of connections first (D174), then each kind's offer for
  each pair of rows, drawn links left out. Past 400 pairs of rows it hints the
  selected card's only, and says so; with none selected, it says to select
  one. A dashed link pressed is drawn as if dragged. Pressed again, or once
  anything is changed, the hint goes.

Known deviations:

- **A row paste runs in the request**, as D166's does, up to its 5,000 rows.
  Running every link at once, when it comes, needs them all as jobs.
- **A link's title is kept as it was chosen**, as a row's label is: the
  canvas draws it without naming kinds.
- **The hint asks every offer one after another.** Four hundred pairs of rows
  can take seconds on sources that are slow to answer.

Spec: [Pipelines: connections laid out on a canvas, and links run between them](../decisions/2026-09-26-pipelines-design.md)
