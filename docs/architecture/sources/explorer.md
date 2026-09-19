# The file explorer

Everything this application does with a tree of files, written once, and the
storage a source brings to it. Read this before adding a source that is made
of files — FTP, an object store, a remote disk — or before changing how a file
source lists, reads or writes.

Decisions here: D150, D151.

```
backend/app/adapters/
├── explorer/
│   ├── storage.py      Storage, Entry, the place of a node id, the name rule
│   ├── explorer.py     Explorer: every capability over one storage
│   ├── catalog.py, members.py, search.py, summary.py
│   ├── content.py, fetch.py, relation.py, update.py, new_relation.py
│   ├── query.py, query_readers.py, dialect.py
│   ├── actions.py, download.py, packing.py
│   └── formats.py, readers.py, records.py, logs.py, binary.py, media.py,
│       parquet.py, workbook.py, arrow.py, archive.py
├── file/
│   ├── storage.py      LocalStorage: the server's own disk below a home
│   ├── options.py      the folder inside the home
│   └── adapter.py      FileAdapter(Explorer), registered as `file`
└── ssh/                an SSH server; on the explorer next (ssh.md)
```

## D150. A source made of files is a storage under one explorer

The catalog, the formats read as text, tables and media, SQL over files, the
editor, search, summaries and the file actions are one package,
`adapters/explorer`, built over a `Storage`. A source that is a tree of files
brings a storage and nothing else of this: where a node id lands, how a folder
is listed, how bytes are read and how a new file is put in place. The explorer
says what the bytes mean.

- **A place is opaque to the explorer.** It is what a node id becomes once the
  storage has judged it — a key and a name — and a folder's child, a node's
  parent and whether one node is inside another are the storage's to answer.
  The disk and an SSH server name a node by its path below the root, so their
  ids are the paths they always were; a store that names files by id, where
  two files in one folder may share a name, will name a node by that id, and
  the explorer does not change for it. D8 is judged by the storage and by
  nothing else, and so is whether a link may be followed: the local disk
  follows one that stays inside the root, as it always did.
- **What a source does not have is a missing action, not a stub.** A storage
  whose folders cannot become connections of their own does not implement
  `DraftsConnections`, and its source leaves `ConnectFolder` out of its action
  types — the registry reads that tuple, so the catalog never offers it.
- **A write is staged, then published.** A new file, an edited document, a
  rewritten CSV, an upload and a packed archive are all written to a staged
  local file and published in one step: claiming a name that nothing holds, or
  replacing a file that is still the version it was read as. On the local disk
  that is the link and the rename it always was.
- **The formats read a local file.** DuckDB, openpyxl, pyarrow, Pillow and
  `zipfile` take a path. The storage lends one: on the local disk the file
  itself, for a remote storage a copy that carries the file's own name. An
  archive entry was already read this way — expanded into a temporary file and
  handed to the ordinary viewer (D53) — and a remote file is the same idea one
  level up.

Rejected: a copy of the explorer per source, which is what the old application
had. Its SSH and FTP adapters each carried their own catalog, archive, media and
search code, some two thousand lines of it, each with a different subset of what
the local explorer could do, and a fix in one reached none of the others.

Rejected: fsspec as the contract. It is the standard filesystem interface of
Python's data tools and it covers S3, GCS, FTP, SFTP and more, but it is not
where this application's rules live: the server key a connection pinned, keys
that never touch the disk, errors that name no address. The contract is ours,
and fsspec may sit behind one storage where it fits — an object store — rather
than in front of all of them.

Known deviations:

- **Only the local disk is a storage so far.** SSH reads over SFTP on its own
  (D144) until it is moved onto the explorer; that move removes its catalog,
  reader and actions.
- **A listing reads every entry's facts.** The local disk used to count a
  folder before describing it; `entries` describes what it lists, so a folder
  the catalog refuses as too large is described first and refused after.

Spec: [One explorer over every tree of files](../../decisions/2026-09-19-file-explorer-design.md)

## D151. A storage blocks, and is asked from a worker thread

Every method of `Storage` is synchronous and is called from a worker thread,
never from the event loop. The explorer's walks, its format readers and the
libraries under them are synchronous already, and they ran in threads before
there was a storage; keeping the storage synchronous kept every one of them as
it was. A storage whose library is asynchronous brings its answers into the
thread; one whose library blocks — `ftplib`, `boto3` — needs nothing extra.

Each capability makes one hop into a thread and does its work there, actions
included: an action that asked a remote storage anything on the event loop would
stall every other request while the server answered.

Rejected: an asynchronous storage. Every walk the explorer makes — a search, a
copy of a folder, the size of a paste, an archive of a selection — would have
been rewritten as coroutines, and the local disk would have paid a hop to a
thread for every stat of a hundred thousand it may make.

Spec: [One explorer over every tree of files](../../decisions/2026-09-19-file-explorer-design.md)
