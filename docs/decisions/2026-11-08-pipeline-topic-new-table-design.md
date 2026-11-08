# A topic read into a table its link makes, each message once

Decision D313. Follows D312: a link reading a topic on wrote only into a
table that was there already, so the first link out of a topic began by
making that table by hand. A pipeline already makes tables from rows (Create
a table, D166, D178); a topic should be able to do the same.

## A second link-only kind: Add new messages to a new table

`rows_since_last_new`, beside D312's `rows_since_last`, as Create a table
stands beside Add rows. Which one is offered depends on where the link is
drawn: to a table, the messages are added to it; to a schema or another
place, a new table is made there. Its window is Create a table's — a name,
the columns and their types, suggested from the topic's columns (partition
and offset numbers, timestamp a time, value JSON, a `value.<field>` by its
JSON type). In a pipeline a topic is offered these two and no other row kind
(D312).

**The table is made once and added to after.** Create a table makes its table
at every run, so its second run meets the name taken. Here the group's
position decides:

- **No position kept** (the first run, or Kafka forgot it): the table is
  made. A name already taken fails the step and says so. Right after making
  it the link keeps the group's position where reading starts, so a failure
  later in the run leaves a position and the next run adds to the table
  rather than meeting its own table as a taken name. A failure before that
  takes the table back, as Create a table does.
- **A position kept**: the table must be there, found by its name in the
  place; the messages are added to it. A table that is gone fails the step
  with "{name} is no longer in {place}; to read everything again, move the
  group's positions to the start". It is not made again: made again silently
  it would hold only what came after, under a name that claims all of it.

**What it makes is a row of its card (D178)**: the table, by the name chosen,
drawn in italics and joinable before the first run. It is published at every
run, made or found, so a link reading it runs after it every time.

## Each message once, where the destination can promise it

D312 delivers at least once: a block written and not yet kept is written
again by the next run. A table the link makes itself can say which rows are
the same: a message is its partition and offset.

- **When the new table's columns include the topic's partition and offset**,
  and the destination can both promise uniqueness (`SupportsConstraints`) and
  write while leaving out what a key already holds (a new capability,
  `SupportsSkippingInsert`), the table is made with a unique key over those
  two columns, and every block is written leaving out the rows the key
  already holds. A block written twice then arrives once. The step counts
  only what arrived.
- **Otherwise** — a destination without either, or partition or offset left
  out of the table — it is D312's at least once, and nothing says otherwise
  to the person beyond the guide.
- The window starts with every column of the topic, partition and offset
  among them, so the promise is what a person gets unless they take it away.
- **The kind for a table that was there already stays at least once.** Writing
  while leaving out what a key holds would, on somebody's own table with a key
  of its own, drop rows silently instead of failing.

`SupportsSkippingInsert.insert_rows_skipping` is `insert_rows` with the rows a
unique key holds left out, answering how many arrived:

- PostgreSQL: `INSERT … ON CONFLICT DO NOTHING`.
- MySQL and MariaDB: `INSERT … ON DUPLICATE KEY UPDATE` of the first column
  to itself, which changes nothing; not `INSERT IGNORE`, which also turns a
  value that does not fit into a warning.
- SQLite: `INSERT … ON CONFLICT DO NOTHING`.
- ClickHouse has no unique keys, MongoDB, Redis and Kafka are not tables of
  this kind: they stay at least once.

## Known deviations

- **A table found by its name is trusted to be the one the link made**: a
  table made by hand under that name after the first is added to.
- **ClickHouse and every source without a unique key stay at least once.**
- **New fields of the messages are not added as columns**: the table keeps
  the columns chosen; a field that disappears leaves its column empty.

## Where it lands

- `connectors/paste/since.py`: the second kind beside the first, sharing the
  reading; the registry's `LINK_ONLY`.
- `adapters/protocol.py`: `SupportsSkippingInsert`; PostgreSQL, MySQL and
  SQLite implement it.
- Documentation: D313 in `pipelines.md`, beside D312; the guide's topic
  section in every language.
- Tests: the first run makes the table with its key, the second adds only
  what is new, a block written twice arrives once, a taken name fails, a table
  gone fails with its sentence, a destination without the capability still
  works at least once; each SQL adapter's skipping insert counts what arrived.
