# A SQLite database made here

Decision D263. Every other database type offers "Start it here": a container
this server starts and a connection it saves (D80). A SQLite source starts
nothing — it opens a file — so its counterpart makes a file.

## What it does

The type panel of the new-connection catalog offers **Create SQLite here**
beside the guide, where a server type offers to start one. Its window asks
"How" with the two answers a service's does (D88):

- **Set it up for me** asks nothing more. The server makes
  `databases/dataplayer.db` filled with the lab of D261 and names the connection
  after the file.
- **Let me choose** asks for the connection's name, the folder, whether to fill
  it with the lab, and whether to use SQLite's write-ahead log. Whatever is left
  empty is still the server's to decide.

Creating makes the file and saves the connection in one request, then opens
the new connection's catalog and says where the file went.

- **Where.** A folder of the person's own storage, `databases` unless chosen,
  made level by level where it is missing. The file name is the connection's
  name with everything a path could misread replaced, or `dataplayer`; a name
  already taken is numbered (`dataplayer-2.db`), never overwritten — an
  existing file is somebody's data. Every place goes through the storage's
  containment rule (D8), so neither a name nor a folder walks out of the
  storage.
- **WAL.** Set on the new file when asked for: reading then does not wait for
  writing, and the file has `-wal` and `-shm` beside it while it is open. Off
  by default, because those two files surprise somebody who copies the
  database by hand.
- **Empty or the lab.** Empty is a real SQLite file with its header, written by
  SQLite itself: a zero-byte file is a database to SQLite and not one to the
  file viewer of D262, which reads the header.
- **No job.** Nothing is pulled and nothing waited for, so the request does it
  at once; a service's job (D81) would be a progress bar for nothing.
- **No managed service.** The file is not listed among the services this server
  runs: there is nothing to stop, restart or read logs of. It is a file in
  **Files**, renamed, downloaded and deleted there.
- **Taken back on failure.** If the connection cannot be saved, the file is
  removed again: a file no connection holds is a file nobody asked for.

## How it is shaped

A capability on the driver, like the rest: `MakesSourceHere`, two classmethods
— make, and take back — since there is no connection to ask yet. The adapter
types list says `makes_here` for a type that has it, read off the class, and the
panel draws the button only there. The route lives with connections
(`POST /connectors/made-here`) and saves the connection the way the form does;
a type without the capability answers 501.

The SQLite package does the making, so the `sqlite3` driver stays inside it;
the route reaches it through the registry, as it reaches every driver.

Rejected: running it through the service machinery with a "fileless" kind. The
services screen, its lifecycle and its states are about containers, and every
one of them would have needed a branch for a file.
