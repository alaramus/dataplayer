# Batching relation descriptions

## Context

The relationship graph requests a full relation model for every selected node.
One hundred nodes can therefore create one hundred HTTP requests. PostgreSQL's
private relation reader already groups catalog reads by schema, but the graph
does not use it. Repeated reads also duplicate complete descriptions already
held by another view in the browser.

## Decision

D246 adds a bounded batch endpoint for selected relation descriptions.

- The request contains 1–100 unique opaque node ids. The response carries
  successful models and per-node failures, so an unreadable relation remains a
  placeholder while other cards load.
- A source may implement a batch capability. PostgreSQL does so by grouping ids
  by schema and reading the selected relations in a single repeatable-read,
  read-only inspection transaction. The connection-local statement timeout is
  five seconds. A source without the capability retains at most four concurrent
  single reads, and so does a batch that ran out of its five seconds: one
  snapshot for a hundred relations on a busy server can time out where each
  relation on its own would not.
- MySQL and MariaDB implement the capability too: five statements per
  database on one connection, each a UNION ALL of one equality branch per
  relation. `TABLE_NAME IN (...)` was rejected after EXPLAIN on MariaDB 11.4:
  equality is a direct look-up ("Scanned 0 databases"), a list opens the frm
  of every table in the database ("Scanned 1 database"). MySQL 8 reads either
  through its data dictionary's indexes. Each branch answers with the name it
  was asked by, so an answer from a server that compares names without case
  still finds its relation.
- The single and batch routes use the source-owned relation cache area.
  PostgreSQL and MySQL keep descriptions for five minutes. Owners cannot stretch that
  window through the row/catalog cache setting. DataPlayer mutations invalidate
  all entries for the connector. Incomplete batches are returned but not
  cached; an external DDL change is read after server-cache expiry on the next
  source request, or immediately by an explicit Reload.
- The graph seeds each returned model into TanStack's per-relation query key.
  Structure and record views in the same browser reuse it. Row pages remain in
  the fetch cache area.

## Consequences

The graph uses one request for the selected set, and PostgreSQL does not inspect
unselected relations. Repeated identical batches can use the server cache, and
overlapping batches can reuse individual models in the browser. The server does
not merge overlapping batch entries or prewarm a schema on connection startup.
For other sources, batching reduces HTTP overhead while retaining the previous
four-read concurrency bound.

## Freshness

Source-owned caching is bounded by TTL and connector-wide invalidation. Explicit
Reload sends refresh=true; a complete answer replaces the cached one. No
stale-while-revalidate response is introduced, because relation structure
controls actions that can change a source and a caller must know which model it
is acting on.
