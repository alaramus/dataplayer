# One row, read downwards

## Problem

A wide relation is unreadable a row at a time in a grid. Twenty columns of one
row are twenty horizontal scrolls, and the thing a person is actually looking
at — this customer, this order — is spread across a strip two centimetres tall.

The old application answered this with a window it called Data Details, and it
was the screen people worked in rather than a detour: one row drawn downwards,
column by column, with the type beside each value, badges saying which keys the
column takes part in, and `PREV`/`NEXT` to walk the rows without going back to
the grid. Both directions of key navigation lived there too — the forward arrow
on a foreign key, and the list of what points here under the primary key.

D110 built both directions over the routes. This builds the screen they were
always meant for.

## The same page, not a second read

The row view reads the page the grid is on, by the same query key, through the
same `useRowsPage`. Opening a row therefore costs no request: the answer is
already in the client's cache, and the two screens cannot disagree about what
the row holds, because there is one answer and both are reading it.

That decides how a row is named, too. Not by a row handle: a handle exists only
where a source can version a row (D25), and a relation with no key at all still
has rows worth reading. Not by its values either. It is a position — which page,
which row of it — and the page travels with it because the page is what the
position is relative to.

Walking crosses pages. `PREV` and `NEXT` move within the loaded rows and, at
either edge, move the request by exactly the limit it already carries and land
on the first or last row of the new page. A reader should not have to know that
a page is how the source hands rows over; the request stays one the grid also
uses, so the page a walk lands on is one both screens then share.

The two controls stay at the foot of the panel, `PREV` against its left edge
and `NEXT` against its right, with no row label between them. The table owns the
remaining height and scrolls inside it. Its column tracks are fixed independently
of the current values, so walking from a short row to a long one changes the
data and not the geometry around it.

## What each line says

The value, the type, and the badges. The badges come from the relation model
and nowhere else — a page of rows knows nothing about a primary key — so a node
the source will not describe simply has none, and everything else about the
screen still works. That is how a CSV is read here.

Beside the value: the way out along a key of this row, the way back to what
points at it, and a copy button. All three are per column, because that is
where the value is.

## One panel per relation

The row view is a panel of a relation, not of a row, and opening another row
tells the panel rather than opening a second tab — the same two steps every
other panel of a node uses. A tab per row would fill the strip by reading a
table.

It does not follow the grid's selection. The old window did until it froze
itself the moment the grid moved to another relation, and the freezing is the
tell: the useful state was the frozen one, on the row somebody had chosen to
look at.

## Deliberate boundaries

- **No editing.** The old window had an `EDIT` button. Editing a row is the
  grid's cell editor and its rules about what a source will accept; a second
  editing surface is a second set of those rules.
- **No `ctid` line.** The old view listed the physical row identity as a column
  of the row. It is a row handle by another name, and D42 already decided that
  a row's identity is the source's business rather than a value on screen.
- **No count of what points here.** D110's boundary, unchanged: the menu says
  which relations point at this row, not how many rows each holds.
