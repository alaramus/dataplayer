# Tables copied with their structure

Date: 2026-09-27. Decision: D182. Extends D164 and D168.

## The problem

A PostgreSQL table pasted into another connection became a bare table: "Create
a table" (D166) makes plain columns from at most 5000 rows, with no key, index,
default or check, and no link to anything. Within one connection a table had no
Paste at all. What people mean by copying a table is the table: its shape, its
rows, and — when it points at other tables — a decision about those links.

The old application copied a table by walking its foreign keys and silently
copying every table it pointed at, dumping each to CSV and translating the
`CREATE TABLE` text into another dialect with sqlglot and a patch per database.
A table that failed was skipped and a key that failed was lost, both silently.
The order it used — tables first, keys last — is kept; the silence and the
translation of SQL text are not.

## D182. A table is copied with its structure, and its links are a choice

A kind of D164, `tables_copy`, "Copy tables": from tables of a source that
describes them for copying into a schema of a source that can make them, in
the same connection or another one. Both ends implement
`SupportsTableCopy`, and they must speak the same dialect, which the source
names; PostgreSQL is the only one today. It is a transfer job (D168): planned
in the request, carried out in the background, stopped at once.

**What is copied.** Columns with their exact types, required values, defaults,
identity and serial columns, stored generated columns, collations and comments;
the primary key, unique, check and exclusion constraints; the other indexes; the
table's comment and whether it is unlogged; the enum, domain and composite
types the columns use, directly or through one another.
The source describes each part in its own words, read with nothing but
`pg_catalog` on the search path so that every name outside it arrives
qualified.

**What is not.** Triggers, row security and its policies, rules, inheritance
from another table, owner and access rights. The window names what is left
behind, per table, before anything runs. Partitioned tables, partitions and
anything that is not an ordinary table are refused with the reason.

**The window asks five things.**

- The schema the tables go into. It is chosen in the window, whatever the
  catalog had selected when Paste was pressed — one schema, several or none —
  and starts where the catalog stood when that was one, then at `public`, then
  at the first.
- The name of each new table. The source's name to start with, and
  `name_copy` where that is taken — always so within the same schema.
- Structure and rows, or structure only.
- Links to tables that were not selected, as one choice for all of them: copy
  those tables too (and theirs, to the end of the chain), drop the links, or
  keep them pointing at the originals. The last exists only within one
  connection, where the originals are in the same database.
- Tables that point at the selected ones, each with a tick, off to begin with.
  A ticked one joins the copy, and its own links follow the choice above.

The window also shows every statement the copy will run, and each problem next
to what it is about. Every change of a choice plans again; nothing runs.

**The copy is one transaction at the destination.** The types and tables are
created, the rows arrive through `COPY`, and then the keys, the indexes, the
links and the sequences follow, so an index is built once over the rows rather
than row by row, and the order of the tables does not matter. The rows of every
table are read in one repeatable-read snapshot of the source, so a child and
its parent agree. Anything failing, a Stop included, rolls everything back: the
destination is left exactly as it was.

**Types in another database.** A type is made again under its own schema when
that schema is there, and in the place otherwise; then every text naming it — a
column's type, a default, a check, an index — is made to name the new one, and
only outside quoted values. A type an extension brings — `citext` — installs the
extension where the server offers it, in the same schema by the same rule. A
range, a base type or a table's row type must already be there.

**Names.** A constraint or index keeps its name when it is free, with the
table's name in it replaced by the new one; one that is still taken gets a
number. A serial column gets a new sequence of its own. An identity or serial
column is set to continue after its largest copied value.

**Every fragment is checked before it is composed.** A default, a check or an
index body is text from the source's catalog, never from the client — and a
server can lie about its catalog. So each one must be a single expression: no
statement separator or comment outside quotes, every quote closed, every
parenthesis matched. One that is not is left behind and said to be.

**Nothing reaches the destination that the destination did not plan.** The
choices travel in the request and in the job; the statements never do. The job
describes the source and plans the destination again when it starts, so a name
taken in between is a refusal rather than a collision.

**Same connection.** A source with no Paste of its own (D74) is offered the
platform's kinds within its own connection too, which is how a table gets
Paste next to itself. "Create a table" and "Add rows to a table" appear there
as well.

**Paste opens it at once.** A kind names the kinds it stands in for wherever
it can run, and the menu's Paste is left with the one that fits what was
copied: a table from a database opens this window, a file or a key opens Create
a table. Adding rows into a ticked table goes somewhere else — into that table
rather than into the place — so it is a line of its own, Add rows to a table,
off until one table is ticked. A list of offers is left for a clipboard two
kinds fit equally, which no pair of connections has today.

**Not in pipelines.** A link stores a name and columns; a copy of several
tables with a choice about each link is not something a link can hold, so this
kind is offered only from the catalog.

## Known deviations

- **A range, base or row type must already be there.** The destination refuses
  the copy when it lacks one, naming it.
- **A default taking values from a sequence the column does not own** is kept
  within one connection, where the sequence is shared, and dropped with a
  warning elsewhere.
- **Other dialects are not translated.** The kind requires both ends to speak
  the same one. A second dialect would add a translation from the source's
  described parts, never from SQL text.

## What was considered

- **Reading the table back into D117's closed definition.** It would have
  given a neutral description, but checks, defaults and index expressions are
  arbitrary expressions, and reading them into the closed model means parsing
  SQL; what does not fit would be lost. Within one dialect the source's own
  words are exact.
- **`CREATE TABLE … (LIKE … INCLUDING ALL)`.** Works only inside one database
  and still leaves the foreign keys out.
- **`pg_dump` in a container (D87).** Exact, but a container per copy, and no
  way to rename a table or choose what happens to its links.
