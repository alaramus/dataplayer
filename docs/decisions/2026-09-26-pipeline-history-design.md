# A pipeline's history of runs

Date: 2026-09-26. Decision: D180. Builds on D177 (a run is a job), D178
(what a link read and made) and D179 (a schedule's skips and misses).

## The problem

The canvas shows a pipeline's last run and nothing before it. A person
asking why last night's file is missing, or since when a link has failed,
has nowhere to look: the runs are kept as jobs but not shown by pipeline, and
a schedule keeps only its latest skip or miss (D179). Nothing removes old
runs either, so a pipeline scheduled every five minutes leaves some three
hundred job rows a day behind it.

## D180. A pipeline's runs are kept, a hundred of them, and one can be shown

### The history

- **A History button in the canvas's head opens a window** listing the
  pipeline's runs, newest first: when each started, whether by hand or by
  the schedule, how long it took, and its sentence. A run that failed or was
  interrupted is in the caution colour, its sentence saying where it
  stopped.
- **The schedule's skips and misses are rows of it too**, in their places
  among the runs: "Skipped at 03:00: the previous run was still going",
  "Missed at 03:00: the server was off".

### The head

- **The head no longer says the last run**, nor the schedule's latest skip
  or miss, as D177 and D179 had it: the history says both, and the lines say
  what the run shown did. A run going is followed by its lines and by the
  footer (D177), not by the head.
- **It keeps the next time the schedule comes**, "Next run: tomorrow 03:00":
  that is not in the history.

### A past run shown

- **A run pressed in the history is shown on the canvas**: each line in the
  colour of what it did in that run, and each link's panel saying what it
  did, read and made then. A strip above the canvas says which run it is —
  "Showing the run of 26 Sep 03:00" — with "Back to the last run" beside it.
- **The canvas is today's**: cards and links are drawn as they are now, a
  link drawn since that run is drawn plain, and one taken away since is not
  drawn.
- **Run still runs the pipeline** while a past run is shown, and brings the
  canvas back to the run it starts.

### Kept

- **The last hundred runs of each pipeline**, and the last hundred skips
  and misses of its schedule. The oldest goes as a new one is written; a
  run still going is never removed.
- **A pipeline deleted takes its finished runs and its notes with it.** A run
  still going when it is deleted ends as it would have, and is removed by
  nobody.

## Out of scope

- Searching or filtering the history, exporting it, comparing two runs.
- The pipeline as it was drawn for a past run: the history keeps what each
  run did, not the canvas it did it on.
- Runs of all pipelines together: the footer's activity lists every job.

## Known deviations, accepted with it

- **A past run is shown on today's canvas**, so a card moved since is where
  it is now, and a result row (D178) is named as it would be made today.
- **A run removed from the history is removed from the footer's activity
  too**: they are one row.

## Acceptance

- Three runs, one by the schedule: the history lists them newest first,
  saying which the schedule started, how long each took and its sentence; a
  failed one is in the caution colour.
- A scheduled time skipped is a row of the history between the runs.
- The head says no last run and no skip, and says the next run while a
  schedule is on.
- An older run pressed colours the canvas by what it did, a link's panel
  says what it did then, and "Back to the last run" brings the last run back.
- The hundred-and-first run removes the oldest; a run still going is never
  removed.
- A pipeline deleted leaves none of its finished runs behind.
- Another person's history can be neither listed nor shown.

Tests cover the history's order and rows, skips and misses among the runs,
the ceiling with a run still going, what a deletion takes, access, the words
of a history row and the lines of a shown run as plain functions, and in the
browser two runs listed, an older one shown and the canvas brought back.

## Settled during implementation

- **A skip or a miss is a row of its own table**, `ScheduleNote`: the time
  that came, `skipped` or `missed`, and why. The schedule's one latest note
  and its time went; the migration carries a note already kept over, its
  kind read off its first word.
- **The row's time is its own column**, so the sentence is "Skipped: the
  previous run was still going", not "Skipped at 03:00: …", and every row
  says its time in the browser's clock. The schedule's times stay in the
  zone it was saved in (D179), so the two can differ when the browser moved.
- **The history is one list from the server**, runs and notes merged newest
  first; the screen does no ordering. A run says who started it by whether
  its record has `scheduled_for`.
- **The newest row pressed is the last run**, not a past one: no strip, and
  the canvas follows it as it goes. Only the last can still be going, so a
  past run is read once.
- **The window stays open** while runs are pressed, the one shown marked in
  it; the canvas behind changes. A past run that can no longer be read — kept
  no more — brings the last back, saying so.
- **Deleting a pipeline says its history goes too** in the question it
  asks, and the footer's activity is read again after it.
- **A banner's one action sits at the end of its line** (`AppBanner`), which
  keeps the strip one line tall.
