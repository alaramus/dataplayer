# References to and from a Redis table, by its key

Date: 2026-09-26. Decision: D172. Builds on D106–D108 (declared references)
and D170 (tables declared over Redis folders).

## The problem

D170 gave a folder of Redis hashes a table: `user:1`, `user:2` read as rows
with `key` first. What it was for is the next question a person asks of such
data: which user is this order's, and which orders are this user's. A
declared reference answers it between any two sources, but D107 lets a
column be an end only when its source can look a value up in it, and no
Redis column can: the grid offers no filter on any of them.

## D172. A Redis table's `key` can be an end of a declared reference

### What can be an end

- **The `key` column of a declared table, and nothing else of Redis.** Looking
  a key up is reading one hash: `42` is `user:42`, one round trip whatever the
  folder holds. A declared field has no index in Redis; finding the rows where
  `user_id = 42` means reading every hash of the folder, and an arrow that
  reads a hundred thousand hashes on every click is the arrow D107 exists to
  refuse.
- So the table's `key` column says it admits equality, and its other columns
  still say nothing. The declaration window already lists only the columns an
  end can be drawn from, so a Redis table offers `key` alone, with no change
  to the window.
- A key read as rows (a hash's `field, value`, a list's positions) and a
  folder's listing are not ends; neither is a Redis table's other column.

### What looking one up does

- **A key filter reads one key.** `key = 42` on the table over `user:` asks
  for `user:42`'s type and declared fields in one pipeline: a hash directly in
  the folder is the one row, and anything else — no such key, a key of
  another type, `42:x`, which lies in a folder below — is no row. No scan, no
  ceiling and no notice about keys left out.
- **The value is the key's name within the folder, as text, exactly.** No
  trimming, no case folding and no reading of numbers: `042` is not `42`.
- **Only equality, only on `key`.** Any other filter, or a sort, is refused as
  now.

### What a person sees

- **Drawing one** is D106's window as it is: stand on the Redis table's
  structure, or on the other end's, pick the other node through the catalog —
  the Redis tree walks to a table like any other — and pair `key` with the
  column on the far side.
- **Following from the far side** — `orders.user_id = 42` in PostgreSQL — opens
  the Redis table filtered to `key = 42`: one row, or an empty grid when no
  such user is kept. The filter is an ordinary filter of the grid, and taking
  it off shows the whole table.
- **Following from Redis** — the arrow on a `key` cell — opens the far node
  filtered to that value, as any declared reference does.
- **The grid's own filter** gains the same: `key` equals a value, typed by the
  person, on a Redis table. The whole-table download with that filter saves the
  one row.

## Out of scope

- Ends on declared fields, found by reading the whole folder: refused above.
- Ends on keys read as rows, on folder listings, and on keys whose value is
  a list of ids.
- `in`, `starts with` and every other operator on `key`.
- A reference drawn by the source rather than the person: Redis has none.

## Known deviations, accepted with it

- **Text meets text exactly.** A PostgreSQL integer `42` finds `user:42`, but
  a Redis key `042`, or a float `42.0` on the other side, finds nothing: the
  two ends agree on how the value is written or the arrow comes back empty.
- **A key that changes type** between the lookup's two commands is no row
  rather than an error, the same as the page does (D170).

## Acceptance

- The declaration window offers `key` of a Redis table and none of its other
  columns; a reference between PostgreSQL `orders.user_id` and the Redis
  `users.key` is drawn and shows an arrow in both grids.
- Followed from `orders`, it opens `users` with the one row whose key is the
  value; followed from `users`, it opens `orders` with that user's orders.
- A value that names no hash, a key of another type or a key in a folder
  below opens an empty grid.
- A key lookup reads one key, never the folder; any other filter or a sort on
  a Redis table is refused.
- The grid's filter on `key` and the whole download with it return the one row.

Tests cover the lookup and what it refuses, the column that admits equality
and the ones that do not, the export with the filter, declaring an end on
`key` and being refused on another column through the API, and in the
browser a reference drawn between a PostgreSQL table and a Redis table and
followed both ways.
