# Selecting and observing the cache backend

## Problem

An optional backend is not optional if importing the application requires its
server, or if losing it fails readiness. Operators also need to know whether a
multi-worker deployment is sharing cache state without exposing the URL or its
credentials.

Configuration must distinguish the user-configured Redis source from the Redis
service DataPlayer may use internally.

## Selection

`DATA_CACHE_BACKEND` is a closed choice of `memory` or `redis` and defaults to
`memory`. The Redis choice requires:

- `DATA_CACHE_REDIS_URL`, held as `SecretStr`, with `redis://` or `rediss://`;
- `DATA_CACHE_DEPLOYMENT`, a bounded plain namespace;
- `DATA_CACHE_SECRET_KEY`, a cache-only urlsafe-base64 AES-256 key;
- a bounded command timeout.

The lifespan selects one implementation, starts its invalidation listener and
closes it. A Redis object is not made at import time and the memory backend
needs none of the Redis settings.

## Health

The ordinary health check continues to answer application readiness. A separate
anonymous `GET /utils/cache-health/` returns the backend name, whether it is
shared, `healthy` or `degraded`, and a fixed safe message. It never returns a
URL, exception or credential.

A Redis probe failure returns HTTP 200 with `degraded`. Data access has already
fallen back to direct reads, so marking the application unready would restart
healthy workers and magnify an optional-cache outage.

## Deployment examples

The Compose service uses authentication, has no published port and no volume.
Cache data is disposable. Its password and the backend URL are explicit
environment values so deployments can replace them.

It started behind a `shared-cache` profile, so that nothing ran unless a
deployment asked for it. That was reversed on 2026-09-05: the service now
starts with the stack and the backend waits for it to answer, and
`.env.example` selects the Redis backend. A cache nobody switches on is a cache
nobody exercises, and the first thing it must survive is ordinary daily use.
The code default is still `memory`, so removing the service is one line rather
than a server that will not start.

The local example is `redis://` on the private Compose network. The environment
example also shows `rediss://` with an ACL username for an externally managed
service. Production certificate trust follows the system trust store used by
redis-py; accepting arbitrary certificate text or disabling verification is
not offered.

## Rejected alternatives

- Auto-selecting Redis when a host resolves makes deployment topology change
  application behaviour without configuration.
- Putting infrastructure Redis in connector records would give end users
  control over a server-owned dependency.
- Folding cache state into readiness turns a performance failure into a restart
  loop.
- Persisting the Compose cache creates retention and backup obligations for
  data whose source TTL already says when it expires.
