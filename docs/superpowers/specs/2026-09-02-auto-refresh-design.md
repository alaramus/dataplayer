# A grid that re-reads itself

## Goal

Watch a relation change without pressing anything. A process list, a queue
table, a job log — the reason to have one open is that it moves, and the tab's
reload button asks the person to be the timer.

## Decision

Auto-refresh is a property of the grid, not of the tab. The tab's reload
already exists and belongs to the panel engine, which knows nothing about the
application (D12); an interval, a pause and a persisted choice per relation are
knowledge about relations, and `DataGrid.vue` is what holds those.

One control in the grid's own toolbar: a menu of 1 s, 5 s, 10 s, 30 s, 1 min
and 5 min, plus Off, which is the absence of an interval rather than a seventh
one. The chosen interval is written on the button. A grid that refetches by
itself and looks exactly like one that does not is a grid whose rows move for
no reason the user can see, so the label is the point — not decoration.

## The pause is the contract

A tick is not "fetch now". It is "fetch unless something says not to", and what
says not to is one list, in `autoRefresh.ts`, that both the timer and the
tooltip read:

- a cell is open in the editor — a landing page would throw away what is typed;
- a row is being written in the grid — the same;
- the tab is not on screen, either because its section shows another one or
  because the browser window is hidden — a kept-alive panel would otherwise
  poll the source for ever with nobody looking;
- a read is already running — a second one would queue behind it, and a queue
  of skipped ticks would all land at once when the first returns.

A held tick is skipped, never queued: the next one is at most an interval away.
Coming back on screen reads once immediately, because the answer to "what is
there now" is what the tab was left refreshing for.

The order matters and is asserted: while a cell is being saved a read is always
running too, and reporting that instead of the editing would explain the wrong
thing.

## What is remembered

The interval is stored per `connectorId + nodeId`, beside the columns and the
query that are already stored that way — a table somebody watched every five
seconds yesterday is a table somebody is watching. Off removes the entry rather
than storing a null, so a relation nobody ever watched and one somebody stopped
watching are the same state. A stored value that is not an offered interval is
discarded rather than trusted, because the offered set may change.

## Rejected alternatives

- **Auto-refresh on the tab's reload button.** It would put a timer into the
  panel engine and make every kind of panel answer a question most of them have
  no answer to.
- **One interval for the whole application.** The reason to watch a process
  list every five seconds is not a reason to hammer a hundred-million-row table.
- **A ticking clock with no visible state.** The old application refreshed
  some views on a timer with nothing on screen saying so.
- **Refetching through vue-query's `refetchInterval`.** It has no notion of a
  cell being edited, and its retry and window-focus behaviour would have to be
  argued about separately; the grid already owns an explicit refresh that
  bypasses the read cache (D31), and auto-refresh is that same refresh on a
  timer.

## Deferred

A source saying what a sensible interval for a node is — a process list wants
five seconds without being asked. That is a contract on the fetch result and
belongs with the slice that makes the process report a task manager.
