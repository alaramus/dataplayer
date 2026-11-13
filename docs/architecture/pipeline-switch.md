# Switching a pipeline on

Read this before changing how a pipeline is started and stopped, the head of
its canvas, what a row being dragged shows, what a link is drawn with, or the
status line at the foot of the canvas. The canvas, links, runs, schedules and
following themselves are [pipelines.md](pipelines.md).

Decisions here: D362, D363, D364.

## D362. One switch starts a pipeline; each link says how it runs

- **A link runs `continuous` or `scheduled`** (`Link.runs`). Only a link-only
  kind may be continuous (D312–D314); a drawn link takes the offer's default,
  continuous where its source is read on. The panel offers the choice there,
  under "While the pipeline is on". It replaced D315's `follow` mark.
- **A pipeline is on or off**: `PipelineSwitch`, beside it, read and set by
  `GET` and `PUT /pipelines/{id}/switch` (`switch.py`). On, the follower of
  D315 carries the continuous links and the schedule of D179 comes for the
  rest; off, nothing runs by itself and the schedule's `next_at` is cleared.
  The schedule has no switch of its own.
- **Switch on refuses whole before anything starts**: no link; a link lacking
  a choice, by Run's rule and with its ids (D177); scheduled links and no
  schedule, `pipelines.no_schedule`, on which the screen opens the schedule.
  A follower is started only when there is a continuous link.
- **The head holds Switch on / Switch off, a chevron menu of Schedule… and
  Run once now, Fit, a "⋯" menu of History, Rename and Delete, and New.** Run,
  Follow, the clock and the hint went.
- **The migration** keeps behaviour: a link marked to follow runs
  continuously only where following was on; a pipeline is on where following
  or the schedule was; a schedule switched off on a pipeline now on for its
  following is dropped rather than starting to run.

Known deviations:

- **Stop in the footer switches the whole pipeline off**, its schedule too:
  the follower's job is the switch's only trace in the activity.
- **A scheduled link does not run when a continuous one before it carries
  something**: that is the event model left aside with D177–D180, so a mixed
  pipeline needs times.
- **A continuous link of `rows_by_key` from a source not read on** is refused
  by its follower as D315's is; the panel offers continuous only where the
  offer says `reads_on`.

Spec: [A pipeline switched on with one button](../decisions/2026-11-13-pipeline-one-switch-design.md)

## D363. A row being dragged shows where it can go

- **`POST /pipelines/{id}/targets`** (`targets.py`) answers, for a source row,
  every row of the other cards, results and tops included: the operation a
  drop would draw, by the first usable offer, or a reason — "Same
  connection", "Already linked", the offers' first reason. The pair of
  connections is asked first (D174), then each kind's offer, as D176's
  offers are.
- **Past `MAX_TARGET_ROWS` (400)** the rows are left unasked and the answer
  says `partial`; the screen asks a card's rows (`card_id`) when the pointer
  first reaches it.
- **The canvas tints** a row that takes the drop in the success wash with the
  operation where its detail was, and fades one that does not with its
  reason (`GraphRow.tint`). A drop on a faded row draws nothing.
- **`Graph2D` says a row drag starts, aims and ends** (`linking`, `aim`) and
  marks the page with `data-graph-linking` meanwhile, so the tour's card lets
  a drop through to the row beneath it.

Known deviations:

- **The tints arrive after the source is read**: a quick drop before them is
  asked as D176 asks it.

Spec: [A pipeline switched on with one button](../decisions/2026-11-13-pipeline-one-switch-design.md)

## D364. A link is drawn ready, and says what it still needs

- **The pipeline's offers carry `defaults`** (`offers.LinkOffer`): how the
  link runs; a new table's name — the offer's suggestion or the source's
  label made a plain name — and every source column typed as the
  destination's text type; a pairing by equal names; a key from a topic's
  `key` with its JSON fields as a hash. The screen copies them into the link
  and opens a window only for what is still missing; the windows open on them.
- **`lacking`** — each link that cannot run, what it needs (`table`,
  `pairing`, `key`) and Run's sentence — is sent with every read and save
  (`runs.lacking`), so Run, Switch on and the canvas share one rule. Such a
  link is drawn in the caution colour with what it needs after its title.
- **The status line at the foot of the canvas** says the first that applies,
  chosen by the server (`switch.status_of`) and worded by the screen
  (`status.ts`): nothing drawn; a link lacking a choice; scheduled links and
  no schedule; a continuous link retrying; on, for how long, when it last
  carried and when the schedule comes next; ready, with what Switch on will
  do. Its action opens the link, the schedule or the history.

Known deviations:

- **A default name already taken** leaves the name out, so the link lacks it.
- **Defaults are not asked of a result not made yet**: its window asks.

Spec: [A pipeline switched on with one button](../decisions/2026-11-13-pipeline-one-switch-design.md)
