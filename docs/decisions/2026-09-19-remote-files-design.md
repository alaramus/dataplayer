# A remote tree of files through the explorer

Date: 2026-09-19. Decisions: D152.

Status: implemented with this specification. SSH is the first storage to read
through the copies (D144).

## What was asked

With the explorer written once over a storage (D150), the owner asked for SSH
to do everything the file source does. Most of the explorer reads formats with
libraries that open a local path, so a remote file has to be copied to this
machine first, and that raised questions about where copies live, how large
they may be and how long they stay. The owner answered them:

1. The copies live in a folder no connection reaches, are cleared when the
   server starts and when unused for an hour, and hold at most 1 GB.
2. A file larger than 200 MB is not copied; it is downloaded instead.
3. A search by content on a remote server reads only files up to 1 MB, with a
   limit on the whole search.
4. Copying inside a remote server uses the server's own copy where it has one,
   and otherwise goes through this server within the same 200 MB.
5. Google Drive is planned, so a node is named opaquely by its storage rather
   than by a path the explorer builds.

## What was decided

**D152 — a bounded local copy per version.** `explorer/copies.py` keeps every
copy under one root beside the personal homes. A copy is keyed by the storage
(its address and its credentials), the node and the version, and is written
beside its name and moved into place so no reader opens half a file. Readers
count; the idle and capacity sweeps skip a copy somebody holds. Staged writes
and fetched trees use scratch folders under the same root, so one sweep at
start clears whatever a crash left.

The fifth answer was carried out before this one: a place is a key and a name,
and the explorer asks the storage for a child, a parent and whether one place
is inside another (D150).

Corrected after it shipped: every viewer and every summary went through a
copy, so a recording was fetched whole before its header was read, and one
larger than 200 MB did not play at all, although the stream behind it was
ranged from the start (D52). The header readers were already bounded; they
were handed a path. They now read the storage's seekable `open`, and only the
libraries that take a path — tables, workbooks, Parquet, archives, SQL — are
given a copy.

## Left for later

- Parquet described from its footer through the handle rather than a copy:
  pyarrow can read a file object, and the footer is all a summary needs.
- Encryption of the copies at rest, if personal storage gets it.
