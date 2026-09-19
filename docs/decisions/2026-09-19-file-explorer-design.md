# One explorer over every tree of files

Date: 2026-09-19. Decisions: D150, D151.

Status: the explorer and the local storage are implemented with this
specification, and SSH is its second storage (D144, D152). FTP and object
stores follow when they are asked for.

## What was asked

SSH had just been added as a source, reading its server over SFTP with a
catalog, a text reader and five actions of its own. The owner asked for it to
do everything the file source does, and pointed out that more sources of the
same kind are coming — FTP first, perhaps others — and that copying the file
source into each of them is the thing to avoid. The question was how to make
the next one cheap.

## The old application

- `file_explorer` was the full set: catalog, formats, archives, media,
  full-text search, folder actions, about twenty modules.
- `ssh` and `ftp` each had their own `*_catalog_operations`,
  `*_crud_operations`, `*_archive_operations` and `*_media_operations`, about
  1,900 lines between them, each doing a subset of what the local explorer did
  and none sharing its code.
- `s3`, `minio`, `rustfs`, `google_cloud` and `google_drive` were adapters of
  their own with still less; `iso_explorer` inherited the local one.

A fix or a feature landed in one of these and not the others, and what a person
could do with a folder depended on which server it was on.

## What was decided

**D150 — a storage under one explorer.** The file source's modules moved to
`adapters/explorer` unchanged in what they do, and every filesystem call in them
now goes through a `Storage`:

- `place(node_id)` — the containment rule, links judged by the storage;
- `entry`, `entries`, `has_entries`, `version` — what is there;
- `open` — bytes, seekable; `local_file`, `local_tree`, `local_root` — a path
  on this machine for the libraries that read one;
- `staged` and `publish` — every write, claiming a name or replacing a version;
- `make_directory`, `make_file`, `rename`, `copy`, `remove`, `filled` — the
  rest of the actions.

`file` became `LocalStorage` plus `FileAdapter(Explorer)`. A new source is a
storage, its options and a subclass that says which actions it offers.

**D151 — synchronous, called from threads.** Chosen because the explorer was
already synchronous inside threads; an asynchronous contract would have meant
rewriting every walk for the sake of the storages that are asynchronous, and a
thread hop per stat on the local disk.

Considered and set aside:

- **fsspec as the contract.** It is what pandas and DuckDB speak and it covers
  most remote filesystems. It does not know this application's rules — a
  pinned server key, keys kept off the disk, errors without addresses — so it
  may implement a storage, not define one.
- **Pathlib-shaped remote paths** (universal-pathlib and the like). Half the
  explorer calls `os.scandir`, `os.link`, `shutil` and libraries that want a
  real path, so a path object that only looks local would fail in the places
  that matter most.

## Left for later

- **SSH on the explorer** was left here and answered by the owner; it is
  [A remote tree of files through the explorer](2026-09-19-remote-files-design.md).
- **A folder of a remote source as a connection of its own**: the draft would
  carry the connection's secrets to the browser, so it is left out until that
  is solved.
