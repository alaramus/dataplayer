# Redis stops at measured read caching

## Problem

Once Redis is connected, using it for a lock, a queue or a copied record is
mechanically easy. That convenience is not evidence that a second state system
is needed. Each use has different delivery, recovery and authority semantics,
and a cache outage is intentionally harmless while losing a lock or queued job
may not be.

Phase 5 must therefore leave a way to measure the cache and an enforceable
boundary around what Redis does now.

## Measurement

Each cache backend counts process-lifetime hits, misses, coalesced calls,
explicit refreshes, bypasses, connector invalidations and backend or value
failures. The cache health response exposes the snapshot. `X-Data-Cache` keeps
the outcome on each individual read for request-level telemetry.

Counters are intentionally local and reset on worker restart. They are evidence
for operators to aggregate, not application facts to restore. A future proposal
must name the observed contention, fan-out or latency and the availability
contract it needs; the presence of a Redis URL is not a measurement.

## Scope

No production measurement accompanies this phase, so Redis gains no additional
responsibility:

- no distributed lock or semaphore;
- no job queue, lease, progress record or event replay;
- no share record, access request or authoritative snapshot;
- no acceleration path whose miss changes an answer.

Jobs and shares remain durable PostgreSQL rows. Query run metadata remains
durable there as well, while D64's bounded result bytes keep their existing
process-local lifetime. A read-cache value is always disposable and cannot be
cited as the truth of a durable workflow.

The infrastructure connection protocol exposes only the commands needed for
cache entries, generations, health, counting and invalidation Pub/Sub. An
import-linter contract forbids jobs, queries, services and shares from importing
the Redis cache implementation or its driver boundary. They may keep using the
generic `DataCache` invalidation contract D31 already requires.

## Rejected alternatives

- Redis-backed locks without fencing can let an expired owner keep writing;
  adding `SET NX` is not a lock design.
- Pub/Sub is lossy and cannot become job delivery merely because invalidation
  already uses it.
- Copying shares or job state into Redis creates two authorities and a recovery
  order, neither of which a cache needs.
- Durable global counters would themselves make Redis application state. The
  selected measurements are observational and may be aggregated externally.
