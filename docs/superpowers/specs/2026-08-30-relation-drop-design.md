# Dropping a relation, and seeing what goes with it

## Problem

Every round so far deferred this one, and always with the same sentence: a
destructive round of its own. What made it worth deferring is not that `DROP
TABLE` is hard to write. It is that a drop can take things with it that nobody
asked about — a view built on the table, a foreign key in another table — and
that PostgreSQL will only do that when told `CASCADE`.

So the question the feature has to answer is not "are you sure". It is "what
exactly would go".

## Asking an action what it would do

The action mechanism had no way to ask anything. An action is declared,
offered, filled in and performed; whether it would succeed was found out by
performing it.

`Previews` is a `runtime_checkable` Protocol with one method, checked the way
`TakesFile` is, and `ActionInfo.previews` is derived from an `isinstance`
rather than declared beside the class — a flag and an implementation can
disagree, an `isinstance` cannot. Most actions have nothing worth previewing: a
folder about to be created is described entirely by the name in the form. Those
answer 501.

The answer is one model:

```
ActionPreview: summary, items[], blocked
```

A sentence, a list of lines and a verdict. Every part of it is the source's,
and the dialog renders it without knowing what is being previewed — which is
the whole reason a generic form can show the consequences of a cascade while no
part of the client learns what a cascade is.

Three things follow from the answer depending on the parameters:

- it is re-asked whenever the form changes, debounced, with late answers
  dropped by sequence number, because ticking a box is the thing that changes
  it;
- it needs the level the action itself needs — reading what a drop would
  destroy is not a lesser thing than the drop for anybody deciding whether it
  is safe, and the list names objects the caller may not otherwise see;
- `blocked` turns the submit button off, since "what would happen" was answered
  with "nothing, and here is why".

## The preview is the drop, rolled back

What a cascade reaches is written in `pg_depend`. A recursive query over it
would be a second implementation of PostgreSQL's own rules — wrong the first
time an extension adds a kind of dependency, and wrong in the worst possible
place, because somebody reads the answer while deciding whether to destroy
something.

`PostgresSession.rehearse` therefore runs the statement inside a transaction
psycopg is told to roll back whatever happens, keeps what the server said, and
returns that. What the preview lists cannot disagree with what the drop does,
because it *is* the drop. The precedent is D38, which asks the parser whether
two types convert rather than restating the coercion rules.

Two kinds of answer are kept:

- a rehearsal that succeeds raises notices — `drop cascades to view …` — which
  are the server describing what it did;
- a rehearsal that is refused carries the list of what stands in the way in the
  DETAIL field of `2BP01`, and **only that field** is passed on. The text of an
  exception is what carries the connection string; nothing else of a failure
  crosses the boundary. A code with no DETAIL — a lock timeout — contributes no
  lines at all, only the sentence this side wrote for it.

Neither is parsed. They are lines, and lines are what is shown.

## It takes the locks, so it is held to a timeout

A rehearsal is a real `DROP`, so it takes `ACCESS EXCLUSIVE` on the relation
and on everything it would cascade to. That is the price of an exact answer,
and it is bounded rather than paid indefinitely: `SET LOCAL lock_timeout` to
two seconds. A question about what would happen must not become an outage, and
a rehearsal that cannot get the lock says so — which is itself worth knowing
before pressing the button.

## The drop

`DROP TABLE`, `DROP VIEW` or `DROP MATERIALIZED VIEW`, composed from the kind
the catalog gave for the node rather than from a guess, with the identifier
through `Identifier` and `CASCADE` appended when the form says so. A system
relation is refused before any of that. `2BP01`, `55P03` and `42501` are named
in this side's own words, so a refused drop reads the same as the preview that
predicted it.

## Deliberate boundary

- **One relation at a time.** `bulk` is false, unlike deleting files: one list
  of consequences cannot be told apart into five relations' worth by whoever
  reads it, and a cascade is exactly what makes them not independent.
- **The preview is a moment, not a promise.** Something can come to depend on
  the relation between the question and the answer. The drop decides, and
  refuses on its own terms.
- **Nothing is dropped but a relation.** Not a schema, not a column — those
  have their own commands or their own round.
- **An open tab outlives what it shows.** A dropped relation leaves its data
  tab in place, to fail on its next read like any node that has gone; the
  workspace can follow a renamed node (D32) and has no word yet for one that
  is not there at all.
