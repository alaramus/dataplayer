# Changing whether a column may be empty

## Problem

A relation says which of its columns accept a row with no value — D22 put
`nullable` in the column model, and the structure tab prints it — and nothing
can be done with it. Of the four column changes built so far (add, drop,
rename, default), none reaches the constraint that decides whether the data is
complete.

Nullability is not another spelling of add-and-drop. Recreating a column to
change it would throw the data away, so it is its own command, the way rename
is its own command for the same reason (D29).

The hard part is not the DDL. `ALTER TABLE … ALTER COLUMN … SET NOT NULL` is
one line. The hard part is what the source does when rows already contradict
the constraint being asked for.

## Three things the source could do about the rows in the way

**Refuse and say nothing.** PostgreSQL scans the table, finds a row with no
value and raises. The driver's message names the row, so it cannot be passed on
(the message would carry source data, and adapter errors are reduced to a kind
and a safe sentence). What is left is "the source rejected the schema change" —
true, useless, and indistinguishable from the twelve other reasons a schema
change is rejected.

**Fill the empty rows.** Rejected. It hides a change to every row of a table
inside a gesture that says it changes the shape. It also needs a value, and a
value entered by a user is a literal (D30), so this would be two commands with
two confirmations wearing one button. It stays out of the round, like relation
creation stays out of the column round.

**Count them and answer with the number.** Chosen. Before anything is locked or
altered, the source asks the table how many rows have no value in that column
and answers with the count. The user is then told the size of the problem —
four rows, or more than a thousand — and can act on the data, which is where
the problem is.

## The count is an answer, not an error

`change_column_nullability` returns one of two shapes:

- `NullabilityChanged` — the column now says what was asked, and repeats what
  that is.
- `NullabilityBlocked` — nothing was changed, and here is the number of rows
  that stand in the way.

A discriminated union rather than a 4xx with the number in the sentence. This
is D2d again, and it is the same shape `follow_reference` already answers with:
a row whose key is empty is not a failed request, and neither is a table whose
rows do not yet satisfy a constraint nobody has applied. The number has to
survive as a number — a screen that has to read "4" out of a message is a screen
parsing prose.

A request that is wrong about the relation rather than about the data stays an
error: an unknown column, a relation that cannot change columns at all, and a
column that already says what is being asked of it are all 422. Asking for a
change is a statement that something differs; if nothing does, the caller and
the source disagree about what is on screen.

## The count is bounded, and it is not a guarantee

`SELECT count(*)` over a whole table has no ceiling, and this project does not
run unbounded reads (paging has one; so does this). The count therefore stops
at a thousand and says whether it stopped: the answer carries `exact`, and a
screen reading it says "more than 1000" instead of a number that is not one.
A thousand is far past the point where the user's next move changes; what
matters then is that it is a lot.

The count is not what makes the operation correct. It runs before the ALTER and
outside its lock, so a row could gain a null in between. PostgreSQL's own
verification scan under `ACCESS EXCLUSIVE` remains the authority — if that races
and fails, the answer is the ordinary rejection. The count exists to give a
useful answer in the case that actually happens, not to replace the source's
check.

Counting first costs a scan the successful path did not previously pay for. That
is the price of not taking an exclusive lock on a table in order to fail on it,
and of not asking the user to guess how much data is in the way.

## Two directions, two different checks

Requiring a value is about the rows: they are counted first.

Allowing no value is about the shape, and the shape is already on the table.
A column in the primary key and an identity column both always have a value,
and PostgreSQL refuses to drop the constraint from either. The source reads
that from the relation model it has already fetched and says which it is —
"is part of primary key customers_pkey" rather than "rejected". Everything
else, including a partitioned parent whose partition still requires the value,
is left to PostgreSQL and comes back as the ordinary safe rejection.

The relation-level rule is unchanged from D27: a view is not a table and a
child partition points at its parent, both through `column_changes_supported`
and its reason, which a caller without a structure grant also receives (D33).

## On screen: the fact is the control

The structure table already prints the answer in a column headed "Null". That
cell becomes the button. A fourth icon in a row that already holds three would
have to name, in a tooltip, which of a column's several facts it changes; the
cell saying "yes" names it by standing where it stands.

The dialog states the current fact as a sentence, offers the one change that is
available, and stays open when the answer is `blocked` so the count can be read
in it. The count is rendered as a warning rather than an error: nothing failed.

After a `changed` answer the relation model and every open row query of the
connector are invalidated, as with the other column commands — the column
model changed, and so did what an insert may omit. A `blocked` answer changes
nothing and invalidates nothing.

## Deliberate boundary

- No offer to fill the empty rows. That is a data change and belongs to a data
  round, with its own confirmation and its own literal-value rule.
- No `NOT VALID` / validate-later dance, and no way to skip the verification
  scan through a pre-existing `CHECK`. Both are real PostgreSQL techniques for
  large tables and both need a vocabulary for a two-step constraint, which this
  round does not have.
- Nullability of several columns at once is not offered. One column, one
  answer.
