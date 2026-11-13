# A pipeline switched on with one button

Decisions D362, D363, D364. They rework how a pipeline is started, how a link
is drawn and how a link says what it still needs. What runs, and how a step
carries rows, stays as D177–D180 and D312–D315 have it.

## Why

Take Binance → Kafka → PostgreSQL, carried as trades arrive. Today it takes:

1. Drag a trade row onto a topic. If that's not allowed, a notification says
   so only after the drop.
2. Open the link's panel and turn on Follow.
3. Drag the topic onto a place in PostgreSQL. Pick the operation in the panel.
4. Open the columns window, name the table and keep its columns.
5. Turn on Follow for that link too.
6. Press the head's Follow button. Run would leave both links out, and the
   clock would run neither while the pipeline follows.

That is nine presses in four places. The head carries three ways to start
(Run, Follow, the clock), plus a mark on each link that decides which of them
applies. What could be drawn is learnt by dropping, or from a hint button that
is slow past a few hundred pairs. A link that lacks a choice looks like a
ready one until Run refuses.

With this spec it becomes two drags and one press: Switch on.

## D362. One switch; each link knows how it runs

- **A link runs `continuous` or `scheduled`**, kept on the link as `runs`.
  A link that reads its source on (D312–D314) starts as `continuous`; every
  other link is `scheduled`, and only a link that reads on may be
  `continuous`. The panel shows the choice only where both are possible. It
  replaces D315's `follow` mark: `follow: true` becomes `continuous`, and a
  link that reads on with `follow: false` becomes `scheduled`, so a pipeline
  kept before this behaves as it did.
- **A pipeline is switched on or off.** One flag beside it, kept as
  `PipelineFollow` is today; that row becomes the switch and the schedule
  loses its own `enabled`. When on, the follower of D315 carries the
  continuous links, and the schedule of D179 runs the scheduled ones at its
  times. When off, nothing runs by itself. The migration sets it on wherever
  following or the schedule was on.
- **Switch on refuses, naming what is missing, before anything starts**: no
  link; a link lacking a choice (D364); scheduled links with no times set, in
  which case it opens the schedule's window. The bounds of D315 apply only
  when there are continuous links.
- **The head holds one split button**: "Switch on" / "Switch off", and a
  chevron opening a menu:
  - *Continuously* sets every link that reads on to `continuous`.
  - *On a schedule…* sets every link to `scheduled` and opens the schedule's
    window.
  - *Run once now* is D177's Run.
  The current choice is ticked, and neither is ticked when the links' own
  choices differ. History, Rename and Delete move into a "⋯" menu; Fit and New
  stay where they are. The separate Run, Follow and clock buttons go.
