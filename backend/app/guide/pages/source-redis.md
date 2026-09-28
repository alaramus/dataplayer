# Redis

An in-memory key-value server. You walk its keys as a tree of the colons in
their names, read what a key holds as rows, write keys of every type, and set
or clear their expiry. How connections work in general is on the
[Connections](connections.md) page.

## What you can see

- Every database on the server, and its keys as a tree
- What a key holds, as rows: fields, list items, members, scores, entries
- A key's type, size and time left to live
- A folder of hashes as one table
- Server metrics on dashboards

## What you can change

- The values inside a key, one at a time
- Keys of all six types: create, replace, delete
- A key's expiry: set it or remove it
- Tables described over folders of hashes
- Keys and tables saved as CSV files

## Connecting

The **Connection** page of the window asks for:

- **Host** and **Port**, 6379 unless the server says otherwise;
- **Database**: the one the catalog opens on. Every database stays reachable
  from the catalog;
- **Authentication**: a password, or none.

A connection string such as `redis://:secret@cache.example.com:6379/0` pasted
into **URL** fills these fields. A `rediss://` address, which needs TLS, is not
supported yet.

## The catalog

The catalog is a tree.

- The control at the top chooses the database. It says how many keys each one
  holds. The choice is remembered in this browser.
- Keys are grouped by the colons in their names: `session:42:token` is under
  `session`, then `42`. Pressing a folder opens it where it stands.
- A key says its type, its size and how long it has left, if it expires.
- Pressing a key opens it in a tab. Pressing a row selects it, and the actions
  menu then acts on it.
- A very large key space is listed as far as a ceiling. A narrower folder shows
  what is beyond it.

## Reading a key

A key opens as rows. The shape follows its type:

- a **string** is one value;
- a **hash** is fields and values;
- a **list** is positions and values;
- a **set** is members;
- a **sorted set** is members and scores;
- a **stream** is entries.

Rows are paged like any table in the grid. Redis has no index over values, so
nothing can be sorted or filtered. **Download** can save every row as a CSV
file.

## Editing a key

With **Edit rows** access, the values of a key are edited in its grid:

- double-click a cell to change a hash field, a list item, a string or a score;
- **Insert row** adds a field, an item, a member;
- tick rows and **Delete selected rows** removes fields and members.

What each type allows is shown by the grid itself. An item cannot be removed
from the middle of a list, and a stream cannot be edited at all.

If somebody changed the value after you read it, your change is refused rather
than written over theirs. Reload and try again.

## Writing keys

Select a folder or a key in the tree and open the actions menu:

- **New string**, **New hash**, **New list**, **New set**, **New sorted set**,
  **New stream**. The name you type is added to the folder you are standing in,
  so `one` written in `cache:` becomes `cache:one`. A collection is written one
  member, or one `name=value`, per line. An expiry can be set at once. A name
  already in use is refused unless you choose to replace it;
- **Delete** removes a key, after asking;
- **Set expiry** gives a key a time to live, and **Remove expiry** takes it off.

## A folder as a table

Many applications keep records as hashes in one folder: `user:1`, `user:2`, each
with the same fields. **Describe as table**, in the actions menu of such a
folder, turns it into a table.

- It proposes the fields found in the first hundred hashes, with a type guessed
  for each. Tick the ones that become columns.
- The table stands in the tree right after its folder. Opened, it has one row per
  hash: `key`, the name within the folder, then the fields you chose.
- Its rows are edited like any table: a cell is one field of one hash, and
  clearing a cell removes that field.
- It is kept with the connection, so everybody who reads the connection sees it.
  Removing it forgets the description and touches no key.
- Its `key` column can be one end of a reference you draw to another
  connection's table, so a row leads to the matching rows there.

Describing, changing and removing a table needs **Change structure** access.

## Copying out

**Copy** a key, a folder or a table in the catalog and **Paste** it into a folder
of a file or SSH connection: each becomes a CSV file. Several ticked are copied
together, one file each.

## Metrics

A Redis connection can report its own counters to dashboards: memory, clients,
commands, hits and misses, expired and evicted keys, network traffic and keys
per database. The owner switches this on in the
**Sources** window of the **Dashboards** space, and chooses how often. The
ready-made layout for it is called **Redis server**.

## What Redis does not have here

- There is no command console: Redis takes commands rather than statements, and
  a console for them would be a shell on the server.
- A key that expires while its tab is open stays on screen until the tab is
  read again.
- Values are shown as text. A key that holds a picture shows as unreadable
  characters.
