# The bar at the foot of the screen

## Goal

Give a home to the commands that belong to a connection and to nothing on
screen.

Almost every button in this application hangs off the thing it acts on: a
table's commands are in its grid, a node's are in the catalog's menu, a
connection's own form opens from its row or from the icon of its tab. A few
have no such thing. Queries were the first: a console is written against a
connection and belongs to a person, so there is no node whose toolbar it could
live in — and it ended up beside the plus in the connections column, which is
where new connections are made and nothing else of that kind would fit.

The room at the foot of the screen has been reserved since the workspace was
built and empty ever since. This is what it is for.

## Decision

The bar lists commands of the connection being read. One rule, in one place:

- a command is enabled while a connection is being read **and** that connection
  can do the thing;
- otherwise it stays in the bar, greyed out, and its tooltip says which of the
  two is missing. Hidden buttons would make the bar change shape as somebody
  walks about, which is a bar they have to read every time;
- the bar also says which connection the commands are about. A row of buttons
  whose subject is somewhere else on the screen is a row nobody trusts.

`features/workspace/commands.ts` is that rule as plain functions, so it can be
read and tested without mounting anything. `CommandBar.vue` renders it into
`AppLayout`'s status slot.

Which connection is being read is `activeConnectorId`, already derived from the
layout tree rather than kept beside it (D12). Nothing new is stored.

## Capability, not adapter type

Whether the command is offered is the source's own answer, never a branch on
which adapter it is (D62). For Queries that answer is the query profile itself:
a source that does not run queries has no profile and answers 501, which is
exactly what "does not run queries" means.

Three states, not two. "We have not asked yet" is not "no": telling somebody
their PostgreSQL connection does not run queries for the half second before the
answer arrives is a worse lie than saying nothing, so the button is disabled
and says it is asking.

## What moves

`open-queries` leaves the connections column. Pressed from the bar it opens the
one library panel filtered to the connection it was pressed from — the filter
travels as a piece of state the panel takes, the way `revealTarget` and
`followTarget` already do, because there is one library panel however often it
is opened and a panel's props are bound when it is first drawn.

## Rejected alternatives

- **Leaving Queries in the connections column.** It was there for want of
  anywhere better, and the next four connection-scoped commands would have had
  to go there too.
- **A command per open connection.** The bar is about the one being read; a bar
  that listed every open connection would be a second connections list.
- **Hiding what does not apply.** See above: shape first, then content.
- **A panel per connection for the query library.** D65 already settled that,
  and this changes nothing about it: the connection is a filter.

## Deferred

Everything else the bar is meant to hold — a backup, a restore, a database
user, a search across the source — arrives with the slice that implements it.
The right half of the bar is still free for what a status line is usually for:
what is running, and what the last request cost.
