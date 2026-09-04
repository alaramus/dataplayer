# An optional shared Redis cache

## Problem

The memory backend is correct for one worker. With several workers, each keeps
its own completed values and in-flight reads; a mutation in one cannot promptly
invalidate the others. Shared storage solves reuse only if invalidation and the
slow-read race cross the same boundary.

Redis is optional infrastructure. Losing it must not turn an otherwise
reachable source into an outage.

## Shared entries and local flights

`RedisDataCache` stores D101's encrypted values in Redis. In-flight tasks stay
inside a worker: until a source call finishes there is no value to transfer,
and turning a source read into a distributed job would give cache misses a new
durable state machine they do not need.

Before choosing an entry or flight, a worker reads the connector generation.
That generation is part of the value and flight key. Invalidation increments
it. A loader re-reads it before writing, so a call begun under an older
generation may answer its existing caller but cannot publish stale data.

Old-generation values expire under the source TTL. Invalidation does not scan
and delete an unbounded namespace.

## Invalidation channel

After incrementing the generation, a worker publishes the connector UUID on a
deployment-scoped Redis channel. Subscribers forget their local flights for
that connector. The generation remains authoritative: Pub/Sub has no replay,
so a worker reconnecting after a missed message still selects only current
entries and flights.

## Failure

Every cache command translates Redis failures to one internal error without a
driver message, because that message may contain the authenticated URL. Reads
catch it and execute the source loader directly with cache status `bypass`.
Invalidation catches it after the source mutation has already succeeded. A
corrupt, wrongly keyed or unknown cache value is deleted when possible and
treated as a miss.

There is no completed local fallback behind Redis. Such a fallback would keep
serving values another worker can no longer invalidate during an outage. Direct
reads preserve correctness and make Redis loss a performance event.

## Evidence

The backend test creates two independent cache instances over one shared Redis
model. It proves that the second reads the first's encrypted value, observes a
generation increment and channel publication, and cannot let a pre-mutation
flight restore stale data. A failure test proves that both reads and
invalidation return without surfacing a cache outage.

## Rejected alternatives

- Pub/Sub alone loses invalidations while a worker is disconnected.
- Deleting by pattern makes mutation latency proportional to cache contents.
- A distributed lock around misses adds availability coupling; duplicate
  upstream reads across workers are acceptable, stale reinsertion is not.
- A local completed-value fallback cannot receive reliable invalidation while
  Redis is unavailable.