- **Run once now runs every link once**, continuous links included, which read
  what is new and stop. While the pipeline is on, it leaves the continuous
  links out, saying "Runs continuously; not run" (D315's rule, reworded).

Declined: running a scheduled link whenever a continuous link before it has
carried something. That is the event model set aside with D177–D180. A
pipeline that mixes the two needs times for its scheduled links, and Switch on
says so.

## D363. Dragging a row shows where it can go

- **When a drag starts from a row**, the screen asks
  `POST /pipelines/{id}/targets` with that end. The answer has every row of the
  other cards, results (D178) and the tops of connections included. For each
  it gives the operation a drop would draw, or the first reason none is usable.
  It is asked as D176's offers are: the pair of connections first
  (`open_kinds`, D174, reading no source), then each kind's offer for the row,
  through the hint's code.
- **Past 400 rows**, the answer covers the pairs of connections only, and the
  rows of a card are asked when the pointer first enters that card. During one
  drag every answer is kept.
- **On the canvas**, a row that can take the drop is tinted in the success
  colour with the operation under its label. A row that cannot is faded with
  its reason under its label. Rows of the same connection are faded at once,
  as "Same connection". Dropping on a faded row does nothing, and no
  notification is raised. A row still unanswered looks as it does now.
- **The hint button and `POST /pipelines/{id}/hint` go.** Every link that
  could be made from a row is now shown while dragging that row, which is when
  the person wants to know.

## D364. A link is drawn ready, and says what it still needs

- **The pipeline's offer brings defaults** (`defaults` on the offer):
  - new table: the suggested name and the columns `foresee` gives, all of the
    source's;
  - pairing into a table: by column name;
  - file: its suggested name;
  - keeping the latest per key (D314): the source's `row_key` when it is a
    single column, the other columns as a hash, and the place's prefix.

  The screen copies them into the link it draws. It does not work them out
  itself, so the server's answer stays the only one. The windows still open
  from the panel to change any of them.
- **What a link lacks is sent with every read and save** as `lacking`: link id
  to sentence, from `runs.missing`, the same check that refuses Run (D177).
  The screen never decides readiness.
- **A link that lacks something is drawn in the caution colour**, with a short
  tag ("needs a name", "needs a key"). Pressing it opens the window for that
  choice. A ready link is drawn plainly. Once something runs, D177's and
  D315's colours take over as now.
- **A status line at the foot of the canvas** says one thing, the first that
  applies:
  1. what is missing, naming the first link, with a link that opens it;
  2. a continuous link retrying, with its last failure (D315);
  3. while on: how long the pipeline has been on and when something was last
     carried, or when the schedule comes next;
  4. while off and ready: what Switch on will do ("2 links will run
     continuously, 1 at 03:00 daily").

  The sentence comes from the server, with the follow state. The head keeps
  only the button. History is opened from the "⋯" menu and from the status
  line.

## What the person sees

On a drag from BTCUSDT · trades, `btc-trades` in Kafka lights up with "Send to
the topic", and `public` in PostgreSQL with "Add to a new table".
`__consumer_offsets` is faded, "Read only". Dropped on the topic, the link
reads on, so it is continuous and ready. A drag from the topic to `public`
draws "Add new messages to a new table" named `btc_trades`, with every column,
and it is ready too. The status line says both links will run continuously.
Switch on.

## Known deviations

- **Answering a drag's targets reads the sources** for each kind's offer.
  Slow sources fill the tints in a second or two, and a drop made before then
  is asked as today.
- **A default name may already be taken.** The offer says so (`name_conflict`),
  and the link is then drawn lacking a name rather than ready.
- **Pairing by name may pair nothing.** The link is then drawn lacking its
  pairing.

## Where it lands

- `pipelines/`:
  - the link's `runs` in place of `follow`;
  - the switch row and its route, which replaces `/follow`;
  - the schedule without `enabled`, run only while the switch is on;
  - `/targets` in place of `/hint`;
  - `lacking` and the status sentence with every read and save;
  - Run's wording.

  One Alembic revision moves `follow` into `runs` in the stored bodies and the
  flags into the switch.
- `connectors/paste/`: `defaults` on an offer from each kind that has a
  workflow.
- Screen: the split button and its menu; the "⋯" menu; drag tints; the
  caution colour and tags on links; the status line; the panel's runs choice;
  the hint button removed. Locales.
- Documentation: D176's hint, D177's Run, D179's switch and D315's mark
  rewritten in `pipelines.md`; the three decisions added there and to
  AGENTS.md; the guide's pipelines page.
- Tests:
  - the migration keeps both kinds of old link working;
  - Switch on refuses with no link, with a lacking link, and with scheduled
    links but no times;
  - on carries continuous links and the schedule runs the others; off stops
    both;
  - Run once leaves continuous links out only while on;
  - targets answer an operation or a reason for every row and stop asking
    rows past the ceiling;
  - each kind's defaults make its link ready;
  - `lacking` matches what Run refuses.

  A Playwright scenario: Binance → Kafka → PostgreSQL drawn with two drags and
  switched on with one press, and trades appear in the table.
