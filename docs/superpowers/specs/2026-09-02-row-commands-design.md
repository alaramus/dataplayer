# Commands over the rows of a relation

## Goal

Make the Processes report a task manager rather than a table about one. It
lists what is connected and what each backend is doing; reading that and being
unable to stop a statement that has been running for an hour is half a tool,
and the old application had the other half — `cancel` and `terminate` on a pid.

## Why an action would not do

An action (D9) is about a catalog node: rename this table, drop that schema. A
process is not a node, and the two shapes that were available were both lies:

- **A delete that is not a delete.** The grid's delete button removes rows from
  a relation; a report is a subquery with no row to write back to (D42), and
  making terminate wear that button would mean a report claiming to be
  writable.
- **A form asking for the pid.** An action on the report node with a `pid`
  parameter works today and asks somebody to type in a number that is already
  on their screen, next to the row they are looking at.

## Decision

A relation may declare commands of its own, and the grid offers them over the
rows that are ticked.

`RowCommand` carries a name, a title, a description in the source's own words,
whether it is destructive, the access level it needs, and `identified_by` — the
column whose value names a row. One column, because that is what every command
that exists needs; a compound key is a different contract and is not invented
before somebody has one.

`SupportsRowCommands` has two methods: what this node offers, and run one of
them. There is no third place a name could resolve differently, and what a
client may do is decided by the first rather than by the vocabulary existing at
all — the same shape `SupportsActions` has.

The commands travel on `FetchResult`, filled in by the route from the composed
adapter, exactly as `export_supported` is: a capability belongs to the whole
source, not to the module that read the page. They are filtered by what the
caller holds, so a command nobody may run is not drawn at all.

`POST /{connector_id}/rows/command` takes `{node_id, name, keys}`. The keys are
the source's to read: nothing on the way in knows what a process id is, and a
key that means nothing to the source is refused by it rather than by a rule
restated in the route.

## What PostgreSQL does with it

Two commands on the Processes report and on no other node:
`pg_cancel_backend` and `pg_terminate_backend`, both requiring `structure` —
the strongest level that can be given away, because stopping somebody else's
work is not what "may write rows" was granted for.

The statements are written in the repository. A request chooses one by name
from the two; the pids are bound as an array parameter and never formatted into
anything. The connection running the command is skipped, so a request cannot
kill the connection carrying it, and a pid that no longer names a backend comes
back as a refusal rather than as an error — `pg_cancel_backend` answering false
is an answer.

The result is a count and a list of what was refused, each in the source's own
words. A key that is not an integer is refused beside them: one bad key does
not stop the rest.

## Two things the grid had to learn

**A relation may ask to be re-read.** `FetchResult.refresh_seconds` is what the
source thinks the relation is worth: five for the Processes report, nothing for
everything else. The grid takes it as the starting interval only where nobody
has chosen for that relation — which means the stored choice needs three states
rather than two, since Off has to survive a source that suggests five seconds.
The suggestion is never written down: it is a default, not a decision.

**A selection holds the refresh.** A page arriving underneath a ticked row
takes it away, and on a list of processes that means the row you meant to
terminate is no longer the row you ticked. So "rows are selected" joins the
list of things that skip a tick, beside a cell being edited.

## Rejected alternatives

- **An icon per command on the client.** That is a table of names on this side,
  which is what declaring them on the source exists to avoid. The buttons are
  labelled with the source's own title and explain themselves with its
  description.
- **Row handles as keys.** A handle is a versioned identity of a row in a
  relation (D25); a report issues none, and a position in a list that changes
  every second is the wrong thing to name a backend by.
- **A confirmation written by the client.** The question names the command and
  its subject; the sentence under it is the source's description.

## Deferred

Killing a process from anywhere but the grid, a compound key, and commands on
file rows. The capability is there when somebody has one.
