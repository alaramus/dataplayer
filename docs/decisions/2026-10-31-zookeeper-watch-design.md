# Watching what a ZooKeeper screen shows

Decision D303. The sixth slice of the ZooKeeper source: the user asked for what
is on screen to follow changes made elsewhere.

ZooKeeper's watch is a one-shot notice on one znode, set on a session. A
persistent recursive watch on the whole tree would be one request, but kazoo
2.11 has no call for it, so the screen names what it shows and only that is
watched. Topics carry no parameters (D18), so the screen says it over HTTP and
renews it; the topic tells, per person as health does (D19).

A session is held open for the watch, against D297's session per operation,
because a watch dies with its session. It reconnects by itself, and kazoo's
recipes set their watches again after a reconnect.
