# A ZooKeeper source

Decisions D297 and D298. The first slice of a ZooKeeper source type: a
connection, the znode tree, a znode's data read and written, its stat and ACL,
and its children as rows. zkCli in a terminal, creating and deleting znodes and
editing an ACL, reports and metrics from the four-letter words, search,
export, copying a subtree, a backup, a service template and live watches
follow in later slices, each in its own commit, on the branch
`zookeeper-adapter`.

ZooKeeper is the second source that is neither SQL nor a tree of files, after
Redis: a tree of small values, each with a version, an ACL and children of its
own.

## What the user chose

Asked before the work began:

- Opening a znode: its data by default, JSON as a tree and text as text, with
  its stat and ACL beside it, and its children as rows as a second view.
- Writing in the first version: create, set data against the version read,
  delete, a recursive delete with a preview, and ACL editing. The data editor
  arrives with this slice because the text view is the editor; the rest come
  in the third.
- The console: zkCli.sh in a terminal (D286), and the four-letter words as
  reports and metrics. No query console reading zkCli's syntax.
- Watches: later, as a slice of their own.

## The client (D297)

Three ways were weighed:

- aiozk, an asynchronous client — rejected: little maintained, and its last
  releases trail the server's;
- the protocol by hand — rejected: a session is a handshake, pings and a
  reconnect policy, which is a client to maintain;
- kazoo — chosen. The client every Python tool around ZooKeeper uses. It is
  synchronous, which the thread pool answers, and it can ask many things at
  once with its asynchronous calls inside one operation.

A session per operation, as Redis has a connection per operation. A session
kept open would need a lifetime in the resource store, a reconnect when the
server drops it, and would sit on the server as a live session that nobody is
using; listing a level is two waits whichever way it is done.

One server, not an ensemble: a list of servers is something a tunnel (D282)
cannot carry, and the server named answers for the ensemble anyway. The root
path is kazoo's chroot rather than a starting point, because ZooKeeper itself
treats it as a confinement.

## The znode as a kind (D298)

A znode was not made a `key`: a key has a Redis data type and no children. Nor
a `directory`: a directory is not opened. It is opened and walked into, which
the catalog already knows from a workbook, so a kind of its own carries its
stat, and the tree learned to expand a leaf that holds nodes.

The data is offered as text always and as a JSON tree when the listing can tell
it is JSON. Telling needs the data, so the listing reads it for children of 4
KB or less, all at once; reading every child's data whatever its size could
be a megabyte per child. A larger JSON value opens as text, highlighted and
validated as JSON by the editor.

The version an editor holds names the znode as well as the write: ZooKeeper
starts a re-created znode at version 0, so the data version alone would let a
stale editor overwrite a znode that is not the one it read.

ZooKeeper 3.9 refuses a stat without READ. A level does not fail for one
unreadable child; that child is listed by name with nothing to open, because
leaving it out would hide that it exists, and a person reading the tree as
another user would see a different tree with no reason given.
