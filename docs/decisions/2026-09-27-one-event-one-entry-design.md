# One event, one entry

## Problem

A pipeline's run ended and the Activity sheet said so twice. Succeeded, it
stayed in Working as a row marked Completed, and Recent held a message saying
what it had saved. Failed, it stayed in Working marked Failed, and Needs you
held an item saying it could not be completed — while nothing appeared on
screen at all, so the only sign after pressing Run was a number beside the
bell. A card for the failure, added the obvious way, would have made it three.

The duplication was not the pipeline's. Every job — a transfer, a backup, a
service, a source operation — was drawn by three pieces of code that each
answered "where does this show" for themselves: Working listed the jobs
listing as it was, finished rows included, until "Clear finished"; Needs you
derived an item from the same row when it had failed; the tab that started a
transfer or a run wrote a message when it ended. An access request was the
same shape: a message with an Open button, and an item in Needs you.

## Decision

One event is one entry, and the entry moves between the sections rather than
being copied into them.

- **Working holds what runs, and nothing else.** A job or a local operation
  that has ended leaves it; there is nothing to clear.
- **An ending is recorded once.** A job that did what was asked, or was stopped
  on request, is one entry in Recent: its name, its message and the steps
  behind it, one to a line — what its row in Working used to say. A job that
  failed or was interrupted is one entry in Needs you, with the same lines, and
  nothing in Recent.
- **A card is an entry arriving, not a record of its own.** It goes up when a
  job this tab saw running — or started a moment ago — ends, except a pipeline
  run its schedule started, which nobody was waiting for; and for anything new
  in Needs you since the page opened: a failure, a request for access, a
  connection that stopped answering. What was already waiting when the page
  opened is in the sheet and the count, and is not announced again on every
  reload. A card about a failure stays ten seconds rather than five.
- **Recent outlives a reload, for jobs.** Jobs are rows on the server already,
  so the endings of the last day are read again from the listing and recorded
  without a card. What a person waved away — in Recent or in Needs you — is
  remembered in the browser for two days, so a poll does not bring it back.
  Small messages such as "Row inserted" still live only in the tab (D114).
- **A local operation's ending is said by whoever started it.** An action's
  window says what came of it, or leaves the files it could not send in its
  list; Working only showed the same thing a second time.
- **A request for access is its entry in Needs you**, and its card is that
  entry arriving. The separate message with an Open button is gone.

## Rejected

- **Keep Working as a history of jobs and hide the duplicates elsewhere.** A
  section called Working that holds what stopped working an hour ago is the
  confusion the screenshots showed.
- **A collapsed "Finished jobs" section below Recent.** A job log is the
  pipeline's History window (D180) and the jobs listing; the sheet is where the
  application talks to a person, and a log of everything would be read by
  nobody.
- **Cards only for failures.** A run started by hand is waited for, and its
  success is the news the person pressed Run for.

## Consequences

- `features/activity/endings.ts` holds the rules as plain functions — what an
  ending becomes, which endings are seen as they happen, what is new in Needs
  you — and `dismissed.ts` the ids waved away.
- The log (`shared/notifications/notices.ts`) records under a stable id, once,
  and never again under an id forgotten by hand; places an entry by when it
  happened; can record without a card; and can put up a card for something it
  does not record, an `Announcement`.
- Starting a job still says so where it is started ("Copying prod out"): that
  message is about pressing the button, and the ending is its own event.
