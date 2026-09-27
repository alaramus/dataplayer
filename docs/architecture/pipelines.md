# Pipelines

Read this before changing the pipelines space, a pipeline's cards, links,
run, schedule or history, or the answer of what a person's connections can
give each other.

Decisions here: D174, D175, D176, D177, D178, D179, D180.

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

- **"Pipelines" is a space of the rail's switch**, next after Data, then
  Dashboards and AI, covering the data workspace by D125's contract. On the
  left the person's connections, which the header's button pushes aside to
  icons; on the right the canvas of the pipeline chosen in the head's
  switcher, with Fit, Rename, Delete and New beside it. The list on the left
  is drawn as Data draws its column of connections — the same head, its plus,
  filter and reload, the filter shared, the same pushed-aside rail — so the
  switch between the two spaces changes only the right-hand side. Their widths
  stay their own.
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
  understands. It is asked of the pipeline as kept,
  `POST /pipelines/{id}/offers`, so the screen saves first; that is how an
  end that is a link's result is answered too (D178). None usable —
  available, or held back only by a taken name — draws nothing and says the
  first reason. Both ends in one connection, or a start at the top of a
  connection, are refused before anything is asked.
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
  the panel says the link's part. The screen reads the last run again at each
  move of its job told over the socket, and every three seconds while it
  runs. The head said the last run's sentence until D180 moved it to the
  history.
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

## D178. What a link makes is a row of its card, and the next link reads it

- **A link end names a node, the top, or what a link makes** (`made_by`).
  Save as CSV makes a file, Create a table a table, Copy and Move the node
  carried; Add rows makes nothing. The body refuses a result end whose link
  writes into another card or makes nothing, and a link that reads or writes
  into, however far along, what it makes itself.
- **The server names each result** (`results.py`), sent with every read and
  save as `results`: each kind's `made` asked of what its link reads — a
  ticked row by its label and kind, a result by the link before it — with
  the link's choices. The canvas draws it in italics below the row its link
  writes into, marked with that link's number, "← 1". It is not checked
  against the connection as ticked rows are.
- **What can be done with a result is asked of what the link will make**
  (`offers.py`): the chain's root is read for its columns, each link along it
  describes what it makes, and each kind's `foresee` takes that description
  in place of a node. The column windows open on those columns before the
  first run. The hint asks the same, results included.
- **At run time a link reading or writing into a result waits for the link
  making it**, and a circle is never broken at such a link (`order.py`).
  Each step keeps the node it made and the name it was made under; the next
  is handed that node when it starts. A result not made in this run leaves
  the link reading it not run, saying so — never what an earlier run left
  under that name.
- **The panel and the footer** say what a link read and what it made, by
  name. A link taken away, or given an operation that makes nothing, takes
  the links using what it made, after a confirmation naming them; so does a
  card taken off or a row unticked.

Known deviations:

- **What is said ahead is checked again when the step runs**: a table
  changed since, a name taken meanwhile, a file too large fail the step with
  its sentence, as any step does (D177).
- **A result's columns are a CSV's as text and a new table's as chosen**,
  not as the database will spell them; a pairing into it is by name.
- **The pairing window's preview has nothing to read** from a result not
  made yet, and says so.
- **Every operation change takes the links using the result when the new
  one makes nothing**; between two that make something, as Copy and Move,
  they stay.

Spec: [Chains: what one link makes, read by the next](../decisions/2026-09-26-pipeline-chains-design.md)

## D179. A pipeline runs by itself on a schedule of its own

- **One schedule a pipeline, in a row of its own** (`PipelineSchedule`), set
  and read by `PUT` and `GET /pipelines/{id}/schedule`: every N minutes,
  hours or days, 5 minutes to 7 days, counted from when it was switched on or
  changed; or up to twelve times of the day on chosen days of the week. Kept
  beside the body, so a change of it is not checked against the canvas's
  version. Switched off, it keeps what was chosen.
- **Times are the owner's wall clock**: the browser's zone is saved with the
  schedule and every save takes the browser's again. `timing.py` works out
  the next time as a plain function: a time the clock skips runs as it moves
  past, one it repeats runs the first time round. The zones come from
  `tzdata` where the system keeps none.
- **`scheduler.py` looks every `SCHEDULE_TICK_SECONDS`** (30) in the one
  process (D124), from the application's lifespan. A schedule whose time has
  come starts the Run of D177 as the owner, the record saying when the
  schedule came (`scheduled_for`), and its next time is worked out from now.
  A run Run refuses — one going, too many a person, a link lacking a choice,
  no link — is not started, and the schedule notes it skipped, and why.
- **A time more than two minutes past when the server starts is not caught
  up**: noted as missed, "the server was off", and the next time is worked
  out from then. One less late still runs: a restart takes seconds.
- **On the canvas** a clock button beside Run opens the schedule's window and
  is highlighted while it is on; the head says "Next run: tomorrow 03:00" in
  the browser's clock. The skips and misses are rows of the history (D180).
  The footer names a run the schedule started "Nightly · scheduled".

Known deviations:

- **A run starts up to half a minute after its time**: the server looks
  every thirty seconds rather than sleeping until each one.
- **The zone is the browser's that last saved the schedule**; the owner's
  moving elsewhere changes nothing until it is saved again.

Spec: [Schedules: a pipeline that runs by itself](../decisions/2026-09-26-pipeline-schedules-design.md)

## D180. A pipeline's runs are kept, a hundred of them, and one can be shown

- **`GET /pipelines/{id}/history`** (`history.py`) answers the pipeline's
  runs and its schedule's skips and misses as one list, newest first: a run
  is its job — state, sentence, start and end, and whether the schedule
  started it (`scheduled_for`) — and a skip or a miss is a `ScheduleNote`,
  the time that came, its kind and why. The screen only words the rows.
- **A History button in the head** opens a window of those rows: the
  sentence, then "26 Sep 03:00 · by the schedule · took 12.4 s"; a run that
  failed or was interrupted in the caution colour, a skip or a miss faded.
  The window reads again at each move of a run told over the socket and
  stays open while runs are pressed.
- **A run pressed is shown on the canvas**: `GET /pipelines/{id}/runs/{job}`
  answers it as the last run is answered (D177), the links still drawn only.
  The lines and the panel say what it did then, a link drawn since saying
  "Drawn since this run"; a strip over the canvas says "Showing the run of 26
  Sep 03:00" with "Back to the last run". The newest row pressed is the last
  run itself, and Run brings the canvas back to the run it starts.
- **The head says only when the schedule comes next.** A run going is
  followed by its lines and the footer.
- **The last hundred of each are kept.** Starting a run removes the ended runs
  of the pipeline after its newest hundred (`jobs.crud.forget_finished`), and
  a note removes the notes after the newest hundred. A run still going is
  never removed: its runner writes into it until it ends.
- **A pipeline deleted takes its ended runs**, and its notes by the foreign
  key. A run going then ends as it would have and stays in the footer's
  activity, which is read again.

Known deviations:

- **A past run is shown on today's canvas**: a card moved since is where it
  is now, and a result row (D178) is named as it would be made today.
- **A run removed from the history is removed from the footer's activity
  too**: they are one row.
- **A row says its time in this browser's clock**, a skip or a miss too,
  though the schedule's times are the zone it was saved in.

Spec: [A pipeline's history of runs](../decisions/2026-09-26-pipeline-history-design.md)
