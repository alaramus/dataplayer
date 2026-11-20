# FTP and FTPS as a storage of the explorer

Decisions D384–D386. An FTP server is a tree of files reached over a protocol
older than every other this product speaks. This source makes it one more
storage under the explorer (D150), so the catalog, the viewers, SQL over files,
search, the editor, transfers and the file actions are the ones the disk, SFTP
and S3 already have. One type, `ftp`, reaches plain FTP, explicit TLS and
implicit TLS.

## Driver

`ftplib`, the standard library's. It blocks, which is what a storage is asked
to do (D151), and it is already on every platform this product runs on. What
it lacks is added in `client.py`: names read as bytes rather than strict UTF-8,
TLS on the data channel resuming the control channel's session, and implicit
TLS, which it does not have at all.

Rejected:

- **aioftp.** Asynchronous, which the storage would only bring back into a
  thread, as asyncssh is for SFTP — the hop SFTP pays and FTP need not. Its TLS
  support is thinner than ftplib's.
- **fsspec's FTP filesystem.** It is ftplib underneath, and it is not where
  this application's rules live (D150): errors that name no address, names in
  any bytes, a pool shaped by the servers' limits.
- **pycurl.** A C extension to build on every platform, for a protocol the
  standard library speaks.

## D384. An FTP server is a storage, reached through a pool of connections

A node is named by its path below the connection's folder, as on SSH. The
folder is where browsing stands, not a wall; the server's permissions are.

A control connection answers one command at a time, while the explorer asks
from several threads — a listing while a file is being read — so connections
are lent from a pool per set of options. Four at most: vsftpd, pure-ftpd and
hosting providers commonly allow a handful per address, and a fifth request
waiting a moment is better than a refusal from the server. A server closes an
idle connection after a few minutes and says so only to the next command, so a
connection idle for a while is asked NOOP before it is lent; one that fails its
first command after being kept has that work done again on a new connection.

MLSD is the one listing a machine can read without guessing, and it is used
wherever FEAT says the server speaks it. vsftpd does not, and is the most
common server there is, so LIST is read as well: `ls -l`'s shape, found by its
date — the one column every server prints — and Windows' `dir`. LIST says
neither the year of a recent file nor the time zone of any, so times are taken
as UTC; `version` asks MDTM, where the server has it, for a time to the second.

A name in an encoding other than UTF-8 is common on old servers and would fail
ftplib's whole listing. Both channels are read with `surrogateescape`, and such
a name is left out of the listing — it could not be shown to a browser or
carried in an id — rather than taking every other name with it.

Reading at an offset is REST and RETR. A sequential read goes on reading the
transfer already open; a seek cuts it short, and the connection is kept only
if NOOP can be read past whatever the server answers to the transfer it lost:
426, 226, or both, depending on the server.

## D385. Writes go under a temporary name, and what FTP lacks passes through here

The explorer stages and publishes every write. On FTP that is STOR under a
temporary name beside the target and a rename into place, so a reader never
sees half a file under the name it looks for. FTP's rename overwrites on most
servers and refuses on IIS, and none has a rename that refuses a taken name, so
a claim looks the name up first, with the race that leaves, and a replace
deletes the old file first where a rename over it is refused.

FTP has no copy. `SITE CPFR`/`CPTO` exists only in ProFTPD's mod_copy, so a copy
passes through this server, within the 200 MB a copy may be (D152).

## D386. One form, explicit TLS by default, an address without a password

Explicit TLS is the default because it is what servers speak today on port 21;
falling back to plain FTP when AUTH TLS is refused would send the password in
the clear to whoever stripped the offer, so the choice is the person's, and
the refusal says so. Implicit TLS is kept for the servers that still listen on
990. Anonymous sign-in is a choice of its own rather than a user field left as
`anonymous`, because it has no password to keep secret (D16).

A line break in a field or a name would end one command and begin another, so
it is refused wherever a string reaches the control channel.

The address is curl's: `ftps://` is implicit TLS, explicit TLS is `ftp://`, and
an absolute folder follows a double slash, as RFC 1738 spells it.

## Tests

pyftpdlib in the test's own process, with pyOpenSSL for explicit TLS: no
container to start and no CI service to declare. Every storage test runs
twice, once against a server speaking MLSD and once against one with MLSD and
MLST taken away, which answers LIST alone. The listing parsers are tested on
the lines vsftpd, ProFTPD and IIS print. Implicit TLS has no test server.

## Rejected

- **A docker FTP server in `compose.override.yml`.** Passive ports have to be
  published and the PASV address configured for both the host and the backend
  container; an in-process server needs neither.
- **Active mode.** A connection from the server back to this one does not cross
  a container's network or a NAT.
- **A connection per request.** A login is several round trips, and TLS a
  handshake more; a listing of a deep folder would pay them for every level.
