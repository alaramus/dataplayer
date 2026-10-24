# A SQLite file seen from a file source, and connected from it

Decision D262. A `.db` listed by a file source opened as text and was refused
as binary data. A database file is opened to see what it holds, so a file
source now shows it as one, and connects it as SQLite.

## What opening it shows

A file named `.db`, `.db3`, `.sqlite` or `.sqlite3` offers one representation,
`database`, titled "View the database". Its content is the relations of the
file — tables, views and virtual tables, with what ANALYZE counted — and the
engine and the file's size. SQLite's own tables and the ones a virtual table
keeps are left out, as the catalog marks them. At most a thousand relations are
listed; the answer says how many there are.

Rows are not read. They belong to a connection to the file, which has a grid,
paging, filters, edits and a console; a second, lesser grid inside the file
source would be a second SQLite source.

## How it is read

The file is opened the way every SQLite connection here opens one (D247): read
only, with the same authorizer and settings, under a five-second clock. It is
also opened immutable: a read-only connection to a file in WAL mode makes the
-shm and -wal files beside it and cannot remove them, so a glance at a listing
left two files in the person's folder. The price is that a listing read while
another program writes the file may be stale. A file
whose header is not SQLite's is refused with that reason, so a `.db` that is
something else says so rather than showing an empty list. A remote file is read
from its bounded local copy (D152).

The `sqlite3` driver stays inside the SQLite package. The package registers a
reader for database files in the content module as it is imported, and the
file source asks that registry by engine; it never imports the driver. Without
the reader the file source says it cannot read database files.

## Connecting it

**Connect as SQLite** is the file's counterpart of Connect folder (D150): the
source drafts a connector — type `sqlite`, the file's path below its owner's
home — and the window opens the new-connection form with it, nothing saved.
It needs ownership, like Connect folder, since the connection is made on the
owner's own file. The draft carries the SQLite options as plain values; the
file source names no SQLite model, because importing the package would import
its driver.

A SQLite connection opens a file of its owner's personal storage only (D247).
A database in a storage that is not one — an SSH server's folder, a bucket — is
still offered the action, drawn off with the reason ("Only a file in your
personal storage can be connected as SQLite"), through the same refusal a
source gives any action it knows but cannot do here. Copying the file into
personal storage first was considered and left to the person: a copy that
silently stops following the original is a different thing from a connection.

The same action is drawn as a button above the tables, so the place a person
reads the file is the place they connect it from.

Rejected: classifying the file by its header in the catalog. Listing a folder
does not open every file (D47), and the name is what a person gave the file.
