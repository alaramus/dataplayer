# The way back along a key

## Problem

D36 gave a row a way out along its own foreign key, and said what it left out:
"Going the other way — from a row to the rows elsewhere that point at it —
means searching a whole schema for keys arriving at this relation and then
asking which of the several found relations was meant. That is a slice with a
screen of its own."

This is that slice. The question it answers is the one asked of a row of
`organizations` or of `users`: *what refers to this?* Today the only way is to
know the schema by heart, open the other relation and type a filter.

The old application answered it, and the shape of its answer is worth copying.
Its row window drew a `<` beside the primary key; pressing it expanded, right
under the key, the list of relations whose keys land there —
`public.auth_group_permissions:permission_id` and its siblings — and choosing
one loaded that relation, filtered to the rows that point at this one.

## A question of its own, asked once

A relation's own keys are part of its definition, and D36 reads them on every
page for that reason. The keys landing on it are not: finding them is a search
of everything else in the catalog. So it is a route of its own, asked once when
a relation's rows are first shown rather than on every page, and a capability
of its own — `SupportsArrivingReferences` — because a source can perfectly well
read its own keys and have no way to search for arriving ones.

Once rather than on demand, and the reason is worth stating: the cells that
offer the way back cannot be drawn without knowing which keys land on which
columns, so the question is answered before anybody presses anything. What is
genuinely on demand is following one, which is the expensive half — it reads
the far relation's columns.

The answer is deliberately the mirror of `FetchReference`: a name to send back,
the columns **of this relation** the key lands on, and a title for what points
here. The columns are this relation's because they are the cells the way back
is offered from and the values the caller already holds. What the key is called
over there, and which of its columns stand for these, stay with the source —
the same rule that keeps a target's columns out of a forward reference.

A relation everything points at can be named by dozens of keys. The answer has
a ceiling of fifty, applied in the query, because this is a menu and not a
report.

## Following it is the same call

`follow_reference` takes a direction. Both ways are the same question — this
row, this key, where does it lead — and both answer with the same union: a node
and equality filters over that node's own columns, or a reason why there is
nowhere to go.

The direction is said rather than worked out from the name. A constraint name
is unique within the relation that carries it, not within a schema, so a key of
this relation and a key landing on it can be called the same thing; a route
that guessed would sometimes open the wrong place and never say so.

Inside the adapter the two directions differ by one thing, and it is worth
naming precisely: which column of this relation is paired with which column of
the far one. A key of this relation pairs its own columns with the target's; a
key landing here pairs the columns it lands on with the ones it is made of.
Everything after that pairing — the missing-value answer, reading the far
relation's columns now, refusing a type that cannot be compared, building the
filters, describing the node through `path_to` — is one piece of code for both.

## What the screen does with it

The corner mark of a keyed cell is the way out; the way back is a second mark
in the opposite corner of the cell, on the columns an arriving key lands on.
Pressing it opens a menu of what was found, because unlike the forward
direction there is usually more than one answer and only the person reading
knows which one they meant. Choosing one opens that relation in a tab,
filtered to the rows that point here — the same arrival D36 already built,
including landing in another connection when a declared reference is what was
followed (D108).

The list is read once per relation rather than once per page: which keys arrive
does not change as the rows are paged through, and a source that cannot search
for them at all answers 501, which draws no marks and shows no error.

## Deliberate boundaries

- **No count.** The menu says which relations point here, not how many rows
  each holds. A count per arriving key is a query per key against a table
  nobody has opened yet, and the answer is one click away.
- **Only foreign keys.** A declared reference (D106) already offers both of its
  ends, so it needs nothing from this slice.
- **The row view is a separate slice.** The old application's window — one row
  drawn vertically, with `PREV`/`NEXT` across the page and both directions
  offered per column — is a screen, and it can be built over exactly these two
  routes without changing either.
