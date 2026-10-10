# Policy changes that cannot end the job scheduler

Date: 2026-10-10. Settles D211.

## Problem

Retention, compression, reorder, compaction and refresh policy changes, and
the hypertable editor, locked `timescaledb_information.jobs` in SHARE ROW
EXCLUSIVE mode before calling TimescaleDB (D123, D207). Locking a view locks
what it reads: `bgw_job`, `bgw_job_stat` and the hypertable catalog.

Up to 2.25 TimescaleDB guards each job with an advisory lock of its own and
documents the order "job lock, then the `bgw_job` table". A scheduler starting
a job takes the job lock, reads `bgw_job` in SHARE mode and writes
`bgw_job_stat` under SHARE ROW EXCLUSIVE. A `remove_*_policy` takes the job lock
in ACCESS EXCLUSIVE mode, then deletes from both catalogs.

So a DataPlayer change holding the view lock and then removing a policy waited
for the job lock, while a scheduler starting that job held the job lock and
waited for the view lock's catalogs. PostgreSQL ends whichever process checks
for the deadlock first. That is the scheduler when the removal arrives within
`deadlock_timeout` of the job's start, and a new policy starts at once. On 2.14
and 2.17, and on 2.19 and later, where `timescaledb.bgw_scheduler_restart_time`
is -1, the launcher never restarts it. Every job in that database stops until
the server restarts or `_timescaledb_functions.start_background_workers()` is
called. 2.18 restarts it after a minute. From 2.26 TimescaleDB takes no job lock
and the cycle cannot form.

`test_job_scheduler.py` reproduced it on every release from 2.14 to 2.23. The
server's log shows the scheduler waiting for ShareLock on `bgw_job` and the
change waiting for `AccessExclusiveLock on advisory lock [db, job, 0, 29749]`.

## Options

- **Take the job lock first.** Its tag carries field 29749, which none of
  PostgreSQL's advisory functions can produce, and the only public routines
  that take it in a mode excluding a starting scheduler are the removals
  themselves. `alter_job` takes it in ROW SHARE mode, which a starting
  scheduler shares, and then writes `bgw_job`.
- **Pause the job with `alter_job` first.** The scheduler sees the pause only
  after the commit, and `alter_job` writes the catalog the scheduler is about
  to read. It closes no window.
- **Remove first, then lock the view.** This keeps TimescaleDB's order. But the
  locked re-plan would then read a state without the removed policies, so each
  plan would need a second description of itself minus its removals to compare
  against the review. The view lock would also still hold every job start in
  the database for the rest of the transaction, the whole of a conversion's
  data move included. A plan removing several jobs is exposed exactly as below.
- **Lock `bgw_job` alone, in SHARE mode.** A starting scheduler shares that
  mode, and every writer is blocked. But it is a private relation, it moved
  schema in 2.30, and locking it needs UPDATE, DELETE or TRUNCATE on it,
  which a role that owns its hypertables does not have. A lock on the view is
  checked against the view's owner, which is why the view was used.
- **No lock on the job catalogs at all.** Chosen.

## Decision

D211. **A policy change never holds a lock on TimescaleDB's job catalogs
before TimescaleDB's own calls take it.**

- The jobs view is not locked. The privilege to lock it is no longer
  discovered or required.
- DataPlayer's own job changes queue on a transaction-scoped advisory lock,
  key `0x445054534A4F4253`, taken first. Nothing in TimescaleDB takes it. It
  keeps what the view lock gave DataPlayer: one job change per database at a
  time, so a refresh window and its source's retention cannot change at once.
- The order is: job guard, dimension metadata (the editor's), the table, then
  the job's own lock, taken by the removal, which then locks the catalogs.
  The scheduler takes none of the first three.
- A plan that removes several jobs removes them in one statement whose lock
  waits last a third of `deadlock_timeout` at most. After the first removal,
  `bgw_job` stays locked to the end of the transaction, so a scheduler starting
  a later job waits for the change while it holds that job's lock. Waiting for
  that lock in turn would close the cycle again. Giving up first refuses the
  change instead, and in one statement the gap between removals is one
  routine's run. The lock timeout is put back afterwards.

## Consequences

- A policy change made outside DataPlayer at the same moment is no longer held
  back. TimescaleDB's duplicate check refuses an addition while a policy of
  the same kind is committed, but two sessions adding the same kind at once
  can both pass it. That is TimescaleDB's own behaviour between any two
  sessions.
- A starting job no longer waits for a whole policy change; it waits only
  once a removal or an addition has written the catalogs.
- New chunk creation no longer waits for a policy change. It still waits for
  the editor when the editor changes dimensions.
- The several-removal case is bounded by timing rather than by order: the
  scheduler survives unless more than a third of `deadlock_timeout` passes
  between two removals in one statement. No public routine takes several job
  locks before the first catalog lock, so there is nothing better to order.

## Evidence

`backend/compatibility/timescale/test_job_scheduler.py` makes a job due while a
change holds its locks, waits until the scheduler has taken the job up, lets
the change remove it, and asserts the same scheduler process is still there
after two deadlock checks. It covers one removal, the editor removing two
starting jobs at once, and setting and removing a policy straight away. Before
the change it failed on 2.14.2, 2.17.2, 2.18.0, 2.19.3 and 2.23.1; after it,
the whole matrix passes.
