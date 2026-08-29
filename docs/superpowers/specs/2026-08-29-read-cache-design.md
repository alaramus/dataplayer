# Кеш чтения catalog и fetch

## Problem

Catalog and fetch calls may be expensive or rate limited. Vue Query prevents
some duplicate calls inside one browser, but a second browser, a second tab
after eviction, or concurrent server requests still reach the source. Caching
inside every adapter would duplicate concurrency, bounds and invalidation
logic, while caching every adapter unconditionally would invent freshness
semantics for sources that have not declared them.

## Boundary

The application owns one process-local `DataCache`. An adapter opts in and
returns a TTL for `catalog` and `fetch`; zero or absence means bypass. Cache keys
contain owner id, connector id, operation and the exact request. Fetch uses the
Pydantic model's canonical JSON representation, including node, page, filters
and ordered sort. Catalog uses the opaque node id.

The first implementation caches PostgreSQL catalog levels for 30 seconds and
fetch pages for 10 seconds. File reads remain uncached because filesystem
freshness and change observation have not been designed.

## Concurrency and bounds

There is one in-flight task for an exact key. Later callers await it instead of
opening another upstream request. Exceptions propagate to every waiter and are
not retained. Completed entries expire by monotonic time and the least recently
used entry is evicted above a hard count ceiling. The lifecycle cancels remaining
loads and clears entries at shutdown.

## Invalidation

A successful operation that may change source data invalidates the complete
connector: cell update, row insert/delete, column DDL and adapter actions. A
connector update or deletion does the same. Broad connector invalidation is
intentional: optional adapter actions describe which catalog branch the client
should reload, but they do not yet declare every cached projection they affect.

Each connector has an invalidation generation. A load records the generation
it began under and stores its answer only if that generation is still current.
This closes the race where a slow SELECT begins, a write succeeds and clears
the cache, then the older SELECT finishes and restores stale rows.

## Explicit freshness

Ordinary reads may use the cache. `refresh=true` bypasses a completed entry but
still joins an already-running fresh read for the same key. The tab Reload
gesture sends this flag for fetch and every catalog level it explicitly
rebuilds. Page download bypasses the cache entirely because its existing
contract is a fresh bounded copy.

The response model stays the adapter response. `X-Data-Cache` exposes the
server decision for diagnostics without making every source model carry
transport metadata.

## Rejected alternatives

- A module-global dictionary has no owned shutdown and is difficult to replace
  in tests.
- Redis first adds deployment and serialization work before process-local
  behavior is measured.
- TTL without an entry bound does not bound memory.
- Invalidation without generations allows an older in-flight read to undo it.
- Returning stale data while refreshing in the background makes Reload unable
  to promise a source read and complicates row-handle conflicts.
