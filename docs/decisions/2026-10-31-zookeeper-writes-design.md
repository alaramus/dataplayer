# Making, deleting and re-ACLing znodes

Decision D300. The third slice of the ZooKeeper source. The user asked for full
writes in the first version: create, set data against the version read, delete,
a recursive delete with a preview, and ACL editing. Setting data came with the
editor in the first slice (D298); this is the rest.

## Where the actions are offered

The catalog's menu draws what the level offers and switches those that act on
a node by the kinds selected. A ZooKeeper tree's level is always its top, since
a znode opens rather than being a place (D298). So the adapter offers every
action everywhere, and making a znode is two actions: at the top, acting on the
level, and inside the selected one, acting on the node. One action with a
parent field was rejected: the form would ask for a path the selection
already says.

## Sequential, not ephemeral

A select of three kinds was rejected for a toggle: an ephemeral znode belongs
to the session that made it, and this source closes its session when the
request ends (D297), so it would vanish at once. The form's choices are drawn
as codes, not words, which a toggle avoids too.

## Deleting a subtree

kazoo's recursive delete is a loop of deletes with no preview. The subtree is
walked here instead, so the preview can name what will go and the delete
refuses where it could not see everything: a child that cannot be listed would
otherwise be found only half way through. Ten thousand znodes is the ceiling,
past which zkCli's `deleteall` is pointed at; a form is not a bulk tool.

## The ACL as text

zkCli's `scheme:id:perms` per line, because it is what people already write and
read in `getAcl`, and it round-trips. A table of entries with a checkbox per
permission was rejected for now: it is a screen of its own, while text fits the
action form every source uses.

To open the form with the ACL a znode has, field hints gained `values`: what a
node already holds in a field. The dialog fills a field from it only while
nothing has been typed there. Choices and integers, the hints there were, could
not say it.

Losing admin is warned about rather than refused. ZooKeeper checks the ACL a
znode has when it is changed, so a connection that gives admin away cannot
take it back; but an `ip` entry may well be this server, which only the server
knows.
