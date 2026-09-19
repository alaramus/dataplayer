# SSH

A server reached over SSH as a source, the server key a connection trusts,
and the SSH keys a person signs in with. Read this before changing how an SSH
connection signs in, what it trusts, or where a private key is kept.

Decisions here: D144, D145, D146, D147.

```
backend/app/adapters/
├── credentials.py      SigningKey, KeyAccess, ServerKey, PinsServerKey
└── ssh/
    ├── keys.py         the one place asyncssh reads a key: make, import, describe
    ├── options.py      password or key, the folder, the pinned server key
    ├── session.py      signing in, the kept connection, the library's failures
    ├── catalog.py      folders over SFTP, one level at a time
    ├── content.py      a text file, a bounded page of it
    ├── actions.py      new folder, upload, download, rename, delete
    └── adapter.py      facade and registration
backend/app/connectors/
├── ssh_keys.py         SshKey, OwnerKeys, which connections use a key
├── keyring.py          passphrases held in memory for a while
└── ssh_key_routes.py   /ssh-keys
```

```
GET    /api/v1/ssh-keys/
POST   /api/v1/ssh-keys/generate
POST   /api/v1/ssh-keys/import
PATCH  /api/v1/ssh-keys/{key_id}
DELETE /api/v1/ssh-keys/{key_id}
POST   /api/v1/ssh-keys/{key_id}/unlock
POST   /api/v1/ssh-keys/{key_id}/lock
POST   /api/v1/connectors/server-key
```

## D144. An SSH server is a folder tree read over SFTP, from where the connection stands

The old application listed a folder by running `ls -la` and parsing the
output. Here nothing runs a command on the server: the catalog, the reader and
the actions are SFTP requests, so no name typed into a form ever reaches a
shell. The terminal is a slice of its own.

- **The catalog stands in the connection's folder**, the user's home when it
  names none, and walks down from there. A node id is the path below that
  folder, and every segment must be a plain name — the file source's rule — so
  no `..` from a client becomes a path. The folder is where browsing stands,
  not a wall: the server's own permissions decide what the user may read, and
  somebody who wants the whole disk writes `/`.
- **Files and folders are the file source's node kinds.** A link is described
  by what it points at; a broken one is left out.
- **A file opens as text, and Markdown as a document.** Chosen by name with the
  file source's rules, narrowed to what this source reads: a table, an image or
  a player over SFTP would be buttons that fail.
- **Five actions, on the file source's forms**: a new folder, an upload, a
  download, a rename and a delete. The folder the connection stands in is added
  to and never renamed or removed. An upload is written beside its destination
  and moved into place, replacing atomically where OpenSSH allows.
- **A stored connection keeps its connection** in the resource store (D10) and
  signs in again when the server has closed it. A check always signs in afresh.
- **The library's defaults that reach outside the connection are refused**:
  no `known_hosts` file, no agent, no key from `~/.ssh`, no `~/.ssh/config`.
- **`asyncssh` is imported only by `adapters/ssh`**, checked by import-linter.

Known deviations:

- **A folder always claims children.** Asking would cost a round trip per
  folder of a listing; an empty one opens to nothing.
- **A download is one file.** A folder or a selection is refused rather than
  archived.
- **No search, no summary, no rows.** The file source's readers work on local
  paths and are not reused over SFTP yet.
- **The address is the client's.** Fetching a server key opens a connection to
  a host the form names, the SSRF of D2's check-draft.

Spec: [An SSH source, its server key and its keys](../../decisions/2026-09-19-ssh-source-design.md)

## D145. A connection trusts one server key, pinned by a person before anything is sent

What stops a password or a signature going to a server that only claims to be
the one intended. Jenkins calls it "accept first connection", Bitbucket
Pipelines "fetch and add host"; this is the second, with the fingerprint shown
before anything is trusted.

