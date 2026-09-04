# Operation progress in the footer

The footer's right edge shows a compact progress button, like an IDE's task
indicator. It names one active operation and counts the others. Selecting it
opens the ordinary floating Processes window; starting work never opens it.
Closing or minimizing that window does not stop work.
Starting or retrying a Docker service does not also show a startup notification.
Request errors still appear where the start was requested.

## Ownership and progress

Docker lifecycle and database backup/restore already belong to durable jobs.
A paged, owner-scoped jobs listing puts active jobs first and supplies the
active count separately. The client reads it through vue-query, invalidates it
on job events and accepted commands, and polls as a fallback. Recent results
remain available after reload. Named steps use an indeterminate bar: steps do
not have equal duration and are not a time percentage.

Catalog actions register their existing requests in an application-provided
client operation registry. This covers archive, extract, upload, delete, copy
and move without branching on adapter or action names. Their results remain
in memory until reload/sign-out or Clear finished; the latest 50 are retained.
An upload reports actual transport bytes, then explicitly waits for the
server's answer. A request without measurable work uses an indeterminate bar.
Completed requests in a batch are counted separately from upload bytes.

## Controls and partial work

Server jobs offer cancellation through the existing owner-checked endpoint.
They cannot pause or resume; cancellation leaves completed external effects
in place. Cancellation during startup must still settle the row and release
the runner's bookkeeping. Repeated cancellation must not interrupt cleanup.

A client batch offers Pause after current and Stop after current while unsent
requests remain. Pausing waits at the next request boundary; Resume releases
that wait. Stopping skips only unsent requests, retains completed results,
refreshes their catalog branches, and reports how many were not started.
Unsent uploads remain in the upload form alongside refused files. No automatic
retry is introduced. Single server requests do not offer cancellation because
aborting HTTP would not stop their filesystem effects. Upload bytes are not a
resumable-upload protocol. Signing out discards local history and stops the
unsent portion of queues without claiming to abort requests already sent.

## Validation

Write tests for owner isolation and bounded job listing, immediate/repeated
cancellation, pause/resume/stop boundaries, partial failures and upload retry
contents. Browser coverage exercises the footer, on-demand window and server
job cancellation. All checks remain deferred at the user's request.
