# A limit on personal storage

Decision D324. Until now a person's directory under `USER_STORAGE_ROOT` could
grow until the server's disk was full, and one person filling it stopped
everybody.

## The figure

`USER_STORAGE_QUOTA_MB` is the server's figure for everyone; 0 is no limit,
which is also the default, so an installation that sets nothing behaves as
before. A superuser may set another figure for one person on the account
(`user.storage_quota_mb`, null for the server's, 0 for none). It is not on
`UserBase`, so neither signing up nor editing one's own account can name it.

Rejected: one figure for everyone only. An installation with an analyst who
keeps large extracts and a dozen people who keep notes needs two numbers.

## Where it is held

The figures set for people are held by the process, loaded at start and kept
in step by the user routes (`app/users/quota.py`). An adapter is built in a
dozen places, several without a session, and a context is built synchronously;
a database read there would be a query per write. This holds because the
backend is one process (D124).

## Where it is judged

`LocalStorage` judges every write the server makes into a home: publishing a
staged file (upload, saving a file's text, a table's rows, a new CSV, a paste,
an archive made), copying, and filling a folder in place (unpacking). Usage is
the walk of the whole home, not of the connection's folder, so two file
connections in one home share one limit.

- A write that does not grow the home always passes, so somebody over the
  limit can still replace a file with a smaller one, or delete.
- A staged file is already in the home and counted once; what it replaces is
  subtracted.
- The refusal is `StorageFull`: an `ActionRefused` of reason `too_large`
  (413) for actions and pastes, and a `ValueError` for the routes that save a
  file's text, which answer with its message.

Rejected: counting usage incrementally. A SQLite file grows and a program in a
container writes without telling the server, so a kept counter would drift;
the walk is the truth, at the cost of one directory walk per write.

## What it does not stop

- A SQLite file growing, and programs run in a container over the home
  (backups, terminals), write without the server's hand. They can take a home
  past its limit; the next write the server makes is then refused until space
  is freed.
- Unpacking is judged once the files have landed. Into a new folder, the
  folder is removed; beside the archive, what landed stays.

## What a person sees

Preferences → General shows what is in use against the limit, with a bar
where there is one (`GET /users/me/storage`). The users table shows each
person's figure, and the account form edits it.
