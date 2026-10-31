# ZooKeeper

What a ZooKeeper source is, how it reaches the server, what its catalog shows
of the znode tree, and how a znode's data, stat, ACL and children are read and
its data written. The contract every source type follows is in
[contract.md](contract.md). Read this before changing the `zookeeper` adapter.

Decisions here: D297, D298.

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
