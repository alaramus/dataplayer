# A database reached through an SSH connection

## D282. A database names one of its owner's SSH connections as its tunnel

PostgreSQL, TimescaleDB, MySQL, MariaDB, ClickHouse and Redis are often
reachable only from a bastion. The SSH source already signs in, pins the
server key a person confirmed (D145) and keeps keys apart from connections
with their passphrases (D146, D147), so a tunnel reuses that connection rather
than asking for SSH fields a second time.

Rejected: SSH fields inside every database form, the way DBeaver has them.
The bastion is then typed once per database, its pinned key is pinned once
per database, and replacing a key or a host is as many edits as there are
databases. A reference is one choice, and the SSH connection stays the one
place that says how that server is reached.

### What the options hold

Every source with an address declares `ssh_tunnel`: the id of an SSH
connection, or empty for directly. Text rather than `UUID | None`, because an
empty choice is what a form sends, and a pattern refuses anything that is not
an id. The field says what it is for (`x-ui-purpose: ssh-connection`), so the
form offers the person's own SSH connections and the store finds which
databases go through one without a list, the way key references are found.

The host and port stay the database's, as the SSH server sees it. The
connection string, the copy's "same server" and every sentence name that
address; a database that goes through a tunnel adds the tunnel to what it is
called internally, because `db:5432` seen from a bastion is not `db:5432` seen
from here.

### How a driver reaches it

`AdapterContext.tunnels` is handed to every source, like `keys`. A driver asks
it for the address to dial before every connection it makes, and gets either
the address itself or a port on loopback. It never holds an SSH session, and
`asyncssh` stays in its adapter.

Behind it, the SSH adapter keeps one forwarder per SSH server, account and
target: a listener on `127.0.0.1` whose every connection becomes a
`direct-tcpip` channel of one signed-in session. Signing in, and one channel
opened and closed, happen when the address is asked for, so a refused key, a
server with `AllowTcpForwarding no` or a target the server cannot reach is
said there rather than as a database that hung up. A dropped session is
signed into again by the next connection, on the same port, so a pool built
on that port keeps working. A forwarder nothing has used for ten minutes
closes.

The forwarders are a module of the SSH adapter, as the keyring is: the health
monitor, the metrics collector and the search-keeper build sources with no
resource store, and a forwarded port must outlive the pool that dials it. Each
is bound to the event loop that made it.

### Whose tunnel

Always the owner's. A grantee reading the database goes through the owner's
SSH connection without being able to open that connection or see its files,
as a grantee signs in with the owner's key (D146). The SSH connection must be
the owner's, switched on and an SSH connection; anything else is refused in a
sentence. An SSH connection a database goes through is not deleted, and the
refusal names the databases.

### What does not go through

A backup runs its program in a container of its own, which cannot reach a
port on this process's loopback, so a database behind a tunnel says a backup
does not go through one yet. ClickHouse over HTTPS is refused through a
tunnel: the certificate names the server, never a port on loopback, and the
tunnel encrypts the connection already. A tunnel does not go through another.
