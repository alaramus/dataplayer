# The file explorer

Everything this application does with a tree of files, written once, and the
storage a source brings to it. Read this before adding a source that is made
of files — FTP, an object store, a remote disk — or before changing how a file
source lists, reads or writes.

Decisions here: D150, D151, D152.

```
backend/app/adapters/
├── explorer/
│   ├── storage.py      Storage, Place, Entry, search limits, the name rule
│   ├── copies.py       local copies of remote files, and scratch folders
│   ├── samples.py      one sample file of every kind, for a home or a started server
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
└── ssh/
    ├── storage.py      SftpStorage: a server's files over SFTP (ssh.md)
    └── adapter.py      SshAdapter(Explorer) without ConnectFolder, and a terminal
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
  that is the link and the rename it always was. A transfer from another
  connection is the exception: `incoming` writes it where it is going, piece
  by piece — beside its target on the disk, under a temporary name on an SSH
  server — because gigabytes staged here first would fill this machine's disk
  (D168).
- **A format whose library takes a path reads a local file.** DuckDB,
  openpyxl, pyarrow and `zipfile` do. The storage lends one: on the local disk
  the file itself, for a remote storage a copy that carries the file's own
  name (D152). An archive entry was already read this way — expanded into a
  temporary file and handed to the ordinary viewer (D53) — and a remote file is
  the same idea one level up. Everything else reads through the storage's
  seekable `open`.

Rejected: a copy of the explorer per source. That is what the old application
had, and a fix in one of its two thousand lines of per-adapter catalog, archive,
media and search code reached none of the others.

Rejected: fsspec as the contract. It covers S3, GCS, FTP and SFTP, but it is not
where this application's rules live: the server key a connection pinned, keys
that never touch the disk, errors that name no address. The contract is ours,
and fsspec may sit behind one storage where it fits, rather than in front of
all of them.

Known deviations:

- **A listing reads every entry's facts.** The local disk used to count a
  folder before describing it; `entries` describes what it lists, so a folder
  the catalog refuses as too large is described first and refused after.

Spec: [One explorer over every tree of files](../../decisions/2026-09-19-file-explorer-design.md)

## D151. A storage blocks, and is asked from a worker thread

Every method of `Storage` is synchronous and is called from a worker thread,
never from the event loop. The explorer's walks, its format readers and the
libraries under them are synchronous already and ran in threads before there was
a storage, so keeping the storage synchronous kept every one of them as it was. A
storage whose library is asynchronous brings its answers into the thread; one
whose library blocks — `ftplib`, `boto3` — needs nothing extra.

Each capability makes one hop into a thread and does its work there, actions
included: an action that asked a remote storage anything on the event loop would
stall every other request while the server answered.

Rejected: an asynchronous storage. Every walk the explorer makes — a search, a
copy of a folder, the size of a paste, an archive of a selection — would have
been rewritten as coroutines, and the local disk would have paid a hop to a
thread for every stat of a hundred thousand it may make.

Spec: [One explorer over every tree of files](../../decisions/2026-09-19-file-explorer-design.md)

## D152. A remote file is read from a bounded local copy

The libraries a table, a workbook, an archive and SQL are read with open a file
on this machine, so a storage that is not this machine's disk lends them a copy.
Every copy lives in one place, `explorer/copies.py`:

- **Only for a library that opens a path.** A viewer that decides from a
  header or a bounded prefix reads the file where it lies, through the
  storage's seekable `open`: a recording, a sound file and a PDF by the blocks
  their headers name, a picture by its header and then whole to be shown
  (D49), text, Markdown, JSON, JSONL and the editor as far as each shows, and
  a summary of any of them the same way. Every range a player asks for is read
  in place too, so a recording plays whatever it weighs and costs its header
  before its first frame.

- **Where.** `USER_STORAGE_ROOT/.explorer-copies`, beside the personal homes
  and out of reach of every file source, which is where restore snapshots
  already stage (D122). Emptied when the process starts.
- **Per version.** A copy belongs to one version of one file of one storage,
  so a file that changes is fetched again beside the old copy rather than over
  it while somebody still reads the old one. The storage is named by its
  credentials as well as its address, so two people reaching one server with
  different rights never read each other's copies.
- **Fetched once.** Two readers of one version wait for one transfer.
- **Bounded.** A file larger than 200 MB is not copied — a table, a
  workbook or an archive that large is downloaded instead, and the refusal
  says so. The copies together hold 1 GB, and a copy
  nobody has read for an hour goes; the oldest go first, and a copy that is
  being read never does.
- **What passes through here is bounded the same way.** A tree fetched for an
  archive, an archive's contents on the way back, and a copy between two
  folders of a server that cannot copy by itself are held to 200 MB.
- **A search by content reads less.** Files up to 1 MB, 32 MB in one search,
  where the local disk reads 8 MB and 256 MB: every byte is a transfer.

Known deviations:

- **The copies are the process's**, correct while the backend is one (D124).
- **A copy is not encrypted at rest**, any more than personal storage is; it is
  as reachable as the homes beside it, and gone within an hour of its last read.

Spec: [A remote tree of files through the explorer](../../decisions/2026-09-19-remote-files-design.md)
