# The ZooKeeper console

Decision D299. The second slice of the ZooKeeper source: zkCli in a terminal,
as mongosh, redis-cli and psql are (D286). The user chose the real zkCli over a
query console reading its syntax when the source was planned.

## Signing in

mongosh, redis-cli and psql each read a password from their environment or an
address they are given. zkCli does not: the digest scheme is an `addauth`
typed into its prompt. `ZooKeeperMain` was read in the 3.9 image for another
way in — a property, an environment variable, a startup file — and there is
none; `-client-configuration` reaches SASL, which is a different scheme from
the digest ACLs the connection signs in with.

Three ways were put to the user:

- open zkCli anonymous, with a line above it saying how to sign in — chosen;
- type `addauth` for the user from a wrapper around zkCli (`stty raw`,
  `script`, and a filter cutting the password from what is echoed) —
  rejected: the password would show if the filter missed it across two reads,
  and the wrapper keeps a resize from reaching zkCli;
- give a digest connection no terminal — rejected: an anonymous zkCli still
  reads every znode whose ACL is open, and `addauth` is one line.

The address goes through the environment rather than into the script, so a
host or root path can never be read by the shell as syntax.
