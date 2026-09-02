# What a page is for, said by the source

## Goal

Make the Processes report a monitor rather than a table that happens to list
processes. It arrived with the whole grid toolbar over it: download this page,
chart it, share a link to it, make a table out of it, open it as a query. All
of them work, and none of them is anything anybody wants to do to a picture of
what a database is doing this second.

## Decision

The commands a grid draws over a page are a vocabulary the source may withdraw
from. `FetchResult.page_commands` lists which of `download`, `chart`, `share`,
`create_relation` and `query` this relation offers; a source that says nothing
offers all five, because a page is ordinarily somebody's own data and only the
source knows when it is not.

One list rather than five booleans beside `update_supported` and its family.
The family answers five different questions about writing; this answers one —
what is this page for — and a source that withdraws one of these usually
withdraws several. PostgreSQL's reports withdraw all five in one line.

Nothing is keyed by a name on the client: the vocabulary is the server's, the
type is derived from the generated client rather than written out again, and
the grid asks `offers(command)` without learning what a report is.

## What stays

Filtering, sorting, choosing columns, copying a selection, paging and
auto-refresh. They are how somebody finds the process they came to stop, and
none of them takes the page anywhere. Insert, update, delete and import were
already withdrawn by D54 — a server-owned relation is read, never changed.

So what is left over the Processes report is: the controls for looking, and
the two commands for acting on what is found.

## Rejected alternatives

- **A flag per command.** Five booleans and five reasons to answer one
  question.
- **A mode on the node — "monitor" versus "data".** The client would branch on
  a mode name, which is the thing every capability in this project exists to
  avoid.
- **Hiding them on the client, by node kind.** Then the client learns what a
  report is, and the next source with a live view has to be taught separately.
- **Leaving them.** They work; that is not the same as belonging.

## Deferred

Withdrawing a command from a relation rather than a whole class of them, and
saying *why* one was withdrawn — the pattern `update_reason` uses. Nothing
shows a reason for an absent button today, because an absent button is not
asking a question.
