"""A Redis server, so far only as something to reach.

The one capability is the connection check, and that is the whole of it (D85).
`DataAdapter` asks for nothing else; everything a source can additionally do —
browsing, reading rows, acting — is a protocol it may implement, and this one
implements none, so the catalog says in the user's own screen that this type
"only checks that it can reach the source".

That is not a stub: it is what a source type is worth while the phase that
introduced it is about running services rather than about reading key spaces.
What Redis holds becomes readable when a phase says so, and the shape of that
is a catalog and a fetch, not an edit here.

`redis` is imported by this package and by nothing else, the rule `psycopg`
already follows: a driver upgrade has one place to change.
"""

import time
from typing import Any

import redis.asyncio as redis
from redis.exceptions import (
    AuthenticationError,
    RedisError,
)
from redis.exceptions import (
    ConnectionError as RedisConnectionError,
)
from redis.exceptions import (
    TimeoutError as RedisTimeoutError,
)

from app.adapters.protocol import ConnectionCheckResult, ErrorKind
from app.adapters.redis.options import RedisOptions, RedisPassword
from app.adapters.registry import AdapterContext, register

# What a check may cost. A server that has not answered in this long is one
# somebody is waiting on a page for.
CHECK_TIMEOUT_SECONDS = 5.0


class RedisAdapter:
    """Everything this application can currently do with a Redis server."""

    def __init__(self, options: Any) -> None:
        self._options = options

    def _client(self) -> redis.Redis:
        password = (
            self._options.password.get_secret_value()
            if isinstance(self._options, RedisPassword)
            else None
        )
        return redis.Redis(
            host=self._options.host,
            port=self._options.port,
            db=self._options.database,
            password=password,
            socket_connect_timeout=CHECK_TIMEOUT_SECONDS,
            socket_timeout=CHECK_TIMEOUT_SECONDS,
        )

    async def check_connection(self) -> ConnectionCheckResult:
        """Say hello, and say what happened in words that name no address.

        A driver's own message carries the host, the port and sometimes the
        password of the connection it failed on — the same reason PostgreSQL's
        errors are reduced rather than passed on.
        """
        client = self._client()
        started = time.perf_counter()
        try:
            await client.ping()
        except AuthenticationError:
            return _refused("auth", "Authentication failed")
        except RedisTimeoutError:
            return _refused("timeout", "Connection timed out")
        except RedisConnectionError:
            return _refused("network", "Could not reach the Redis server")
        except RedisError:
            return _refused("unknown", "The Redis server refused the connection")
        finally:
            await client.aclose()
        elapsed = int((time.perf_counter() - started) * 1000)
        return ConnectionCheckResult(
            ok=True, message="Connection successful", latency_ms=elapsed
        )


def _refused(kind: ErrorKind, message: str) -> ConnectionCheckResult:
    return ConnectionCheckResult(ok=False, message=message, error_kind=kind)


@register(
    name="redis",
    title="Redis",
    # Not a SQL database and not a file store: no statements, no relations and
    # no schema — a key space with an expiry clock. It sat under "SQL
    # Databases" for one commit because that was the only group there was.
    category="keyvalue",
    description=(
        "An in-memory key-value server. This application can reach one and "
        "start one of its own; reading what is in it comes later."
    ),
    options_schema=RedisOptions,
    adapter_class=RedisAdapter,
)
def _build(options: Any, _context: AdapterContext) -> RedisAdapter:
    # No home directory and no pooling: this source opens a connection to
    # say hello and closes it again.
    return RedisAdapter(options)