- **The form asks the server for its key and shows its fingerprint** before a
  credential is typed into anything that sends it. Asking sends a greeting and
  nothing else: the key is exchanged before anybody signs in.
- **The key is kept in the connection**, as the one `known_hosts` line it is.
  It is not a secret, so it is configuration; only the owner edits it.
- **Nothing connects while none is pinned**, and a server presenting any other
  key is refused before signing in, with a sentence that says so.
- **Trusting a new key is the owner's act** in the form: fetch, compare, trust.
  A reinstalled server is a real reason, and a silent re-pin would make the
  check worthless.
- **There is no "do not verify" setting.** The old application had one as its
  only mode.
- **`POST /connectors/server-key`** describes the pinned key without a network
  call and, when asked, fetches the presented one and says whether they match.
  The comparison is the server's, so the client does not repeat it.

Spec: [An SSH source, its server key and its keys](../../decisions/2026-09-19-ssh-source-design.md)

## D146. SSH keys are a person's, apart from connections, and their private half is write-only

One key serves as many connections as its owner points at it, and replacing
it is one change. Coolify and Semaphore keep keys this way; Rundeck makes the
private half write-only.

- **A key is made on this server or imported.** Made is the default, ED25519
  (RSA for servers that refuse it): the private half never existed anywhere
  else, and a leaked key opens only the servers it was added to for this
  application. The public line ends in `dataplayer`, so a server's owner can
  tell which line of `authorized_keys` it is.
- **The private half is never read back.** No route returns it; what a person
  sees is the public line, the fingerprint and the connections that use the
  key. It is encrypted under the connector key (D4), itself encrypted under its
  passphrase when it has one.
- **A connection names a key by id**, and the driver is handed the key at the
  moment it signs in, through `AdapterContext.keys`. Only the owner's keys
  answer: a grantee reading a connection signs in with the owner's key (D33),
  and a draft signs in with its author's.
- **Which option names a key is read off the schema**, the way secrets are
  (D4): the store finds the connections that use a key without a list.
- **A key in use is not deleted**, and the refusal names the connections.
- **`asyncssh` stays in its adapter**: the store asks `adapters/ssh/keys.py`
  what a key is, and never parses one itself.

Known deviations:

- **Anyone who holds the server's environment and its database can use a key
  kept without a passphrase, or with a stored one.** The connector key is in
  the environment. Only a passphrase that is asked for (D147) protects against
  that, and moving the connector key into a KMS is a decision about every
  credential, not this one.
- **A key is never rotated in place.** A new key is a new row.

Spec: [An SSH source, its server key and its keys](../../decisions/2026-09-19-ssh-source-design.md)

## D147. A passphrase is stored, or asked for and held in memory for 15 minutes, an hour or eight hours

AWX calls the second "prompt on launch"; `ssh-add -t` is the same idea for an
agent. It is the one mode in which a copy of the database and the environment
opens nothing.

- **The mode is the owner's, per key**: none, stored beside the key, or asked.
  A key that asks keeps no passphrase in the database.
- **An asked passphrase is held in this process only**, until its time is up
  or the key is locked by hand, and a restarted server holds none. The clock is
  the monotonic one, so moving the system clock keeps nothing open.
- **The key is asked for on every use**, not only on signing in, so a key that
  has been locked stops the source even while a kept connection is open.
- **A locked key is an error of its own kind**, `locked`, so a screen offers
  the passphrase rather than reporting a failure.
- **Unlocking checks the passphrase first**, so a mistyped one is said there.

Known deviations:

- **The keyring is a module, not something passed in.** Every place a source
  is built needs it, the health monitor among them, and that is made by a
  topic factory that takes nothing. It holds no connection and runs no task,
  and the backend is one process (D124).
- **A shared connection stops for its grantees while its owner's key is
  locked.** That is the time limit working, and the grantee cannot unlock it.

Spec: [An SSH source, its server key and its keys](../../decisions/2026-09-19-ssh-source-design.md)
