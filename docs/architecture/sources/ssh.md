# SSH

A server reached over SSH as a source, the server key a connection trusts,
and the SSH keys a person signs in with. Read this before changing how an SSH
connection signs in, what it trusts, or where a private key is kept.

Decisions here: D144, D145, D146, D147, D153.

```
backend/app/adapters/
├── credentials.py      SigningKey, KeyAccess, ServerKey, PinsServerKey
└── ssh/
    ├── keys.py         the one place asyncssh reads a key: make, import, describe
    ├── options.py      password or key, the folder, the pinned server key
    ├── session.py      signing in, the kept connection, the library's failures
    ├── storage.py      SftpStorage: the server's files for the explorer (explorer.md)
    ├── terminal.py     the login shell in a pty (D149, ../terminals.md)
    └── adapter.py      SshAdapter(Explorer), the terminal, registration
backend/app/connectors/
├── ssh_keys.py         SshKey, OwnerKeys, which connections use a key
├── keyring.py          passphrases held in memory for a while
└── ssh_key_routes.py   /ssh-keys
frontend/src/features/sshKeys/
├── SshKeysSection.vue  the keys, on the Preferences page
├── SshKeyDialog.vue    making one, or importing one
├── UnlockKeyDialog.vue opening a key that asks, for a span of time
├── ServerKeyField.vue  the server key in the connection form
└── keys.ts             the words for a key's state, and the form's choice of keys
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

## D144. An SSH server is the file explorer over SFTP, from where the connection stands

The old application listed a folder by running `ls -la` and parsing the
output, and read, archived and searched with commands of its own. Here the
source is the file explorer (D150) over a storage that speaks SFTP, so it does
what the file source does — tables, SQL over files, the editor, archives,
search, paste — and nothing runs a command on the server: no name typed into a
form ever reaches a shell. The one shell is the terminal its owner types into
([D149](../terminals.md)).

- **The explorer stands in the connection's folder**, the user's home when it
  names none, and walks down from there. A node id is the path below that
  folder, and every segment must be a plain name — the file source's rule — so
  no `..` from a client becomes a path. The folder is where browsing stands,
  not a wall: the server's own permissions decide what the user may read, and
  somebody who wants the whole disk writes `/`.
- **A link is described by what it points at**, and a broken one is left out.
  A download refuses one, and so does a folder that passes through this server
  whole — for an archive, or a copy the server cannot make itself.
- **What a library reads from a path is a local copy** (D152), bounded to
  200 MB a file; a larger file is downloaded instead. A search by content reads
  files up to 1 MB.
- **A write is sent beside its name and moved into place.** A new name is
  claimed with the plain rename, which refuses an existing one; a replacement
  keeps the file's own permissions, so a script stays executable, and is moved
  over atomically where OpenSSH allows. The version a document was read as is
  its modification time and size.
- **A copy is the server's own** where it offers one (`copy-data`), and passes
  through this server otherwise, within the same 200 MB.
- **A folder of a server is not offered as a connection of its own**: the draft
  would carry this connection's credentials to the browser.
- **A stored connection keeps its connection** in the resource store (D10) and
  signs in again when the server has closed it. A check always signs in afresh.
- **The library's defaults that reach outside the connection are refused**:
  no `known_hosts` file, no agent, no key from `~/.ssh`, no `~/.ssh/config`.
- **`asyncssh` is imported only by `adapters/ssh`**, checked by import-linter.

Known deviations:

- **A folder always claims children.** Asking would cost a round trip per
  folder of a listing; an empty one opens to nothing.
- **A modification time counts seconds.** Two writes of one size within a
  second would look like one version, so the storage drops its copies of what
  it has just written and sets a replaced file's time at least a second past
  the one it replaced, by this server's clock. A change of the same size made by
  somebody else within the second of a read is not seen until the next one.
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
  nothing else: the key is exchanged before anybody signs in. ED25519 is asked
  for first, because `ssh_host_ed25519_key.pub` is what a person usually
  compares against; a server without one presents what it has.
- **The key is kept in the connection**, as the one `known_hosts` line it is.
  It is not a secret, so it is configuration; only the owner edits it.
- **Nothing connects while none is pinned**, and a server presenting any other
  key is refused before signing in, with a sentence that says so.
- **Trusting a new key is the owner's act** in the form: fetch, compare, trust.
  A reinstalled server is a real reason, and a silent re-pin would make the
  check worthless. The one exception is a server this application started
  itself (D153).
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
- **The keys are on the Preferences page**, and the connection form offers
  them as a choice; a field is marked `x-ui-purpose: ssh-key` and the screen
  fills the choice, so the form stays generic.
- **`asyncssh` stays in its adapter**: the store asks `adapters/ssh/keys.py`
  what a key is, and never parses one itself.

Known deviations:

- **Anyone who holds the server's environment and its database can use a key
  kept without a passphrase, or with a stored one.** The connector key is in
  the environment. Only a passphrase that is asked for (D147) protects against
  that, and moving the connector key into a KMS is a decision about every
  credential, not this one.
- **A key is never rotated in place.** A new key is a new row.
- **A key is renamed only through the API.** The route exists; the
  Preferences page offers making, importing, unlocking and deleting.

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
  the passphrase rather than reporting a failure: the connection form inside
  the result of its check, the catalog beside its error and a terminal above
  its screen. Which key to open is found in
  the server's own list of which connections use which key, so only the owner
  is offered it. Unlocking re-reads what failed, and a `locked` answer is not
  retried, since asking again answers the same.
- **Unlocking checks the passphrase first**, so a mistyped one is said there.

Known deviations:

- **The keyring is a module, not something passed in.** Every place a source
  is built needs it, the health monitor among them, and that is made by a
  topic factory that takes nothing. It holds no connection and runs no task,
  and the backend is one process (D124).
- **A shared connection stops for its grantees while its owner's key is
  locked.** That is the time limit working, and the grantee cannot unlock it.
- **A source keeps the key it read for 30 seconds.** A listing is many requests
  of the server and each would read the database again. The keyring is still
  asked on every use, so locking takes effect at once; a changed passphrase
  mode waits out the 30 seconds.

Spec: [An SSH source, its server key and its keys](../../decisions/2026-09-19-ssh-source-design.md)

## D153. An SSH server this application started trusts the key it presented first

The catalog starts one like a PostgreSQL (D80): a template in
`services/templates.py`, the image `lscr.io/linuxserver/openssh-server` pinned
by tag, the one volume on its home `/config`, the account `dataplayer` with a
password made up here, and a connector filled from the same plan.

- **The key is pinned by the job, not by a person.** Nothing knows it before
  the container has made one, so the readiness probe asks for it first and
  answers with the options the source then succeeded with; the job saves those.
  The container was made moments before and is reached by its name on this
  server's own network, the path a PostgreSQL service is sent its password
  along with nothing checked. Every later connection is checked against it.
- **Which field holds the key is read off the schema**, by the purpose the
  form already uses (`ssh-host-key`), the way key references are (D146).
- **The key is asked for once it answers.** OpenSSH shuts out an address that
  keeps connecting without signing in, and asking for a key is that; a port
  nothing listens on yet refuses without counting.
- **An automatic start fills the home** with the sample files a development
  stack seeds into a personal home, written through the explorer's own storage
  from `explorer/samples.py`.
- **Its address is `ssh://user@127.0.0.1:port`**, written by the adapter, and
  stays without a password when the password is handed over: no SSH client
  takes one in an address (D89).

Known deviations:

- **A key is not offered.** The old application could start a server that
  took one of its owner's keys; here it takes a password.
- **The image is the one the development override runs**, with `latest` there
  and a pinned tag here.

Spec: [An SSH server this application starts](../../decisions/2026-09-19-ssh-service-design.md)
