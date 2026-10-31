# ZooKeeper

What a ZooKeeper source is, how it reaches the server, what its catalog shows
of the znode tree, and how a znode's data, stat, ACL and children are read and
its data written, znodes made and deleted and their ACLs changed (D300), the server's reports
and metrics, finding znodes and exporting children (D301), a server started here with a
lab (D302), and zkCli in a terminal (D299, run as D286 says in
[terminals.md](../terminals.md)). The contract every source type follows is in
[contract.md](contract.md). Read this before changing the `zookeeper` adapter.

Decisions here: D297, D298, D299, D300, D301, D302.

## D297. A ZooKeeper source speaks to one server through kazoo, a session per operation

The adapter uses kazoo, ZooKeeper's Python client. kazoo is synchronous and
runs threads of its own, so one operation — open a session, do the work, close
it — is one call into the thread pool; the work inside may ask many things at
once through kazoo's asynchronous calls. No session is kept between
operations: a kept session is a lifetime on the server for nobody, and a
znode is a handful of round trips. kazoo is imported by
`app.adapters.zookeeper` and nothing else, which an import-linter contract
holds. A failure is reduced by kazoo's exception class, never by its text: a
missing znode is a 404, a changed version a conflict, a refused ACL `auth`.

Options are host, port (2181), a root path, TLS (verified), an SSH tunnel
(D282), and either a digest user and password or an anonymous session. The
root path is kazoo's chroot: every path is read under it as if it were the
top, and nothing above it is reachable. One server is named; the rest of an
ensemble answers through it. A connect string `host:port/root`, with
`zookeeper://` before it allowed, fills the form; a list of servers and a user
in the address are refused. The check opens a session and reads the root, and
says so when the root path is not there.

Known deviations:

- No ensemble list: a connection names one server and does not fail over.
- No SASL or Kerberos, and no client certificate; TLS verifies the server only.
- kazoo tries a refused address three times before giving up, a few seconds
  inside the five-second limit on opening a session.

Spec: [2026-10-31-zookeeper-source-design.md](../../decisions/2026-10-31-zookeeper-source-design.md)

## D298. A znode is a node of its own kind, opened for its data and walked into for its children

A znode is `ZnodeNode`, kind `znode`; its id is its path under the root path,
`/` first, which is ZooKeeper's own name for it. It carries what ZooKeeper
states with every stat — the size of its data, its children, its version,
when it was changed, whether it is ephemeral — and whether this connection may
read it. `/zookeeper` and everything under it is the server's own.

The catalog is a tree expanded in place, as Redis's is (D91). A level is the
first thousand children by name, their stats asked for together; the children
table pages through the rest. ZooKeeper 3.9 asks for READ even for a stat, so
a child this connection may not read is listed by name, marked unreadable,
with nothing to open; the level does not fail for it. A missing level is a
node id the source cannot reach (422), by the catalog's contract.

A znode opens as:

- its data as JSON, read only (`tree`, D295) — first, when the data is an
  object or an array of 4 KB or less, which the listing reads to tell;
- its data as text (`text`), edited whole — first otherwise. Data that is not
  UTF-8 is shown as a hex dump and is not offered for editing. JSON data is
  edited with JSON validation, so a configuration a program reads stays one;
- its children as rows (`table`) — first when it has children and no data.

The editor's version is the creation zxid and the data version together, and a
save writes only while both still hold: a znode deleted and made again counts
its version from zero, and an editor holding version 0 of the old one must not
overwrite the new one. A stale save is a conflict (409).

The children table is name, a preview of the data (the first 200 characters of
data of 4 KB or less; `0x` and hex where it is not text; nothing where it was
not read), its size, version, children, when it was changed and made, and the
session an ephemeral one belongs to. It is in the order of names and nothing
else: ZooKeeper has no index over data or stats, so no column sorts or filters.

The summary is the stat — versions, zxids in hex, children, the ephemeral
owner — and the ACL, one line per entry: scheme, id and the permissions named.
A tree catalog offers Details for the selected node when the source says it
describes it, which for ZooKeeper is every readable znode.

Data is text when it is UTF-8 without control characters other than a tab and
a line break; bytes 0 to 31 decode as UTF-8, and a counter a program stored is
no less binary for it.

Each view offers the others the node has: the JSON tree a button to the text
and one to the children, the text a button to the children, the children one
to the text.

Known deviations:

- A level past a thousand children shows the first thousand in the tree.
- Nothing is watched: what is shown is what was read, refreshed by hand.

Spec: [2026-10-31-zookeeper-source-design.md](../../decisions/2026-10-31-zookeeper-source-design.md)

## D299. zkCli is the terminal, opened anonymous with a note for a digest connection

A ZooKeeper connection's terminal is `zkCli.sh` from the `zookeeper:3.9`
image, run as D286 runs a client program: on the service network, not through
an SSH tunnel. It connects to the host, port and root path of the connection,
which reach the shell in `ZK_SERVER` and are expanded in double quotes, never
read as shell syntax.

zkCli takes a digest identity only as the interactive `addauth digest`; it has
no environment variable, argument or configuration for one. So a digest
connection's zkCli opens connected and anonymous, with one line above it,
from `ZK_NOTE`, naming the user and saying to type `addauth digest
user:<password>`. The password is in neither the environment nor the
arguments, and is never printed.

