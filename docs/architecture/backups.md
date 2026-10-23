# Backing up a database and restoring it

Copying a source out whole, into the owner's own storage, and putting it back.
The services these jobs borrow a container runtime from are in
[services.md](services.md); the jobs themselves are in [jobs.md](jobs.md).

Decisions here: D87.

```
backend/app/services/
├── tools.py          a container run once for its exit code
├── backups.py        copying a database out and putting it back, as jobs
└── backup_routes.py  the backups of one person, and the two commands
```

```
GET    /api/v1/backups/
GET    /api/v1/backups/offer
POST   /api/v1/backups/
POST   /api/v1/backups/restore
DELETE /api/v1/backups/{filename}
```

## D87. A program that is not a statement runs in a container of its own

`pg_dump` and `pg_restore` are programs. This application's image has neither,
and installing them would fix their version — a `pg_dump` older than the server
it is pointed at refuses to run, correctly. So the source is asked what version
it is, and the program runs in the image of that version.

- **The engine runs a program once**: create, start, wait, read what it printed,
  remove — the removal in a `finally`, because a container kept for its exit code
  is one nobody will look at again.
- **The source says what to run.** `SupportsBackup` answers with an image, an argv
  and an environment; a source that cannot say does not implement it and the route
  answers 501, the rule every capability follows.
- **The password is in the environment, never in the arguments.** Arguments are
  visible to anything that can list processes, and `PGPASSWORD` is what libpq
  documents for this.
- **A backup is a file in the owner's personal storage**, written there by the
  program itself: the storage is a named volume, so the container mounts it and
  writes where the file source will list it. No copying out of a container, no
  streaming through the application, no path on the host. A deployment that has not
  said which volume gets no offer, because a dump written inside a container that
  is then thrown away is worse than a refusal.
- **Both are jobs**, with the same durable state, named steps and socket as
  everything else the server owns (D81) — a dump of anything real is minutes.
- **A restore says that it is meant.** `--clean` drops every object in the dump
  from the target first, so the request carries `understood` and one without it is
  refused. The handler does not check again: a job carries out what was decided.
- **Which backup travels in the job's `parameters`**, a small column for a kind of
  work that needs more than a subject. Never a secret: a job row is not encrypted.
- **A backup is named, not pathed.** The name is matched against the files in one
  folder, so nothing resolves a path a client wrote — D8's containment rule, kept
  by having nothing to contain. Deleting one is that same match and then an
  `unlink`: no job, because removing a file is not minutes of work.
- **Which sources this is offered for is read off the driver.** `SupportsBackup`
  puts a `backup` capability on the type, the button is greyed out where the type
  does not declare it, and pressing it anyway answers 501. Two questions, not one:
  whether the machine can run the program at all is the offer, and whether this
  source can name one is the capability. `backup_availability()` adds the live
  source answer (D122); the authenticated offer accepts a connector ID and combines
  it with runtime and storage availability. Admission and execution repeat it, and
  ownership, enabled state and the prepared program are rechecked after the tool
  image is fetched.
- **Backing up is the owner's.** Copying a database out whole is every row, every
  schema and every function in one file the caller keeps, which is more than a
  read.

Known deviations:

- **Only PostgreSQL and MySQL (D240).** Redis has no equivalent here, and the
  file source's answer to "back this up" is that it is already files. Both say so by not declaring the
  capability, which is what greys the button out.
- **No schedule and no retention.** A backup happens when somebody presses the
  button, and stays until they delete it.
- **A dump is not verified.** Nothing reads it back to check it can be restored,
  and a truncated one is found out at the moment it matters.
- **A restore may be pointed only at the connection the screen offers it for.**
  Nothing in the model forbids restoring into another connection of the same kind;
  nothing offers it either.
- **The program's own last line is passed on when it fails.** It is the program's
  words about a database rather than the daemon's about the machine, and it may
  still name a host or a database.

Spec: [Copying a database out, and putting it back](../decisions/2026-09-03-backup-and-restore-design.md)
