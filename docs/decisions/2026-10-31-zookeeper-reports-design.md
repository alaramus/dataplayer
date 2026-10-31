# ZooKeeper's reports, metrics, search and export

Decision D301. The fourth slice of the ZooKeeper source. The user chose, when
the source was planned, to have the four-letter words as reports and metrics
rather than a query console.

## Reports from four-letter words

ZooKeeper says what it is through words sent on the client port: `srvr`, `mntr`,
`cons`, `wchs`, `conf` and more. kazoo sends one on the connection the session
already has, so no second address or port is needed and a tunnel (D282) carries
it like everything else. The AdminServer's HTTP interface says the same things
as JSON, but on another port the connection does not know, so it was not used.

Each answer is read into setting-and-value rows, the shape Redis's and
MySQL's reports already have, so the grid, its filters, the download and the
chart need nothing new. `cons` is a line per client; its address is the
setting and the rest of the line the value. `wchc`, `wchp` and `dump` list
every watch or session and can be very large on a busy ensemble, so they are
left to zkCli.

A server answers only the words its whitelist allows, and since 3.5 that is
`srvr` alone. Refusing the whole report would hide which word is missing; one
row naming it and the setting to change says what to do.

## Metrics

`mntr` is what monitoring tools read, so it is what is polled: a dozen of its
counters, the packets as counters whose rate is drawn.

## Search by walking

ZooKeeper has no index over names. A search lists levels until its ceiling or
its clock, and keeps the best-classed matches it met, as Redis's scan does. A
level that may not be listed is passed over rather than failing the search,
and the answer says it may be incomplete. Paths are their own ancestors, so a
found znode is placed in the tree without asking anything more.

## Export

The children are read for export a page at a time, a session per page, so an
export of a large level does not hold one session for its whole length.
