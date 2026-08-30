# Promising uniqueness, and pointing at another relation

## Problem

D39 builds indexes, and an index is not a promise. A unique index happens to
reject a duplicate, but nothing in the schema says the values are meant to be
unique, and nothing may point at them. A foreign key is missing entirely: the
grid can follow one (D36) and the structure tab draws them, but they can only
be made outside the application.

Two of the five constraint kinds are reachable here. A check constraint is not,
and will not be through this door: its body is an expression, which is the
thing D2c refuses. An exclusion constraint is an operator vocabulary of its own.

## What a constraint adds over an index

Three things, and they are why this is a separate command rather than a flag on
D39.

It is a **named promise in the catalog**, which other objects can depend on. A
foreign key can point at a unique constraint, and PostgreSQL then holds that
constraint in place — the refusal D39 already names when someone tries to drop
the index underneath one.

It carries **behaviour**: what happens to a referencing row when the row it
points at changes or goes away. That is a closed vocabulary, and it is one this
project already has — `RefAction` is in the relation model because the model
reports it.

It can be **unenforced**. A constraint added `NOT VALID` promises nothing about
the rows that were already there. The model now says so, which it did not
before: `validated` travels with every foreign key and check, because showing
an unenforced promise as an enforced one is a lie the reader cannot catch.

## Nobody types a name, again

The rule D39 set holds: PostgreSQL derives the name from the relation and the
columns and makes it unique against the schema, and the answer says which
constraint appeared by reading the relation again. Adding one adds exactly one,
so the difference is a single name.

## What may be pointed at is published, not inferred

A foreign key needs the target's columns to carry a unique key. Which of a
relation's constraints and indexes qualify is PostgreSQL's rule — a primary
key, a unique constraint, or a bare unique index, but not a partial one, which
promises uniqueness only among the rows its predicate admits.

So the relation publishes `candidate_keys`: the column sets it can be pointed
at, each named by whatever provides it. The dialog offers those, the adapter
checks against those, and neither works the rule out from the constraint list.
A client that sent something else is told the target has no such key, by name,
rather than handed SQLSTATE 42830.

The target itself is a catalog node id, handed back exactly as it was given
(D21). The screen finds the candidates by asking where this relation lives and
what else lives there — two ordinary catalog calls — never by taking an id
apart.

## The data can stop both, and it is counted

This is the fourth command the rows can refuse, after D37, D38 and D39, and by
now the shape is settled enough to be one module: a bounded count, and whether
the count is the whole truth. `counting.py` holds all four.

A unique constraint is stopped by values that repeat — the same count D39
already makes, now shared rather than copied. A foreign key is stopped by rows
whose key names nothing in the target, counted with the same rule PostgreSQL
would apply: a row holding a null anywhere in its key satisfies MATCH SIMPLE,
so counting it would refuse a key the server would have accepted.

The two answers stay separate — `RepeatingValues` and `UnmatchedRows` — rather
than one count with a reason beside it. They lead to different work: one value
has to be made unique, one row has to be corrected or removed. A screen reading
which it was out of a sentence would be parsing prose.

The count can itself be refused, and that is new: comparing a `date` with a
`varchar` fails in the counting query before it could fail in the constraint.
So the SQLSTATE mapping travels with the count too, and the answer is a bad
request rather than an unwell source.

## A drop takes nothing with it, and stops short of the primary key

No `CASCADE`, the rule D27 set for a column: a foreign key standing on this
unique constraint stops the drop instead of vanishing with it.

A primary key is refused outright in this round — not because PostgreSQL minds,
but because a relation without one cannot have its rows edited at all. The
handle that versions a row is built from the key (D25). Losing that as a side
effect of tidying a constraint list is a consequence that needs a round of its
own to state.

## Deliberate boundary

- No `NOT VALID` and no `VALIDATE CONSTRAINT`. A two-step constraint is a
  second state in the model and a second command, and the count already tells
  the user what a validation scan would find. Existing unvalidated constraints
  are shown as such.
- No check constraints, no exclusion constraints, no deferrability, no
  `MATCH FULL`, no `NULLS NOT DISTINCT`.
- The request waits for the scan, as it waits for an index build in D39. Jobs
  are Phase 4.
- No cross-connector references. A foreign key lives inside one database, and
  the target is a node of the same source.
