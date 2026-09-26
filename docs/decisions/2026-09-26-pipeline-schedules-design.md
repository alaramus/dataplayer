# Schedules: a pipeline that runs by itself

Date: 2026-09-26. Decision: D179. Builds on D177 (one run of a whole
pipeline, as a job) and D178 (chains), on the jobs of D81 and on D124 (the
backend is one process).

## The problem

A pipeline is drawn to be run again: the orders saved as CSV every night,
the file copied on to a server every morning. Until now a person has to open
the canvas and press Run each time, and a pipeline nobody presses does
nothing. n8n's Schedule Trigger is what is missing: the same Run, started by
the clock rather than by a hand.

## D179. A pipeline runs by itself on a schedule of its own

### The schedule

- **One schedule a pipeline**, set from a clock button beside Run in the
  canvas's head. Its window offers:
  - off;
  - every N minutes, hours or days — no more often than every 5 minutes;
  - every day at one or more times — "03:00", or "09:00 and 18:00";
  - on chosen days of the week at one or more times — weekdays at 09:00.
- **Times are the person's wall clock**: the browser's time zone is kept
  with the schedule, and a day's 03:00 is 03:00 there whatever the season. A
  time the clock skips when it goes forward runs as the clock moves past it;
  a time it repeats when it goes back runs once.
- **Switched off, a schedule keeps its settings**, and switched on again it
  counts from then.
- **Kept beside the pipeline's body, not in it**: when it runs is not what
  it runs, and a change of schedule is not checked against the version the
  canvas saves with (D129, D175).
- **Up to twelve times a day**; an interval between 5 minutes and 7 days.

### Running when it is due

- **The server keeps each schedule's next time** and, in its one process
  (D124), looks every half minute for those that have come. A run due is the
  Run of D177, started as the pipeline's owner: the pipeline as saved, every
  step checked again for the owner's access now.
- **The job says it was started by the schedule**, and the footer shows it
  so: "Nightly · scheduled · 2 of 5: Save as CSV".
- **A time that comes while the previous run still goes is skipped**, as is
  one refused for any reason Run would be refused — three pipelines already
  running, a link lacking a choice, no link at all — and the head says so:
  "Skipped at 03:00: the previous run was still going".
- **A time that passed while the server was off is not caught up.** The next
  time is worked out from when it started again, and the head says what was
  missed: "Missed at 03:00: the server was off".
- **A scheduled run that fails waits in Needs you** in the footer, as any
  failed job does (D115); one that succeeds is quiet.

### On the canvas

- **The head says the next run**, "Next run: tomorrow 03:00", beside the last
  run's sentence (D177), and the last skip or miss when there is one.
- The clock button is highlighted while the schedule is on.

## Out of scope

- Starting on an event: a file arriving in a folder, a table changing. The
  next step for triggers, and a larger one: it means watching sources.
- Several schedules of one pipeline; catching up what was missed.
- Telling anybody outside the application — mail, a chat — that a run
  failed.
- A history of runs, skips and misses beyond the last of each.

## Known deviations, accepted with it

- **A run starts up to half a minute after its time**: the server looks
  every thirty seconds rather than sleeping until each one.
- **Only the last skip or miss is kept**, with the last run; a pipeline
  skipped every night says so only for the latest night.
- **The schedule is the owner's clock, not the server's**: a person who
  moves to another time zone keeps the old one until the schedule is saved
  again.

## Acceptance

- A pipeline set to run every 5 minutes runs by itself, and the head says
  when next; switched off, it stops and keeps its settings.
- Every day at 03:00 in a zone with a clock change runs at 03:00 local time
  on both sides of it.
- On weekdays at 09:00 and 18:00: the next time after Friday 18:00 is Monday
  09:00.
- The time coming while the previous run goes: nothing starts, and the head
  says it was skipped and why.
- The server off at the time: nothing is caught up when it starts, the head
  says the time was missed, and the next time is the following one.
- A scheduled run failing waits in Needs you, and its footer row says it was
  scheduled.
- Another person's pipeline's schedule can be neither read nor set.

Tests cover the next time as a plain function — intervals, several times a
day, days of the week, time zones, a clock skipped and repeated — what a due,
late and missed schedule does, a refused run noted as skipped, the loop
starting a due run as the owner with the clock given to it, the bounds and
access of the schedule's route, and in the browser a schedule set, its next
time shown, and switched off.
