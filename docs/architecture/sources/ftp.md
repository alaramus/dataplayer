# FTP and FTPS

An FTP server, plain or over TLS, as one more storage under the file explorer
(D150). Read [explorer.md](explorer.md) first: the catalog, the viewers, SQL
over files and search are the explorer's, and this is only the storage under
them.

Decisions here: D384, D385, D386.

```
backend/app/adapters/ftp/
├── options.py   the form: host, port, encryption, certificate, folder, password or anonymous
├── client.py    connections lent from a pool per set of options, failures reduced to kinds
├── listing.py   MLSD and LIST lines read into entries, tested without a server
├── storage.py   FtpStorage: a path below the folder as a node id
└── adapter.py   FtpAdapter(Explorer) without ConnectFolder, registered as `ftp`
```

`ftplib` is imported by this package and nothing else (`.importlinter`). It
blocks, as a storage does (D151), so nothing goes back to the event loop.

## D384. An FTP server is a storage, reached through a pool of connections

- **Ids are paths**, as on SSH: a node id is the path below the connection's
  folder (`PathPlaces`). The folder is where browsing stands, not a wall: the
  server's own permissions are, as on SSH (D144). An absolute folder is taken
  as it is; a relative or empty one is below the folder the server signs the
  user into (`PWD`).
- **Connections are lent.** A control connection serves one command at a time,
  so every set of options has a pool: a request takes a connection and gives
  it back. Four at most are open at once, because servers limit connections
  per address; a request waits a minute for one, then fails as a timeout. A
  connection idle for 15 seconds, or given back after a failure, is asked NOOP
  before it is lent again; one idle for two minutes is closed. A kept
  connection the server closed meanwhile fails only the next command, so that
  work is done once more on a new connection.
- **A listing is MLSD where the server speaks it**, by FEAT, and LIST
  otherwise — vsftpd, the most common server, has no MLSD. LIST is read in
  `ls -l`'s shape, found by its date rather than by counting columns, and in
  Windows' `dir` shape; `LIST -a` first, so names beginning with a dot are
  listed. A line that fits neither is left out.
- **Names are bytes.** ftplib reads both channels as strict UTF-8, so one name
  in another encoding would fail a whole listing. Both are read with
  `surrogateescape`, and a name that is not UTF-8 is left out of a listing, as
  a name the path rule refuses is. It stays on the server.
- **A link is what it points at.** One that can be entered is a folder, one
  whose size can be read a file, and one that is neither is left out.
- **Reading** is RETR at an offset given by REST, buffered by 256 KB. A read
  where the last one ended goes on reading the open transfer; any other cuts
  it short and starts a new one, and the connection is kept only if NOOP's
  answer can be read past the replies to the transfer cut short. A library
  that opens a path gets a copy (D152), and a search by content reads as
  little as on SFTP (`REMOTE_SEARCH`).
- **Facts** are the size, the modification time and, where the listing says
  them, the permissions. `version` is the time from MDTM, to the second where
  the server has it, and the size.
- **TLS on the data channel resumes the control channel's session**, which
  vsftpd, FileZilla Server and pure-ftpd require and ftplib does not do.
- **Failures are kinds.** A refused login, a refused certificate, a failed TLS
  handshake, a name that does not resolve, a timeout, a closed connection, a
  server with too many connections and an unreachable host each become a kind
  and a sentence. The server's own words are logged and never passed on.

Known deviations:

- **Times are taken as UTC.** LIST does not say the server's time zone, and
  gives a time to the minute for the last six months and only the day before.
- **Passive mode only.** An active connection from a server back to this one
  does not pass a container's network or a NAT. The address in PASV's answer
  is ignored and the control connection's host used, so a server behind NAT
  still works.

Spec: [FTP and FTPS as a storage of the explorer](../../decisions/2026-11-20-ftp-storage-design.md)

## D385. Writes go under a temporary name, and what FTP lacks passes through here

- **A write is staged, then published**, as the explorer writes everywhere: the
  file is sent with STOR under `.dataplayer-<id>` beside its name and renamed
  into place, so nobody reading the folder sees half a file. Whatever is not
  put in place is deleted. `incoming` (D168) sends a transfer the same way as
  it arrives, nothing staged here whole.
- **Claiming a name asks first.** FTP has no rename that refuses a taken name,
  and most servers overwrite one, so the name is looked up before the rename.
- **Replacing compares the version** a document was read as and refuses with
  `VersionChanged` when it moved. The permissions are kept with `SITE CHMOD`
  where the server takes it. A server that refuses to rename over a file
  (IIS) has it deleted first. Where MFMT is spoken, the time is set a second
  past the old one, so two saves inside one second are two versions.
- **No copy on the server.** FTP has none, so a copy is read here and sent back,
  within the 200 MB that may pass through this server (D152); a folder holding
  a link is refused, as on SFTP.
- **Removing a folder** removes what it holds first, a file at a time, since
  RMD takes only an empty folder; `remove_empty` is RMD itself (D169).
- **No connection of its own for a folder**: its draft would carry the
  password to the browser (`ConnectFolder` left out), as on SSH.

Known deviations:

- **A claim races.** A file made by somebody else between the lookup and the
  rename is overwritten on a server that renames over files.
- **A move is a rename** within a connection, and between connections a copy
  and a removal, as everywhere; cut short, it leaves the file in both places.

Spec: [FTP and FTPS as a storage of the explorer](../../decisions/2026-11-20-ftp-storage-design.md)

## D386. One form, explicit TLS by default, an address without a password

- **The form** asks for the host, the port, the encryption, whether to verify
  the certificate, the folder, and a user and password — or nothing, for
  anonymous sign-in, which sends `anonymous` and `anonymous@`. Signing in is a
  discriminated union, as Redis's is (D16).
- **Explicit TLS is the default.** It is what servers speak today, on port 21.
  Implicit TLS is the older FTPS on 990. No encryption sends the password as it
  is typed, and is chosen, never fallen back to: a server that refuses AUTH TLS
  is refused with a sentence that names the choice.
- **A line break is refused** in the host, the folder and the user, and in any
  name sent, since it would end the command and begin another.
- **An address names the server, never the password**: `ftp://user@host:port/folder`,
  `ftps://` for implicit TLS as curl reads it, an absolute folder as `//`
  after the host (RFC 1738). One pasted in fills the host, the port, the user
  and the folder, every part answered, an empty one as empty; `ftps://` also
  chooses implicit TLS. One with a password, a query or a fragment is refused.
- **No card and no service template.** There is one kind of FTP server to
  reach, and none this product starts.
- **The test server is pyftpdlib** in the test's own process, with pyOpenSSL
  for TLS, both development dependencies: no container, no CI service. Every
  storage test runs against one that speaks MLSD and one that answers LIST
  alone, and explicit TLS against one that requires it on both channels under
  a certificate made for the test.

Known deviations:

- **Implicit TLS is not tested.** pyftpdlib does not serve it.

Spec: [FTP and FTPS as a storage of the explorer](../../decisions/2026-11-20-ftp-storage-design.md)
