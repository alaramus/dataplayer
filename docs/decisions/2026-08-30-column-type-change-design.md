# Changing a column's type

## Problem

Of the column commands built so far, none touches the type. The old
application never had one either — its PostgreSQL templates cover rename, add
and drop and stop there — so there is nothing to port and nothing to learn from
except the shape of the problem.

The naive implementation is the one D2c exists to forbid. `ALTER TABLE … ALTER
COLUMN … TYPE …` takes a type, which is syntax rather than a bound value, and
it takes a `USING` expression, which is an arbitrary SQL expression. A form with
a "new type" box and a "USING" box would hand a client both halves of a
statement, and the second one is a general-purpose SQL channel wearing a
different name.

## The target comes from the vocabulary that already exists

D27 already made a source publish its type choices as opaque codes with titles,
and the add-column command already turns a code into a fixed
`psycopg.sql.SQL` fragment. A type change reuses that list unchanged: the
request carries a code, and an unknown code is refused before a statement is
built. Nothing new is offered, so nothing new has to be argued about — length,
precision, arrays, enums and domains stay outside the boundary exactly as they
do for a new column.

## The conversion is written by the source, always

The statement is always `… TYPE <target> USING <column>::<target>`, with the
column through `Identifier` and the target from the registry. There is no
request field the cast is read from.

Writing `USING` rather than leaving it out is deliberate. Without it PostgreSQL
uses assignment casts only, and the commonest change a person actually wants —
a text column that should have been a number or a date — fails with advice to
supply the very expression this design refuses to accept. With it, the change
means what the user asked for: read each value as the new type.

The price is that explicit casts can lose information. `numeric` to `integer`
rounds and says nothing; `timestamp with time zone` to `date` drops the time.
That is stated once, on the screen, as a property of changing a type at all,
rather than computed per pair of types in two places.

## What stands in the way is found before the table is locked

Three things can stop a change, and they are different kinds of thing.

**There is no conversion between these two types at all.** `uuid` to `integer`
has no path. Rather than restate PostgreSQL's coercion rules in a table of our
own — which would be wrong the first time an extension adds a cast — the source
asks PostgreSQL: `SELECT <column>::<target> FROM <relation> WHERE false`. No
row is read and no lock is taken; if there is no pathway the parser says so, and
the answer is a refusal naming both types.

**Some rows hold a value the target cannot read.** Where the conversion is
PostgreSQL's own input function — that is, where the column is a string type,
which is exactly the case people reach for this command in — `pg_input_is_valid`
answers per row without raising, so the source counts the rows that would fail
and answers with the number, bounded and reported the way D37 bounds and reports
its own count. Where the conversion is a real cast function there is no
non-throwing way to try it, so no count is offered and the failure is named by
kind instead.

**Something else depends on the column.** A default that cannot be cast, a view
or rule built on the column, a value out of range or too long. These surface
only from the attempt, so the driver's refusal is reduced to a sentence by its
SQLSTATE — `42804` becomes "remove the column's default first", `0A000` becomes
"a view or rule uses this column" — and never by its text, which quotes the
data and the schema.

Indexes are not in that list on purpose: PostgreSQL rebuilds them itself as part
of the change, and check constraints are revalidated. Nothing is dropped as a
side effect, which is the same rule D27 set for `DROP COLUMN` without `CASCADE`:
an outside dependency stops the operation instead of disappearing under it.

## Two answers and a refusal

`ColumnTypeChanged` and `ColumnTypeBlocked` are one discriminated union, as in
D37, and everything above that is a fact about the request rather than about the
data is a 422 — an unknown column, an unknown code, a generated or identity
column, a column that already has that type, and each of the named refusals.

`ColumnTypeBlocked` is kept separate from `NullabilityBlocked` rather than
merged into one "the data is in the way" model. They count different things and
lead to different next moves: one names rows that hold nothing, the other names
rows that hold something the target cannot read. A single model carrying both
would have to explain which it meant in a sentence, and reading a fact out of a
sentence is what D37 refused.

## On screen

The type is printed in the structure table, so — by the rule D37 introduced —
that cell is the control. The dialog offers the source's own list, states that
every value is rewritten and that information can be lost, and puts that on one
explicit button rather than behind a second confirmation on top of a dialog that
already says it. A blocked answer keeps the dialog open with the count, as a
warning: nothing failed and nothing changed.

## Deliberate boundary

- No `USING` from a client, in any spelling, ever.
- No parameterised targets — no `varchar(n)`, `numeric(p,s)`, arrays or enums.
  Those need typed option parameters, which is a separate round.
- Nothing dependent is dropped to make the change possible. A default that
  blocks it is removed by the user, with the command they already have.
- One column at a time, and no combination with a rename or a nullability
  change in the same statement.
