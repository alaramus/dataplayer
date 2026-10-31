# ZooKeeper

A ZooKeeper server. You walk its znode tree, read a znode's data with its stat
and ACL, edit the data, and page through a znode's children as rows. How
connections work in general is on the [Connections](connections.md) page.

## What you can see

- The znode tree, expanded where you stand
- A znode's data: JSON as a tree, text as text, anything else as hex
- A znode's stat: versions, zxids, children, the session of an ephemeral one
- A znode's ACL: who may read, write, create, delete and administer it
- A znode's children as rows, a page at a time
- zkCli, connected to the server and root path, in a terminal

## What you can change

- A znode's data, written whole against the version you read
- Anything zkCli can change, typed into its terminal

## Connecting

The **Connection** page of the window asks for:

- **Host** and **Port** of one server of the ensemble, 2181 unless it listens
  elsewhere;
- **Root path**: everything is read under this path as if it were the top, and
  nothing above it can be reached. Leave it empty for the whole tree;
- **TLS**: an encrypted connection, with the server's certificate checked;
- **Authentication**: **Anonymous**, or a **Digest** user and password, added
  to the session as it opens.

A connect string such as `zk.example.com:2181/apps/billing` pasted into
**URL** fills these fields. A list of servers is not supported: name one.

## The catalog

- The tree opens at the top, or at the root path. A znode with children has an
  arrow; clicking its name opens it.
- Each znode says how much data it holds and how many children it has, and
  whether it is ephemeral.
- `/zookeeper` belongs to the server and is marked as such.
- A level shows its first thousand children by name. The children table of
  the znode above pages through all of them.
- A znode this connection may not read is listed by name and marked **no
  access**. ZooKeeper asks for read permission even to say how big it is.

## A znode's data

- JSON data up to 4 KB opens as a tree; it can also be opened as text.
- Other data opens as text in an editor. Save writes the whole of it.
- Save writes only if nobody changed the znode since you opened it, and only
  if it is still the same znode rather than one deleted and made again. If it
  changed, reload it and make your change again.
- JSON stays JSON: a save that does not parse is refused.
- Data that is not UTF-8 text is shown as a hex dump and is not edited here.

## Children as rows

- One row per child: its name, the start of its data, its size, version,
  number of children, when it was changed and created, and the session of an
  ephemeral one.
- The rows are in the order of their names. They cannot be sorted or filtered:
  ZooKeeper keeps no index to do it with.
- Data larger than 4 KB is not read for the table, and its cell is empty; open
  the znode to read it.

## The details panel

Select a znode in the tree and choose **Details** in the catalog's menu.

- The znode's stat: data, child and ACL versions, the zxids of its creation,
  last change and last change of its children, and its number of children.
- The session an ephemeral znode belongs to.
- One line per entry of its ACL: the scheme, the id, and what it may do.

## zkCli

**Terminal** on a ZooKeeper connection opens `zkCli`, the client that comes
with ZooKeeper, connected to the server and the root path of the connection.
It runs in a container the server starts, so the server must be allowed to
run containers, and it does not go through an SSH tunnel.

zkCli cannot be given a digest password when it starts: it only takes one
typed as a command. On a connection with a **Digest** user the terminal opens
connected but not signed in, and the first line says so. Type
`addauth digest user:password` to read and change znodes whose ACL needs that
user. The password is not filled in for you and is never shown by DataPlayer.

## What ZooKeeper does not have here yet

- Creating and deleting znodes and changing an ACL
- The server's reports and metrics
- Watching a znode for changes: refresh by hand
