# Copying a database out, and putting it back

## Goal

The last item of phase 4: backup and restore, once the job model holds. The
roadmap states the difficulty in its own words — `pg_dump` and `pg_restore`
are programs, not statements; this application's container has neither; their
version must match the server; and a restore is destructive in a way nothing
else here is.

## Where the programs come from

Three ways were available, and two are worse.

**Install the client tools in the backend image.** Then the version is
whatever was installed, and a `pg_dump` older than the server it is pointed at
refuses to run — correctly, because it cannot know the newer format. An
application that can back up a PostgreSQL 17 and not an 18 is one that will
quietly stop working the year after it ships.

**Write a dumper.** Read the schema, order the tables, quote the values, get
sequences, extensions, partitions, generated columns and identity right. This
is the old application's `include_test_data` road, and the result is never a
`pg_dump`.

**Run the real program in a container of the right version.** The phase built
a container runtime for services; a program run once for its exit code is the
same runtime with less to keep. The source is asked its own version —
`SHOW server_version_num` — and the answer picks the image: `postgres:18`
dumps an 18. Nothing is installed, and nothing has to match anything.

So the engine gained one verb, `run_once`: create, start, wait, read the
output, remove — with the removal in a `finally`, because a container kept for
its exit code is one nobody will look at again.

## Where a backup goes

Into the owner's personal storage, as a file. Not a table, not a new store:
personal storage is already browsed, downloaded, renamed and deleted through
the file source, and a backup that needed a place of its own would be a second
file system with a worse browser.

The program writes it directly. The storage is a named volume, so the tool
container mounts that volume at the same path this application uses and writes
to `<user id>/backups/<name>.dump` — which is exactly where the file source
will list it. No copying out of a container, no streaming through the
application, and no path on the host anywhere.

A deployment that keeps storage somewhere else has not said which volume, so
`SERVICE_STORAGE_VOLUME` is empty and backups are not offered: a dump written
inside a container that is then thrown away is worse than a refusal.

## Who says what runs

The source. `SupportsBackup` is a capability with two methods, and each
answers with a `BackupProgram` — an image, an argv and an environment. It is
the same shape as a service template and for the same reason: what runs is
code, not a request.

PostgreSQL's answers are `pg_dump --format=custom --no-owner --no-privileges`
and `pg_restore --clean --if-exists --no-owner --no-privileges`. The owner and
privilege flags matter: the owner of a database backed up here is a role of
*that* server, and a restore elsewhere would fail on a role that does not
exist.

The password is in the environment as `PGPASSWORD`, never in the arguments:
arguments are visible to anything on the machine that can list processes, and
this is what libpq documents the variable for. There is a test that the
password appears in neither the argv nor the `repr` of the run.

## Two jobs, and one of them is destructive

Both are jobs of the model D81 built — a row, named steps, the socket, the
same authority — because a dump of anything real is minutes.

A restore is different in kind: `--clean` drops every object in the dump from
the target before writing it. So the request carries `understood`, and one
without it is refused with a sentence rather than obeyed. The handler does not
check again: a job carries out what was decided, and deciding twice is how one
of the two decisions comes to be wrong.

Which backup to write back travels in the job's own `parameters`, a small
JSONB column the job model gained for exactly this — a kind of work that needs
more than a subject. It is documented as never holding a secret: a job row is
not encrypted, and what a job needs to keep secret it reads from the connector
it is about.

The file is named rather than uploaded, and the name is matched against the
files in one folder. Nothing resolves a path a client wrote — the containment
rule D8 states for a file source, kept here by having no path to contain.

Backing up is the owner's, not a grant's: copying a database out whole is
every row, every schema and every function in one file the caller keeps, which
is more than reading it.

## How it was verified

Twelve tests through the routes with a fake engine, including that the program
is given its password apart from its arguments, that a failed program's own
last line becomes the job's message, that a restore without `understood` runs
nothing, and that a name which is not one of the caller's backups is not
found.

Then the real thing, twice. Through the API: a PostgreSQL service started, a
table seeded through the console, a backup taken (`pg_dump` in `postgres:18`,
1319 bytes into the owner's storage), a row added afterwards, the backup
restored — and the table then held exactly what it held at the moment of the
dump. And through the browser: the Backups command in the bar at the foot of
the screen, the dialog listing the file with its size and time, and a 94 KB
dump of the application's own database taken with one press.

## Decision

**D87. A program that is not a statement runs in a container of its own.** The
statement, its consequences and the known deviations are in
[managed services](../architecture/services.md).

## What the screen offers it for

The offer was about the machine only, at first — a container runtime and a
volume to write into — so the button was live on every connection, and a file
source or a Redis server would have started a job that failed on the sentence
"this kind of connection cannot be backed up". The job was right and the
button was a lie.

Whether a source can be copied out is a capability, and capabilities in this
application are read off the driver rather than listed: `SupportsBackup` now
puts "Copy the whole database out" on the type's own card, the bar greys the
button out where the type does not declare it, and the two routes answer 501
before a job exists. One list decides the refusal, the tooltip and what the
catalog says a type can do.

Deleting a backup went in at the same time, because a folder that only fills
up is a folder people stop using. It is a file, so it is an `unlink` and not a
job, and the name goes through the same match a restore uses.

## What is not here

A schedule, a retention rule, a backup of anything but PostgreSQL, and a
restore into a connection other than the one the dump came from. The last is
possible — the dump has no owner and no privileges in it — and it is refused
only by the screen, which offers the backups of the connection being looked
at.
