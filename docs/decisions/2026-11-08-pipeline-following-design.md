# A pipeline that follows its topics

Decision D315. The fourth piece of the topic as a distribution centre (D312–D314):
a link that carries what arrives within seconds rather than at the next
scheduled run, five minutes at the soonest (D179).

## Why a schedule is not the answer

- **A schedule's shortest step is five minutes**, and every run is a job and a
  row of the history, which keeps a hundred (D180). A run a second would fill
  it in two minutes.
- **A restart replays nothing (D81)**: a job the process was running when it
  stopped is interrupted. Whether a pipeline follows is therefore kept beside
  it, as its schedule is, and a fresh job is started from that, never the old
  one resumed.

## What follows

- **A link is marked "Follow"** in its panel. Only a link that reads on (D312):
  Add new messages, into a table there or a new one, and Keep the latest per
  key, each from a node its source reads on. A link from a table cannot be
  marked: read whole every few seconds it would be pointless and heavy. The
  mark is the link's own, kept in the pipeline's body.
- **"Follow" in the canvas's head** switches following on and off for the
  pipeline. The switch is a row of its own beside the pipeline
  (`PipelineFollow`), as the schedule is, so turning it does not touch the
  canvas's version. It is highlighted while on.
- **One follower a pipeline**: one job of kind `pipeline.follow` that runs
  until it is stopped. Every two seconds it asks each marked link's source
  whether anything is unread (the span of D312, which reads no message) and
  runs the link's step for those that have — the same step a run carries out,
  through the same code: span, blocks, bookmark, D313's key, D314's keys. The
  marked links go in the run's order (D177). Nothing new, nothing written.
- **A link that fails does not stop the others.** It is tried again after 5
  seconds, then 30, a minute, and every five minutes after; its last failure is
  said in its panel. After ten failures in a row it becomes an item of "Needs
  you" (D115), one a link, gone when the link carries a block again.
- **The server starting starts every follower that was on**, from its row, by
  the scheduler's own loop (D179); a follower that was running when the process
  stopped is interrupted like any job, and the new one takes over from the
  groups' bookmarks, so nothing is read twice that was kept.
- **Run and the schedule leave a marked link out while its pipeline follows**,
  and say so for each: "Followed; not run". Two readers of one group would
  race over its positions.

## What is seen

- **On the canvas** a marked link carries a small sign before its title; while
  following, its line takes its state's colour — carrying, idle, retrying.
- **The panel** says how many messages the link carried while following, when
  the last arrived, and its last failure if it is retrying.
- **The footer** shows "Nightly · following · 3 links", with Stop, as a running
  job is shown (D177); Stop switches following off.
- **The history (D180)** gets one row a following: from when it was switched
  on to when it stopped, with what each link carried, not a row an iteration.
  The follower's job is that row; its record keeps each link's totals and
  last failure, written at most once a second.

## Bounds

- `PIPELINE_FOLLOW_MAX` followers a person (3) and `PIPELINE_FOLLOW_SERVER_MAX`
  on the server (20); switching on past either is refused and says which.
- `PIPELINE_FOLLOW_SECONDS` between checks (2).
- A link's step while following keeps its blocks of five thousand; a
  follower falling behind catches up block by block, every block kept.

## Known deviations

- **Seconds, not milliseconds.** Every check opens Kafka's clients again, as
  every operation does (D304); a consumer kept open would deliver sooner and is
  left for later.
- **A pipeline that follows checks every marked link every two seconds**
  however quiet it is; that is one request a link to the broker.
- **A link marked while its pipeline follows** is picked up at the next check,
  from the pipeline as kept; an unsaved change is not followed.

## Where it lands

- `pipelines/`: the follower's handler, the `PipelineFollow` row and its
  routes, the scheduler starting followers, Run and the schedule leaving
  followed links out, the "Needs you" source.
- `connectors/paste/since.py`: the step run for one link with no transfer
  job of its own.
- The link's `follow` mark; the head's button; the panel's numbers; the
  footer and the history row. Locales.
- Documentation: D315 in `pipelines.md`; the guide.
- Tests: a follower carries what arrives within a check or two; only marked
  links; a failing link retried while others carry on; ten failures make an
  item and a success clears it; Run leaves followed links out; the switch
  survives a restart and starts a new job; the bounds. A Playwright scenario:
  a message sent to a topic appears in a table without pressing Run.