Rejected, with the user: typing `addauth` into zkCli from a wrapper around it.
The echo would print the password unless the output were filtered, and the
wrapper would stand between the terminal and zkCli, so a resize would not reach
it. Also rejected: no terminal at all for a digest connection.

Known deviations:

- A digest connection's zkCli is not signed in until `addauth` is typed.
- zkCli runs a JLine prompt of its own; its history lives and dies with the
  container.

Spec: [2026-10-31-zookeeper-console-design.md](../../decisions/2026-10-31-zookeeper-console-design.md)

## D300. Znodes are made, deleted and re-ACLed from the catalog's menu

Five actions, all offered at the tree's level, which is always its top (D298);
the four that act on a znode are switched on by the selection:

- **New znode at the top** and **New znode inside** the selected one: a name
  that is one part of a path, data as UTF-8 text, and whether it is
  sequential — ZooKeeper then adds a ten-digit number to the name and the
  znode made is the one opened. Not ephemeral: one would end with the session
  of the request that made it (D297). The ACL is open; it is changed after.
- **Delete** a znode with no children, any number at once; one with children
  is refused and pointed at the next.
- **Delete with children**, after a preview naming how many znodes and the
  first twenty paths. The subtree is walked first, deepest first, and refused
  past ten thousand znodes, under `/zookeeper`, at the top, and wherever a
  child cannot be listed. A znode made under it meanwhile stops the delete at
  its parent, which says so.
- **Change ACL**: one `scheme:id:permissions` per line, as zkCli writes them,
  permissions from `cdrwa`. The form opens with the ACL the znode has, sent
  as a field hint's `values` — what a node already holds in a field, filled
  in where nothing was typed yet. It may be applied to every znode under the
  one selected, deepest first. The preview lists the new ACL and warns, without
  refusing, when no entry leaves this connection admin: anyone, `auth`, or the
  digest user it signs in as.

Known deviations:

- Deleting a subtree is a znode at a time, not one transaction: a failure
  part way leaves the deeper znodes deleted.
- An ACL is set at whatever version it is; two people changing one at once
  is the last one's.
- A grid of a znode's children is not read again when one of them is made or
  deleted; refresh it.

Spec: [2026-10-31-zookeeper-writes-design.md](../../decisions/2026-10-31-zookeeper-writes-design.md)

## D301. The server's four-letter words are reports and metrics; znodes are found by walking

A **Server** section heads the top of the tree, as Redis's System section does.
Its reports are ZooKeeper's four-letter words sent on the session's own
connection, each answer read as setting-and-value rows: Server (`srvr`),
Monitoring (`mntr`), Connections (`cons`), Watches (`wchs`) and Configuration
(`conf`). The first four are read again every ten seconds. A word the server's
`4lw.commands.whitelist` leaves out answers with one row saying so, since the
others may still be allowed; ZooKeeper 3.5 and later allow only `srvr` unless
told otherwise. Report ids start with `\server`, so they never meet a znode's
path. Reports offer no actions.

Metrics are one `mntr` per poll: connections, outstanding requests, latency,
packets as counters, znodes and ephemeral ones, watches, data size and open
files, with a ready-made dashboard. A server that refuses `mntr` gives no
samples.

Searching by name walks the tree below where it starts, breadth first, a level
at a time, matching each znode's own name by D202's classes and keeping the
best. It is bounded by fifty thousand znodes looked at and by the search's
clock, never by matches. A level this connection may not list is passed over
and the answer says it is not complete. A found znode carries the paths above
it as its ancestors, so the tree shows it in place (D91). The same walk reads
every name for a kept list (D213), the whole tree one scope. A search is always
costly: there is no index to ask.

A znode's children are exported whole, a page of five hundred per session, in
name order; a request to filter or sort is refused, as the grid offers neither.
A report is exported as its rows.

Known deviations:

- The walk runs in the thread pool's own limit rather than under the search's
  limiter.
- A found znode's ancestors are drawn as folders until the tree reads them.

Spec: [2026-10-31-zookeeper-reports-design.md](../../decisions/2026-10-31-zookeeper-reports-design.md)

## D302. A ZooKeeper is started here with no password and a lab; nothing is copied or backed up

The service template runs `zookeeper:3.9` with its data in `/data`. It settles
no credential: ZooKeeper has no password for the server as a whole, access
being each znode's ACL, and its port is published on the loopback only (D86),
as an unprotected Redis's is. It allows the four-letter words the reports and
metrics read (D301) — `srvr`, `mntr`, `cons`, `wchs`, `conf` and `ruok` — and
not `dump`, `wchp` or the resets. Its connection is anonymous.

A server started here is given a lab under `/lab`, made again from nothing each
time: configuration as JSON, a registry of service instances, an election and
a queue of sequential znodes, counters stored as bytes, a lock, and
`/lab/private` with a digest ACL for the user `lab`, password `lab`, which the
guide names.

ZooKeeper offers no copy between ensembles and no backup through its clients:
a copy is a walk that makes every znode again, and a backup is the snapshot
and log files in the server's own data directory, or the AdminServer's
`snapshot` on a port the connection does not know. Neither is offered here;
the user chose to leave them out rather than call a walk either one.

Known deviations:

- No copy of znodes into another connection and no backup or restore, unlike
  the database sources.

Spec: [2026-10-31-zookeeper-service-design.md](../../decisions/2026-10-31-zookeeper-service-design.md)
