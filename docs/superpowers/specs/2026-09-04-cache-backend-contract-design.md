# A replaceable read-cache backend

## Problem

D31 put cache calls behind one `DataCache`, but made that name the concrete
process-local implementation. Optional shared storage would therefore require
application routes and background runners to know which backend was selected,
or would duplicate the cache contract beside the original class.

The storage choice must not weaken the behaviour already relied on by reads and
mutations. In particular, a slow read begun before a successful mutation must
not restore its stale answer afterwards.

## Boundary

`DataCache` is a runtime-checkable protocol exposing the complete
`get_or_load`, connector invalidation, size and lifecycle operations.
`MemoryDataCache` implements it and remains the application default.

The boundary is the complete cache operation, not a key/value store. Exact
keys, source-owned TTL, refresh, in-flight coalescing and invalidation are one
semantic unit. A backend that only offered `get` and `set` would move the
load/invalidation race into every caller and let implementations disagree.

The key remains D31's owner UUID, connector UUID, cache area and exact
normalized request. Nothing is removed or combined to suit a backend.

## Compatibility

The process-local algorithm and its tests move under the new implementation
name without changing behaviour. Routes, query execution and service cleanup
accept the protocol, so a later backend can be selected once at application
assembly. A dependency rejects an object that does not implement the protocol.

## Rejected alternatives

- A union of concrete cache classes makes every consumer know the available
  implementations and grows whenever another one is added.
- A raw storage protocol is too low-level to preserve coalescing and the stale
  reinsertion guard as a single contract.
- Making Redis the default would turn an optional performance dependency into
  a correctness dependency before failure behaviour exists.
