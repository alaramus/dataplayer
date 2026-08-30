# Pasting a block of cells

## Problem

The grid can copy a rectangular selection as TSV (D24) and can change one cell
at a time (D25). The obvious missing half — putting a block back — is how
anybody actually corrects twenty rows after looking at them in a spreadsheet.

It is not twenty single-cell updates. Half of them landing is worse than none
of them landing, because the reader cannot tell which half without comparing
against what they pasted. So it is one request, and it is all or nothing.

## The request names rows, not cells

D25 versions a row, not a cell: the handle carries the key and the row's `xmin`,
and that is what an optimistic update checks. A block of cells therefore
travels as rows — a handle and the cells being changed in it — rather than as a
flat list of cells with a handle repeated on each.

Every row must still hold the version it was fetched with. If any one of them
does not, nothing is written and the answer is the same conflict a single-cell
edit gives: the page moved under the reader, reload it.

The bound is on the whole request rather than on rows alone: 500 rows, 100
cells in a row, 2000 cells altogether. A paste is a correction someone made by
hand, and the ceiling is there for the same reason every other ceiling in this
project is.

## What the data can refuse arrives from outside this time

D37 through D40 all ask the same question before acting — how much of what is
already in the source contradicts what is being asked for. This one is the
mirror: the rows are fine, and it is the arriving values that may not be
readable as the column's type.

The answer is the same shape all the same. Before anything is written, every
value is checked against its column's type with `pg_input_is_valid` — the
function D38 uses for the same purpose — in one query, and the cells that
cannot be read come back named: which row of the request, which column.
Nothing is written when any cell is rejected, because a partly-applied paste is
the thing this whole design exists to avoid.

Naming the cells rather than counting them is the difference from D37–D40.
There the reader is being told the size of a problem in data they have not
looked at; here they are being told which of the values in front of them is
wrong, and there are at most two thousand of them.

The check is exact wherever the input function reports softly, which is every
core type. A type whose input function still raises would take the query down
with it, so the query carries the same SQLSTATE mapping the rest of this area
uses and the answer degrades to one honest sentence instead of a 502.

## Atomicity is a transaction, not a trick

D26 got all-or-nothing out of a single statement with a CTE, because the
session could only run one statement at a time. That does not stretch to
setting different values in different rows without composing per-column casts
into the statement, so the session gains what it was working around: a
transaction that runs several statements on one connection and rolls back if
any of them does not do what it said.

Each row is one `UPDATE … WHERE key = … AND xmin = …`. A row that matches
nothing is a conflict, and the transaction ends without a commit.

## What lands where

The block lands from the top-left cell of the selection and extends right and
down. It is refused before it is sent if it would run past the last loaded row
or the last visible column, or across a column the source says is not editable
— nothing is silently truncated, and no row is invented to hold the overflow.

A selection larger than the block changes only the block's cells. Filling a
selection by repeating a smaller block is a spreadsheet habit, not an obvious
one, and it is left out.

## Copy becomes lossless on the way

The TSV the grid writes today spells both an empty string and a null as an
empty field, so a copy followed by a paste would turn every empty string into a
null. An unquoted empty field now means null and a quoted one means the empty
string, in both directions. That makes the grid's own round trip exact, which
is the least a paste can be expected to do.

## Deliberate boundary

- No new rows. A block taller than what is loaded is refused, not appended;
  inserting is its own command (D26) with its own defaults.
- No fill, no formulas, no transpose, no paste into the header.
- No file. Importing a CSV is the next bullet of this phase and needs mapping,
  preview and an error report of its own.
- The single-cell editor keeps its own route. It now shares the type check, so
  its refusal names the type instead of saying the source rejected something,
  but merging the two paths is a tidy-up rather than part of this.
