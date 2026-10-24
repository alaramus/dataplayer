# A SQLite file seen from a file source

Decision D262. A `.db` listed by a file source opened as text and was refused
as binary data. A database file is opened to see what it holds, so a file
source now shows it as one.

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
only, with the same authorizer and settings, under a five-second clock. A file
whose header is not SQLite's is refused with that reason, so a `.db` that is
something else says so rather than showing an empty list. A remote file is read
from its bounded local copy (D152).

The `sqlite3` driver stays inside the SQLite package. The package registers a
reader for database files in the content module as it is imported, and the
file source asks that registry by engine; it never imports the driver. Without
the reader the file source says it cannot read database files.

Rejected: classifying the file by its header in the catalog. Listing a folder
does not open every file (D47), and the name is what a person gave the file.
