# One Run for a whole pipeline

Date: 2026-09-26. Decision: D177. Builds on D175 and D176 (pipelines, their
links), D164 (one paste answer for a pair), D166 (rows pasted), D168
(transfers as owned jobs) and the jobs of D81. Replaces D176's Run of one
link from its panel.

## The problem

D176 runs a link at a time, from the panel of the link selected. A pipeline
is meant as a workflow, the way n8n draws one: the person lays the steps out,
presses Run once, and everything goes in order, each step after the ones it
depends on, with the canvas showing what has run, what is running and what
failed. Pressing Run on every link in turn, in an order kept in one's head,
is the work the pipeline was drawn to take away.

## D177. A pipeline runs as one job, link by link along its arrows

### One Run

- **Run in the canvas's head is the only Run.** A link is no longer run on
  its own: its panel keeps its choices and its result in the last run.
- With no link drawn, Run is off and says "Draw a link first".
- **Run saves the draft first**, and the server runs the pipeline as saved.
  Edits made while it runs are kept for the next run and change nothing in
  this one.
- **Before anything runs, every link is checked for the choices its
  operation needs** — a new table's name and columns, the pairing into a
  ticked table — by its kind's workflow, reading no source. If any is
  missing, nothing runs, and the answer names those links.

### The order

- **A card is read only after every link writing into it is done**: a link
  goes after every link whose target row is on its source card. Several cards
  of one connection are how a person says a connection is read at one point
  and written at another (D175).
- **Links free to go at once go by position**: the one whose source card is
  further left first, then higher, then the one from the higher row.
- **Where links write into each other in a circle**, the circle is broken by
  the same position rule, and the link it was broken at says so: its number
  is drawn in the caution colour, and a hint that pops up over it names the
  cards writing into each other and why this link goes first.
- **The order is the server's answer**, sent with the pipeline: each link
  carries its number, drawn on its line — "2 · Save as CSV". A link drawn
  since the last save gets its number when the save comes back.

### Running

- **One job of a new kind, `pipeline.run`**, owned by the person, carries the
  steps out one after another. The footer shows it by the pipeline's name,
  and where it is: "2 of 5: Save as CSV". It goes on with the page closed.
- **Each step is the Paste its link stands for**, checked again for access
  and for what the kind serves (D164). A transfer is carried out inside the
  run's job rather than as a job of its own, and rows are pasted inside it
  too: no step runs in a request.
- **The first step that fails stops the run.** That link is failed with its
  sentence, every link after it is "not run", and the run's sentence says
  where it stopped: "Stopped at 3 of 5, Save as CSV: orders.csv is already in
  reports; 2 not run".
- **Stop, in the footer, stops the run**: the step running stops as a
  transfer stops (D168), and the rest are not run.
- **One run of a pipeline at a time**: Run is off while one runs, and says
  so. A person runs at most three pipelines at once, as transfers (D168).

### On the canvas

- **Each link's line takes the colour of its result in the last run**:
  running, done, failed or not run; the link running is the one highlighted.
- **The head says the pipeline's last run**: when, and its sentence.
- The panel's result line is the link's own result in that run.

## Settled during implementation

- **The run is its job.** What each step runs, copied in at the start, and
  what it did live in the job's payload; the last run is the pipeline's newest
  `pipeline.run` job. D176's table of one row per link was dropped with the
  route that ran one link.
- **A step goes through the parts of Paste's door**: both ends opened by the
  one door to a source, then `paste_now` or `planned`, taken out of
  `run_paste`, and a transfer carried out by `RunTransfer` on the transfers'
  slots, its payload kept in the step rather than a job of its own.
- **A circle is broken where nothing outside it writes in**: a link after a
  circle waits for it however far left it lies. The hint names the cards'
  connections and the part of the position rule that decided. Two links from
  one card into a card that writes back both go before it, and both say so.
- **The refusal for missing choices names the links' ids** beside its
  sentence, and the screen opens the first.
- **The last run is answered as `{run}`**, not as a bare null: a null body
  reached the screen as an empty value it read as a run.
- **Labels are placed so none covers another**: along its own line first,
  then stacked beside its middle. Two links from one row to neighbouring rows
  shared a middle, and the second hid the first's number. A label pressed
  selects its link.
- **A card's window reads its connection afresh when it opens**: a run had
  just written files the catalog's cache still kept as fresh for a minute.
- **A CSV that Save as CSV writes reads back**: its byte order mark had been
  read into the first column's name, which the first acceptance chain found.
- **The footer** says "Nightly · 2 of 5: Save as CSV", reads again the
  connections the links wrote into as they end, and the tab that started the
  run tells how it ended, as for a transfer. At most `PIPELINE_MAX_ACTIVE`
  runs a person.
- **Rows of a canvas that draws links select no text** while a link is
  dragged across them.

## Out of scope

- Running one link on its own, n8n's "execute step".
- Schedules and triggers; a history of runs beyond the last.
- Steps side by side: every step waits for the one before it.
- Handing data from one step to the next: a step reads what its source
  holds when it starts.

## Known deviations, accepted with it

- **The order is by card, not by node.** A link writing into a folder and one
  reading a file of that folder from the same card are ordered; from two
  cards of one connection they are not, and position decides.
- **A step's rows keep D166's ceiling** of 5,000, now inside the job.

## Acceptance

- Sales → Files (a table saved as CSV into `reports`) and Files → Warehouse
  (a CSV file's rows into a table), with the cards placed right to left, run
  the first link before the second, numbered 1 and 2.
- Of three links, the second failing stops the run: the first is done, the
  second failed with its sentence, the third not run, and the job's sentence
  says where it stopped.
- Two links writing into each other run by position, and the link the circle
  was broken at shows its number in the caution colour with the hint.
- Run with a link to a new table whose columns were never chosen runs
  nothing and names that link.
- Stop in the footer ends a run with steps left, and they are not run.
- The panel of a link has no Run; the route that ran one link is gone.

Tests cover the order as a plain function — dependencies, position, a
circle — the refusal for missing choices, a run of a transfer step and a rows
step as one job, the stop at a failure with the rest not run, one run at a
time, Stop between steps, the step numbers and line colours as plain
functions on the screen, and in the browser two links run by one Run and a
failure stopping the one after it.
