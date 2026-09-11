# The row of commands above a table

## Problem

Twenty commands, in one run, in an order nobody chose.

```
▽ ⇅ ▥ ⧉ ⟳ ⇥ 📋 ⭳ ⤴ 📊 ⊞ ‹› ⌨ ⛭ ＋ − ⟳ ⌖        Rows 100
```

Nothing said where one kind of command ended and the next began, so reading the
row meant reading all of it. Worse, the row was assembled out of `v-if`s: a
command the source could not carry out was not drawn at all, so a file showed
eleven buttons, a table eighteen and a query result eight — and the fourth
button along was a different command on each. A place cannot be learned if it
moves.

The one control on the row that did not do anything to the rows — how many of
them a page holds — sat at the far end of it.

## Two rules

**Nothing is hidden for want of support.** A command the source will not carry
out stays where it is, greyed, and says why when somebody points at it. This is
the answer the command bar already gives (D69) and it is here for the same
reason. The cost is real and was accepted deliberately: on a CSV file a whole
group can be grey, labelled, and useful to nobody. What is bought with it is
that the row is the same row everywhere.

**The commands are grouped by what they act on, and each group is named.**

| Group | What is in it | Why it is one thing |
| --- | --- | --- |
| The view | filters, sort, columns | narrows what is on screen and touches nothing |
| Read it as | structure, query, document, chart | each opens a tab of its own on the same rows |
| Take it out | copy, download, share, keep as a table | out of the grid, and read-only |
| Change the rows | paste, bring rows in, insert, delete, the source's own commands | everything that writes, and nothing else |
| This tab | auto-refresh, re-read, show in catalog | about the tab rather than about the data |

The order is the order of a working session: narrow what you see, look at it
another way, take it out, change it. That everything which writes ends up in
one group, apart, at a distance from everything that reads, is half of why the
grouping is worth the room it takes: it answers "where do I look" and "what can
I press by accident" at the same time.

The names are drawn over the groups, in the smallest legible type. They are
read on the first visit and ignored ever after, which is exactly what a label
should cost.

## Two kinds of off

The distinction that makes the sentence worth writing:

- **This source never will.** A CSV file does not sort, whatever anybody does.
  "This source does not sort rows" — a person can stop looking.
- **Not this second.** A table deletes rows once one is ticked. "Tick a row
  first" — a person can act.

They are worded apart and drawn the same. Two shades of grey in one row is a
distinction nobody stops to compare, and the sentence is where the difference
lives. When both apply, the first wins: "tick a row" under a button that will
never delete anything is a lie, and a lie under a greyed button is worse than
the vaguer truth.

## What it cost in the kit

Quasar gives a disabled button no pointer events, so a tooltip hung on one
never opens — which would have made the whole scheme silent exactly where it
has something to say. `AppIconButton` now wraps its disabled shape in a span
and hangs the tooltip there. Only the disabled shape is wrapped: the enabled
button is in a hundred places that were laid out around it.

That removes D69's known deviation for icon buttons rather than repeating its
workaround at every call site.

## The one thing this cannot know

A source declares commands of its own — `Vacuum` for PostgreSQL — and the
application draws them without knowing what they are (D70). To put a button in
a group you have to know what it does, and the declaration says only whether a
command is *destructive*, which is not the same as whether it *writes*:
`Analyze` destroys nothing and writes statistics.

They go in *Change the rows*. That is true of every source command that exists
today and not known to be true of every one that could exist. If a reading
command appears, it will sit in the wrong group, and the fix then is a field on
the declaration saying which it is — a change to the schema and to every
adapter that declares commands, which is not worth making before there is
something it would place correctly.

## Rejected

- **A "more" button over the tail.** The shortest row of all, and it puts four
  commands somewhere other than where they were learned — the thing this whole
  change exists to stop.
- **Wrapping onto a second line.** Same objection, plus the row's height would
  then depend on the panel's width.
- **Two shades of grey for the two kinds of off.** Considered and dropped: see
  above.

The bar scrolls sideways instead. On a narrow panel the far commands are
reached by scrolling to them, and they are still in the order they always were.
