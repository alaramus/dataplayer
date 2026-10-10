# Reviewed actions from rows picked in a report

Date: 2026-10-10. Settles D209.

## Problem

D208's deviation: chunk maintenance was "not offered from a selection in the
Chunks report". A report row offers only commands that run at once (D70), and
drop, move, reorder, detach and merge are reviewed jobs (D123). The submenu's
window chooses whole chunks by time, which is the wrong tool when somebody is
looking at the exact chunks they mean: three chunks out of forty, two
partitions of a hash hypertable, chunks with a gap between them.

The Chunks report is database-wide. Its rows belong to many hypertables, and
an action is about one catalog node (D9). The client cannot compute a node id
from a row: a node id is the source's encoding.

## Decision

D209. **A report may offer a reviewed action over the rows picked in it.**

- The report declares a *picked-rows action*: the name of an existing action,
  the columns that name a row, and a title and an icon for the grid's
  toolbar. It travels on the fetch result beside the row commands (D70).
- The grid offers it while rows are picked. Pressing it sends the picked rows'
  keys to the source, which answers with the node the action is about and the
  parameters that name exactly those rows, or refuses: rows of more than one
  hypertable, a row that is no longer there.
- The client opens the action's ordinary window (D9) for that node, with those
  parameters set and the fields they replace left out. The preview, the review,
  the fingerprint and the job are the action's own; nothing about running it is
  new.
- The parameters name the chunks themselves, not a window over them. A plan
  over named chunks reads each one again and refuses a name that is not a
  chunk of that hypertable any more; it applies the same filters the window
  does (already in the tablespace, compressed, adjacent for a merge).

The source keeps both meanings: which column names a row, and what node a row
belongs to. The client learns neither.

## Offered

From the Chunks report: drop, move, reorder, detach, merge and merge with reads
going on. Split takes a point and attach a table that is not a chunk, so
neither is a selection of chunks.

## Rejected

- **Turning the picked rows into a window.** Rows with a gap, or one partition
  of several, are not a window; the plan would act on rows nobody picked.
- **A row command that runs at once.** D70's commands are for what needs no
  review. Dropping chunks is the opposite.
- **Computing the node id on the client.** It would make the client know how
  the source writes one.
