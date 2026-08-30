# Bringing rows from one source into another

## Problem

A CSV sits in the user's personal storage, which already reads it as columns
and rows (D8), and a relation sits in a database, which already accepts an
inserted row (D26). What is missing is the sentence between them.

Calling it "CSV import" would be a mistake in the first line of the design. The
file source is one source among several, the target is one target among
several, and everything in between — a bounded read, a mapping of names, a
lossless text cell (D23), an all-or-nothing write — belongs to neither of them.
So this is not an import of a file. It is **moving a bounded set of rows from
any source that can be read into any source that can accept rows**, and a CSV
in personal storage is the first pair it is used on.

## The first thing that has never happened before

Every command so far addresses one connector. This one names two: the relation
being written and the node being read. That is the whole reason it lives in the
`connectors` module rather than in an adapter — an adapter knows itself and
nothing else, and asking one to read another would be the first crack in that.

Two connectors mean two permissions, checked separately: writing rows into the
target, reading the node in the source. Neither implies the other, and the
grants of D33 already answer both questions independently.

## Bounded, and it says so

The read has a ceiling of 5000 rows and pages the source at its own limit to
get there. A file with more is not refused — that would make the feature
useless for the case it exists for — but the answer says the rows were cut off
at the ceiling, so nobody is left believing a whole file arrived.

Anything larger is a job: durable state, progress, cancellation, a request that
returns before the work is done. That is Phase 4, and pretending otherwise by
raising the number would only move the point where the request times out.

## Columns are paired by name, both sides checked

The request carries pairs: a column of the source, a column of the target.
Both are validated against what each side says it has — the source's fetched
columns and the target's insertable ones — before anything is read. A source
column that is not there, a target column the source will not insert, and the
same target column twice are all refused.

The pairing is explicit rather than by position or by matching names, because
the two sides are written by different people at different times and a silent
match is a wrong import that looks right.

## Either every row arrives or none does

The target checks every value against its column's type before writing
anything — the same `pg_input_is_valid` pass D41 makes — and answers with the
cells that cannot be read: which row of the read, which column, and the value
itself, cut short. The value is echoed because it is the reader's own file
content, and because "row 12, column price" without it sends them hunting.

Then one transaction, and one statement run for every row, pipelined by the
driver. Not one statement with the whole list inside it: PostgreSQL resolves
the types of the parameters in a multi-row `VALUES` from that list, so a text
value stays text and assigning it to an integer column is refused, while a
single-row `VALUES` is resolved against the target's own columns — which is
the coercion every other write here relies on. A failure at any point leaves
the relation as it was.

That is also why there is no downloadable error report, which the plan asked
for: a report of what went wrong in a partial import only means something if
imports can be partial. This one cannot, so the same information is the answer
to the request, bounded like everything else.

## The preview shows the mapping, not the outcome

`preview` reads the first rows through the same mapping and hands them back as
a small page. Its job is to answer "have I paired these columns correctly",
which is the mistake that actually happens, and which nothing else can catch.

It deliberately does not validate against the target. The import itself does
that and writes nothing when it fails, so a second validating call would be the
same answer one step earlier, at the cost of a second contract that could drift
from the first.

## Deliberate boundary

- No transformation. A value goes across as the text the source gave (D23) or
  it does not go across. Trimming, date formats and decimal separators are a
  vocabulary of their own.
- No new relation. The target exists; creating one from a file's header became
  D45, and dropping one D46.
- No upsert, no key matching, no update of existing rows. Rows are inserted.
- No streaming and no job. The ceiling is the honest form of that limit.
