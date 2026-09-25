# Tables declared over Redis, and Redis saved as CSV

Date: 2026-09-25. Decisions: D170, D171. Builds on D44 (an export is a
source-owned row stream), D106–D108 (declared references), D164, D165 (a
table pasted into a folder becomes a CSV file), D166 and D168 (transfers as
owned jobs).

## The problem

Redis has no structure. Data that is plainly a table — `user:1`, `user:2`,
`user:3`, each a hash with `name` and `email` — is shown as a folder of
unrelated keys, each opened on its own as `field, value`. Nothing can say
"these are the users, and these are their columns", so nothing can treat them
as one table: not a grid, not a CSV, and not a reference from `users.id` in a
database to the Redis user with that id, which is the next step.

There is a second, smaller gap. Copy has been on a Redis key since D166, whose
row kinds take any source that reads rows, so a key already pastes into a
database. Pasted into a folder, nothing happens: D165's "Save as CSV" takes a
relation from a source with a relation model and a D44 export, and only
PostgreSQL has both.

## D170. A folder of Redis hashes can be declared a table

A person can say of a Redis folder: its keys are hashes, and these fields are
the columns. The folder then has a table beside it, as the structure Redis
does not have.

### Declaring one

- **"Describe as table"** is a command on a Redis folder. Its window proposes
  a name — the folder's — and lists the fields found in the first hundred
  hashes of the folder, each with a tick and a type: text, number, boolean,
  date and time. A field can be added by hand for keys the sample did not
  reach. The order of the list is the order of the columns.
- **Changing or removing** it is the same command on the table: the window
  again, and "Remove table". Removing forgets the description; no key is
  touched.
- **It belongs to the connection**, kept with its stored options rather than
  in Redis: everybody who can read the connection sees the table. Declaring,
  changing or removing one needs `structure` on the connection, the level that
  changes a table's structure elsewhere.
- One table per folder. A folder's keys belong to one database, and so does
  its table.

### What it looks like

- **In the catalog**, the table stands beside the folder it reads, with a
  table's icon and its declared name. The folder stays as it was: walking into
  it lists its keys, which remain keys of their own.
- **Opened, it is a grid**: one row per hash directly in the folder — not in
  folders below it — in key order; a first column `key`, the key's name
  within the folder (`1` for `user:1`); then the declared fields. A field a
  hash lacks is an empty cell; a field it has and the table does not declare
  is not shown.
- **A key of another type** in the folder is not a row, and the grid says how
  many it left out.
- **Size.** The grid reads up to 100,000 keys, in name order; a folder with
  more shows those and says so. Names are short, which is why this is higher
  than the catalog's own ceiling of 5,000.
- **Read-only in this step.** No filter, no sort but the key's, no editing of
  cells. Equality lookup by a column comes with references, next.

### Structure for every Redis node

The same step gives Redis what a structure is read through, for all it
shows, not only for declared tables:

- **A relation model** (`SupportsRelationModel`): a declared table with its
  columns and types; a key as the grid shows it — a hash `field, value`, a list
  `index, value`, a set `member`, a sorted set `member, score`, a stream `id,
  fields`, a string `value`; a folder as its list of keys, `key, type, ttl,
  size`. The structure view shows it as it shows a table's.
- **A path to every node** (`SupportsNodePath`): database, folders, key or
  table — how a node is named anywhere that names one, and what references
  will need.

## D171. A Redis key, folder or table is saved as CSV

- **Copy, then Paste in a folder** of a file connection or from a pair's bar:
  "Save as CSV" offers a name from the relation model — `session:42:token`
  becomes `session_42_token.csv`, because a colon is not a file name on every
  system — and runs as D168's transfer.
- **What is written is the grid's**: a key with its type's columns, a string
  whole rather than cut where the viewer cuts it; a folder as its list of keys;
  a declared table as `key` and its fields.
- **Redis implements D44's export**, in bounded batches with the command each
  type has for it: `HSCAN` and `SSCAN` for a hash and a set, index ranges for
  a list and a sorted set, `XRANGE` from the last id for a stream, and for a
  table `SCAN` over the folder with the declared fields read for each batch of
  keys. Nothing reads a key whole except a string, which is one value.
- **Order is the source's.** A list, a sorted set and a stream keep theirs; a
  hash, a set and a table are written as Redis scans them. The grid sorts for
  the eye; sorting a million fields would mean holding them all.
- **A folder beyond the catalog's 5,000 keys is refused** as a CSV, "This
  folder holds more keys than can be listed", rather than saved short. A table
  has no such ceiling in a CSV: it is scanned, not listed.
- **Several ticked at once** are one transfer and one file each, named after
  each. The name window is for one; several go straight to Save, and a taken
  name opens the conflict window once, for all of them. This holds for
  PostgreSQL tables as well, which D165 took one at a time. One failing does
  not stop the next; the 10 GB ceiling is for all of them together. An offer's
  workflow is narrowed by the selection as its `can_replace` is (D169).
- **The grid's "export all rows" follows**: it is D44's capability, so a Redis
  key, folder or table gains the whole download PostgreSQL has had.

## Out of scope

- References from or to a Redis table: next, with equality lookup by a column.
- Editing a declared table's cells, adding or removing its rows.
- Tables over keys of other types, or over keys in more than one folder.
- A key of a type no reader knows — a module's own — refused as in the grid.

## Known deviations, accepted with them

- **A hash, a set or a table changing while it is saved** may give an element
  twice or miss one: that is what `SCAN` promises, and the alternative is
  reading it whole.
- **A string is read whole.** It is one cell, and a cell is written whole;
  Redis holds up to 512 MB in one.
- **A table past 100,000 keys** is shown in part in the grid, with a notice.

## Acceptance

- "Describe as table" on a folder of hashes proposes the fields of its first
  hundred; saved, a table stands beside the folder and opens as a grid of one
  row per hash, `key` first, missing fields empty, other types counted out.
- Only a person with `structure` on the connection declares, changes or
  removes one; everybody who reads the connection sees it; removing it leaves
  every key.
- A key, a folder and a table each have a relation model and a path.
- Each key type, a folder and a table save as CSV with the grid's columns and
  every row; a folder past 5,000 keys is refused.
- Several keys, or several PostgreSQL tables, save as one file each in one
  transfer; a taken name asks once.
- A hash of more rows than a batch is read in several batches, never whole.

Tests cover the declaration and who may make it, the table's rows, the model
and the path of each node, each type's export and its batches, the ceilings,
and several items with one failing on the server; the declaration window and
the name window skipped for several as plain functions; a table declared and a
key saved through Paste in the browser.
