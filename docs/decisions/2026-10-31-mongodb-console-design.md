# The MongoDB console

Decision D286. The second slice of the MongoDB source (D283–D285): its
console. The SQL sources each have a query editor that runs statements and
shows results in the grid; MongoDB has no SQL, and its own language is
JavaScript run by `mongosh`.

## What the console is

Three answers were put to the user:

- a subset of the shell's syntax — `db.c.find({...}).sort().limit()`,
  `aggregate([...])`, `countDocuments`, the writes, `db.runCommand({...})` —
  parsed as Extended JSON into driver calls, with results in the grid;
- only `runCommand` documents, the same in less comfortable clothes;
- the real `mongosh` in a terminal (D148), its results on its own screen.

The user chose the third. It is the shell MongoDB's users already know, with
all of its language, its helpers and its completion, and nothing here has to
keep pace with it. What it gives up is results in the grid, which the catalog
already gives for a collection.

## Where it runs

`mongosh` is a Node program. Three places were weighed:

- the backend's image — rejected: it would fix a version of the shell into the
  application, add a Node runtime to the image, and start programs in the
  application's process tree, which no other part does;
- the database's own container, with `docker exec` — rejected: that container
  is somebody else's server, or not a container at all;
- a container of the vendor's image, run by the server, as a backup is (D87) —
  chosen. The engine and its limits (D86) are already there, and the shell is
  thrown away with the container.

The engine sits in `app.services`, above `app.terminals` in the layers, so the
socket cannot reach it. It names what it needs as a `ConsoleRunner` protocol
in `app.terminals`, the engine satisfies it, and the application hands its
engine in at start-up. The adapter only says what to run
(`SupportsConsoleProgram`), the way `SupportsBackup` does.

## Attaching

A console needs input as well as output, so `run_once` does not serve. The
Engine API attaches to a container through an HTTP request it upgrades to a
raw stream; httpx cannot give a connection it upgraded back to its caller, so
the request is written on a Unix socket of its own. The container is made
with a TTY, an open stdin that closes with the attach, and `AutoRemove`, and
attached before it is started, as the Docker CLI does, so the first prompt is
not lost. A program whose server went away reads the end of its input and
exits, and the daemon removes it.

## The password

D87's rule holds: a password is never an argument, since arguments are seen
by anything that lists the host's processes. `mongosh` has no variable it
reads a password from, so it starts with `--nodb` and runs, before its prompt,
a line that connects with an address taken from its environment and deletes
the variable. A wrong password ends the shell with the server's own
"Authentication failed" on the screen and the terminal's `ended` frame.
