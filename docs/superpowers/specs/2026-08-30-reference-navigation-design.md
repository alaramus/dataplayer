# Navigating by a foreign key

## Problem

A relation says it has foreign keys — D22 put them in the relation model, and
the structure tab draws a badge for each — but nothing can be done with one. The
commonest question asked of a row is "what is this key pointing at", and today
it is answered by reading the value, opening the other table by hand and typing
a filter.

The obvious implementation is the wrong one. The client already holds the FK's
columns, the target's node id and the target's columns; pairing them up and
building an equality filter takes ten lines in the grid. Those ten lines put
three rules about relational sources into a screen that is supposed to know
nothing about any source: that the two column lists are parallel, that the id
names a place the client may address, and that an empty key means an empty
answer rather than every row.

The old application went further in that direction and paid for it. It copied
each constraint onto every column it touched, which split this exact two-column
key into independent one-column links, and it grew a client-side registry of
"weak links" that could be drawn between any two columns of any two connections.
That registry is a separate feature with its own storage and its own truth, and
it is not part of this slice.

## The source issues the target

`SupportsReferences.follow_reference` takes the id of the relation being looked
at, the source's own name for one of its references, and the values that row
holds for that reference's columns. It answers with a place to go.

Everything the answer is made of is read from the source at the moment of
asking: which references the relation has now, which of the target's columns
each local one stands for, what the target is called now, and what its columns
can be looked up by. Nothing is taken from the request except the name and the
values, and both are checked against that reading before a filter is built — a
name that is not a reference of this relation is refused, and values that are
not exactly its key are refused.

The client's whole influence on the resulting query is which reference of which
row it pointed at. That is the same standard D2c holds a filter to, and the
predicate it gets back is validated a second time anyway, because it is handed
to the ordinary fetch route, which checks the column, checks that the column
declares the operator and coerces the value.

## Two answers, both about the data

`ReferencedRows` carries the target as a whole `CatalogNode` and a list of
equality filters. A whole node rather than an id and a name: `path_to` already
answers with nodes for the reason D21 gives, and the screen already knows how to
open one, label its tab and decide whether it also has a structure — so nothing
needs a second model of a node or a second table of what a kind of node affords.

`NoReferencedRows` carries a reason. Two cases reach it. A key with a missing
value names no row at all, and MATCH SIMPLE and MATCH FULL agree about that. A
key standing on a type the source will not compare through the closed filter
vocabulary — bytea is the plain example — cannot be looked up, and saying so is
better than handing back a filter the very next fetch would refuse. Neither is a
failure of the request, so neither is an error status: this is D2d, said in the
answer.

A row handle was rejected as the way to name the row. Handles exist only where
the source can version a row (D25), and a keyless table can still hold a foreign
key. The values travel instead, as the canonical text the page already holds.

## What the page says, and where the arrow goes

`FetchResult.references` lists the relation's keys: the source's own name, the
columns in key order, and a title for the target to put in a tooltip. It is one
object per key rather than a mark on each column, which is the mistake D22
already names. The target's id is deliberately absent: it arrives when the key
is actually followed, so there is no id on the page for a client to be tempted
to take apart.

PostgreSQL reads this beside the columns on every page rather than remembering
it. A constraint added or dropped between two pages would otherwise leave the
grid offering a way out that no longer exists, and the bounded read cache
already keeps a whole page for a moment, which is where the cost of asking again
belongs.

The grid draws one arrow per key, on the first of that key's columns that is
actually on screen — hiding a column moves the arrow rather than taking the way
out away. A cell with nothing in it draws none. That last rule is about the
cell and not about the key: an empty cell has nothing to act on, the same reason
a null value does not open the viewer. A composite key with this cell filled and
a sibling empty still offers the arrow, and the source answers that it names
nothing.

## Arriving

The workspace opens the rows tab of the node that came back, exactly as the
catalog opens one, and leaves the predicate where the tab picks it up. State to
watch rather than a call into the panel, for the reason `revealTarget` is state:
the tab may have been opened a moment ago and not be mounted yet.

One tab per relation, as everywhere else. Following the same key from two
different rows is the same table with a different question asked of it, and what
a tab shows is the answer to the last one. The predicate is therefore stored the
way a filter the user typed is stored, and it lands over the remembered query
rather than under it — which is the one thing the grid has to know about having
been navigated to.

## Deliberate boundary of the first slice

Only the forward direction. Going the other way — from a row to the rows
elsewhere that point at it — means searching a whole schema for keys arriving at
this relation and then asking which of the several found relations was meant.
That is a slice with a screen of its own.

No client-side link registry. A reference is what the source says it is; two
columns that happen to hold the same numbers are not a reference. If that
feature is wanted it needs its own storage, its own owner and its own answer to
what a link between two different connections means.

No editing through a reference. Picking a value from the target instead of
typing it is a good idea and belongs to the cell editor, not here.
