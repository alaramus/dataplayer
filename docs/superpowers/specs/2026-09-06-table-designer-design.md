# Designing a table

## Problem

Two paths already end in a new relation, and both start from data that exists.
D43 brings rows from one source into another; D45 loads a delimited file, and
the table it makes has one text column per column of the file, because a file
states no types. Neither can make an empty table, and neither has anywhere to
put a key, an index or a check — they take their shape from the rows.

Everything a table actually needs is decided before there are any rows: which
columns, of what types, which of them may be empty, what the key is, what is
numbered by the database, what may not repeat, what points at another table,
what the database should refuse. That is a screen, not a form of fields, and it
is the one thing a person opening a database expects to be able to do.

The awkward part is that nearly every one of those answers is a piece of SQL
syntax, and [D2c](../../architecture/sources/contract.md) refuses SQL typed into
a field. A column default is a literal because of it (D30); an index has no
predicate and no expression because of it (D39). A table designer that took the
same shortcut would hand the browser a text box for `total >= 0` and compose the
statement around it, which is the door this project closed on purpose.

## What the old application did

The legacy pair had this screen. `CreatTable.vue` listed fields with an
inspector for the selected one, type parameters and controls for keys;
`useTableCreate.ts` opened it as a window and submitted the fields together with
the SQL the browser had already composed; `table_generator_base.py` assembled
that SQL out of strings, and gave an index one column.

Three things there are worth taking: designing the objects together rather than
one `ALTER` at a time, an inspector for the object that is selected, and showing
the statement before it runs. Three are not: SQL composed in the browser, SQL
composed by string concatenation on the server, and an index model that cannot
express a composite key.

## Two steps in one window

The editor is the object tree on the left, the selected object's properties in
the middle, and the SQL of the current draft on the right. The footer says what
the draft holds and carries one button, **Review SQL**.

Review is the second step of the same window, not a panel underneath it. It
replaces the tree, the inspector and the SQL pane with the destination, the
complete script, **Back to definition** and **Create table**. The first sketch
opened a pane below the editor and left both on screen, which made creating the
table look like another edit; a step of its own is what makes the decision a
decision. Going back changes nothing about the draft, and typing anything
returns to the first step, because what would be created is then no longer what
was read.

Only the review step creates anything, and only the plan the server last
composed.

## The definition is a model, not the contents of a form

What crosses to the server is a `TableDefinition`: columns, an ordered primary
key, unique constraints, checks, foreign keys, indexes, a partition strategy and
table options. Every part of it is typed, forbids unknown fields and is bounded
— a hundred columns, thirty-two indexes, thirty-two columns in a key. The editor
holds something else: a draft with half-finished objects in it, an index whose
key names nothing yet, a length being typed. One function turns one into the
other, and it leaves the half-finished objects out rather than sending them as
something else.

Every draft object carries an id the browser made up, and keys, indexes and
expressions refer to columns by that id. Renaming a column therefore changes
nothing else, reordering changes nothing at all, and a problem the server finds
comes back naming the object the editor should select. Removing a column names
everything that would go with it before it goes: the primary key, the indexes
over it, the checks that mention it, the column computed from it.

How a column is filled in is a discriminated union — nothing, a literal, a
source-published function, an identity column, or a stored generated expression.
Two of those cannot be in the request together, which is the point of the union:
a default string kept beside a generation mode can hold both, and then somebody
has to decide which one wins.

Column types take parameters here — a length, a precision and a scale, and
arrays — which the smaller vocabulary behind D27 deliberately does not. That
vocabulary is what an existing relation offers for a new column, and widening it
would change what every existing caller may send. The designer publishes its
own, richer list, with the same codes where the two overlap, and says per type
which parameters it takes and whether it can be an identity column.

## Expressions, not SQL

`now()`, `total >= 0`, `status IN (…)`, `lower(order_number)` — the examples this
feature exists for are all expressions, and none of them may arrive as text.

So there is a closed expression model: typed literals, a reference to a draft
column, comparisons, boolean groups, negation, null tests, bounded membership in
a list of literals, arithmetic, casts to published type codes, and calls to
functions the source advertised **by code**. A code resolves through a registry
that fixes its fragment, its arity and the contexts it may appear in, so a name
nobody published resolves to nothing rather than to a call. There is no path
from a string in a request to a fragment of syntax; a statement separator, a
subquery and an arbitrary identifier are not things the model can hold.

The contexts are not decoration. PostgreSQL requires an index expression and a
stored generated column to be immutable, so `now()` may fill a column and may
not index one — the server's rule, published per function rather than learned by
the browser. A default may not read a column of the row it is writing, and a
generated column may not read another generated column; both are refused where
the object is composed, with the column named.

Two guards, and they are not copies of each other. The model is recursive, so
Pydantic recurses on the way in and a deeply nested payload would arrive as a
crash rather than as a refusal: the raw JSON is walked iteratively and turned
away before it is parsed. Then the tree that did parse is measured — at most
eight levels and a hundred parts per expression — before the composer walks it.

## One composer, planned and not executed

The plan a person reviews and the statements that run are produced by the same
function from the same definition. A second composer for the preview would be a
second thing to keep in step, and the first time the two drifted the review
would be a lie.

Planning executes nothing. That is deliberately not D46's rehearsal, which
carries a change out and rolls it back: rolled-back DDL still takes locks and
still fires whatever the server hangs off it, and this runs on every pause in
the typing. A plan is a composition plus what the server was asked about it —
which methods it has, which operator classes and collations, which version,
which of the wanted names are already taken in the schema, and what each foreign
key's target publishes.

