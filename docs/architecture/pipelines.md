# Pipelines

Read this before changing the pipelines space, a pipeline's cards, links or
run, or the answer of what a person's connections can give each other.

Decisions here: D174, D175, D176, D177.

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

## D176. A link is drawn row to row and set in a panel below

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
- **The panel below the canvas** is the selected link's: its number and
  what it does in one sentence, a choice of operation when several fit, the
  operation's own choices, and what it did in the pipeline's last run. A new
  table's columns and a pairing are chosen in the windows Paste opens for
  them, started from what the link kept; they keep the choice rather than
  run. A link is run only with the pipeline (D177).
- **The hint** — a button in the head — draws dashed every link that could be
  made among the rows kept on the pipeline, labelled by what it would do. It
  asks each pair of connections first (D174), then each kind's offer for
  each pair of rows, drawn links left out. Past 400 pairs of rows it hints the
  selected card's only, and says so; with none selected, it says to select
  one. A dashed link pressed is drawn as if dragged. Pressed again, or once
  anything is changed, the hint goes.

Known deviations:

- **A link's title is kept as it was chosen**, as a row's label is: the
  canvas draws it without naming kinds.
- **The hint asks every offer one after another.** Four hundred pairs of rows
  can take seconds on sources that are slow to answer.

Spec: [Pipelines: connections laid out on a canvas, and links run between them](../decisions/2026-09-26-pipelines-design.md)

## D177. A pipeline runs as one job, link by link along its arrows

- **Run in the head is the only Run.** It saves the draft, then
  `POST /pipelines/{id}/run` runs the pipeline as saved. It refuses before
  anything runs with no link drawn, and when a link lacks a choice its kind's
  workflow needs — a new table's name and columns, a pairing — naming those
  links, their ids beside the message; the screen opens the first. That is
  asked of the kind alone, reading no source.
- **The order is `order.py`'s**, a plain function of the body, sent with every
  read and save as `order`: a link goes after every link writing into its
  source card; links free at once go by their source card's x, then its y,
  then the row, then the order they were drawn. Where links write into each
  other in a circle, the first link by that rule whose own waits all lie in
  the circle goes first, and carries `circle` — the cards, and why it — drawn
  as its number in the caution colour with a hint over it.
- **One job of kind `pipeline.run`** carries the steps out. Its payload
  (`record.py`) is what each step runs, copied in when the run starts, so an
  edit made while it runs changes nothing in it; and each step's outcome,
  with a transfer's own payload. Each step opens both ends again as the owner
  stands now through the one door to a source, checks what the kind serves,
  and carries the kind out: rows by `paste_now`, a transfer by `planned` and
  `RunTransfer.transferred`, on the transfers' slots and threads. No step runs
  in the request.
- **The first step that fails stops the run.** The steps after it are
  `not_run`, and the job fails with "Stopped at 3 of 5, Save as CSV: …; 2 not
  run". Stop in the footer cancels the job: the step in hand stops as a
  transfer does (D168) and says what it got done, and the job says "Stopped on
  request at …".
- **One run of a pipeline at a time**, and `PIPELINE_MAX_ACTIVE` a person, by
  `admit_within(alone=True)` under the owner's lock: 409 and 429.
- **The last run is the pipeline's newest `pipeline.run` job.**
  `GET /pipelines/{id}/run` answers `{run}`: the job's state, sentence and
  times, and each link still drawn with what it did. A step a restart left
  running reads as failed with the job's sentence, and one never reached as
  not run. D176's row per link went with the route that ran one link.
- **On the canvas** each line takes its result's colour — the link running
  highlighted, done, failed, not run faded — and its number before its title;
  the head says the last run's sentence and when, and the panel the link's
  part. The screen reads the last run again at each move of its job told over
  the socket, and every three seconds while it runs.
- **The footer** shows the run by the pipeline's name and where it is —
  "Nightly · 2 of 5: Save as CSV" — and lists what each link did once it
  ends; the connections its links wrote into are read again as a transfer's
  are.

Known deviations:

- **The order is by card, not by node.** A link writing into a folder and one
  reading a file of that folder from the same card are ordered; from two
  cards of one connection they are not, and position decides.
- **Every link that goes before a circle writing into its card says so.** Two
  links from one card into a card that writes back both run before it, and
  both numbers are in the caution colour.
- **A step's rows keep D166's ceiling** of 5,000, now inside the job.
- **A step names its connections as their cards kept them** (D175): a
  connection renamed since keeps its old name in the run's record.

Spec: [One Run for a whole pipeline](../decisions/2026-09-26-pipeline-run-design.md)
