# Redis system reports

## D265. The Redis catalog leads with a bounded, read-only view of the server

Redis has no catalog node that describes the server itself. Add a `System`
section before its databases, with two reports that use the existing report
and table contracts. The tree still opens at the connection's preferred
database, while drawing root-level report sections above that database's key
space so the server reports remain visible in the rooted view:

- `Server` reads selected fields from `INFO` sections covering version, uptime,
  clients, memory, persistence, replication and counters. Refresh it every ten
  seconds.
- `Settings` reads a fixed list of non-secret values with `CONFIG GET`.
  Credentials, ACL entries and local configuration paths are excluded by
  construction rather than fetched and hidden later.

Rows use the normal bounded page, filtering and sorting behavior. Both reports
can be exported as CSV. The reports are read-only and server-wide, independent
of the selected Redis database. If a Redis user cannot run one of the read
commands, show a small unavailable row instead of withholding the other
report.

The allowlists make the report's scope explicit and avoid treating arbitrary
server configuration as safe to show. This adds inspection without adding a
Redis command console or a route for changing server configuration.
