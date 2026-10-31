# A ZooKeeper started here, and what is left out

Decision D302. The fifth slice of the ZooKeeper source. It was planned, as for
the database sources, as copying, backups, a service template, a lab and the
guide in every language.

## What ZooKeeper does not have

Asked whether ZooKeeper can be backed up or copied at all, the answer was:

- no command or API copies a subtree from one ensemble to another. Tools that
  do it (zkcopy, zk-shell's `cp`) walk the tree with the client API and make
  every znode again, losing versions, zxids and times, turning a sequential
  name into a plain one and leaving ephemeral znodes behind; nor is it a
  snapshot of one moment, since the tree changes while it is walked;
- its backup is the snapshot and transaction-log files in `dataDir` on the
  server, or the AdminServer's `snapshot` command since 3.8 on a port of its
  own with admin credentials. Neither is reachable through the connection; a
  client can only write the tree out as a file, which is the same walk.

The user chose to leave both out: a walk called a copy or a backup would
promise what ZooKeeper does not give.

## The template

The image the source is tested against, so its zkCli is the terminal's (D299).
No credential: a password field would set nothing ZooKeeper reads. A server
with no password is safe here for the reason an unprotected Redis is: its
port is on the loopback only (D86).

Its whitelist allows the words the reports and metrics read and nothing that
lists every session or resets the counters.

## The lab

Written out rather than generated, as Redis's is, so two demonstrations look
the same: the shapes an application leaves in ZooKeeper, each of which
exercises a part of the source — JSON opens as a tree, sequential names, bytes
shown as hex, and one branch only a digest user reads, with its password in
the guide so signing in can be tried.