The plan carries the statements, each tagged with the draft id of the object it
belongs to, warnings, per-object problems, and a fingerprint over the composed
statements and the destination. Creating sends the definition and that
fingerprint, and the server composes again from the definition: statements never
travel in a request, so nothing a browser sends can become SQL. A definition
that no longer composes to the reviewed statements — because a name was taken
meanwhile, because a target moved, because the draft changed — is refused
instead of run.

A definition with problems is an answer, not a failure. Which object is at fault
and why is the useful part, and the editor shows all of them at once. Creation
is one transaction: a table whose second index the server refuses leaves nothing
behind.

## What the server decides, so the browser cannot

- **Names.** An index nobody named gets the name PostgreSQL itself would compose,
  nudged past whatever the schema already holds; a name somebody typed is
  refused when it is taken, never silently replaced. A taken table name is a
  conflict, never an implicit `DROP` or `CASCADE`.
- **A key column must have a value.** PostgreSQL would add the `NOT NULL`
  silently; a column shown as optional and quietly made required is a lie the
  form would be telling.
- **A partitioned parent's keys** must hold every partition column.
- **`SET NULL` on a required column** is refused next to the mapping that chose
  it, and `SET DEFAULT` on a column with no default is a warning: the server
  accepts that one and fails on the first delete, a long way from the form.
- **A foreign key needs a candidate key** the target publishes (D22) — a column
  called `id` is not evidence of one — and the two sides must be comparable.
  That last question goes to `pg_operator`, and it has to follow implicit casts:
  `=` for `varchar` is `text`'s operator, so the first version of the query
  refused a key between two `varchar` columns. The test that caught it is why
  this is written down.
- **Index method limits** — unique, several columns — come from
  `pg_indexam_has_property`, as they already do for D39; whether a method can
  carry `INCLUDE` columns is a property of the method too.
- **An index that repeats a key** is refused: a primary or unique constraint
  builds its own index, and a second one over the same columns is a copy of it
  maintained on every write.
- **Null-distinctness** is offered only where the server is new enough to have
  it.

## The editor

Three panes on a desktop window; the SQL moves below the inspector on a narrow
one, and the navigation joins it on a very narrow one. The SQL pane shows the
statement the selected object is responsible for, with the full script behind a
disclosure, and dims while a new plan is being worked out rather than emptying —
what it said a moment ago is the closest thing to the truth on screen.

Planning is debounced, and each request carries a revision the answer echoes, so
an answer about an older draft is dropped instead of shown as the current plan.
Only the latest successful plan can enable review.

The panels do not receive the draft as a prop, and they cannot inject it either.
A floating window mounts its content under the window host rather than under the
component that opened it, so a `provide` from the designer is not on that parent
chain — the first version of this editor rendered nothing at all for exactly
that reason. Each open designer registers its draft under a name and hands the
panels the name. Editing then goes straight to the shared draft, instead of
every field becoming a binding and an event to avoid mutating a prop.

Closing a draft that was touched asks first — through the window frame's own
close as well as through Cancel.

## Deliberate boundaries

- **PostgreSQL only.** The models, the routes and the editor are source
  independent; the vocabulary, the limits and the composer belong to the
  adapter. Another database publishes its own, and answers 501 until it does.
- **One destination.** A draft is created in one schema, resolved from a
  source-issued node id, and the connector is fixed for the life of the draft.
- **No temporary tables.** Their lifetime is a database session, and a pooled
  request cannot promise one.
- **No exclusion constraints yet.** They need operator metadata per method and
  per type, beyond the operator classes the options call publishes today.
- **A draft lives in its window.** Nothing survives a reload, and a second
  session sees nothing of it.
- **Nothing offers to open the new table.** The action returns its source-issued
  id and the branch of the catalog reloads, so it is there to click.
- **Data is not part of this.** Rows, migrations, triggers, grants, policies and
  installing extensions are elsewhere or nowhere.

## Rejected

- **A text field with a bounded parser.** A compact notation for expressions is
  possible — a grammar that rejects everything outside itself and produces the
  typed model — but it is a parser to write, test and keep honest, and the
  structured editor already covers every example this feature exists for. It
  stays open. What is closed is a field whose contents reach a statement.
- **CREATE and roll back, to find out whether it would work.** That is D46's
  rehearsal, and it is the wrong tool for a preview that runs while somebody
  types. A plan is not a promise that execution will succeed, and does not
  pretend to be.
- **Composing the SQL in the browser and posting it.** What the old application
  did, and the reason half of this document exists.
- **A route of its own for creating the table.** Creation goes through the
  ordinary action, so access, refusals, cache invalidation and which branch of
  the catalog to re-read stay where every other change keeps them (D9).

## Visual reference

[Variant B](assets/2026-09-06-table-designer/variant-b.html) is the authority for
the editor's arrangement: 175-pixel navigation, an SQL pane beside the
inspector, object actions in the inspector, a combined primary/unique/check
section and a separate review step.

Its appearance is not adopted. The reference's palette, type scale and compact
bordered controls stay in the reference; the screen uses the kit and the theme
tokens like every other screen, and one visual pass covers the whole
application once its behaviour is finished.

The application keeps real source capabilities: expressions open the typed
editor from their field, foreign keys select a published target key, and owner
and tablespace fields are disabled until the creation API supports them. Demo
branding and a hard-coded PostgreSQL version are not application data. These
differences must not change the reference's layout or spacing.
