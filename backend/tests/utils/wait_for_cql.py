"""Wait until Cassandra and ScyllaDB accept a sign-in, for CI before pytest.

Connects through the adapter's own `make_cluster`. A plain `Cluster` follows
the address a server reports for itself, its container's, where nothing
listens on the published port, and never succeeds: CI waited out every attempt
for ten minutes on every run that way.
"""

import sys
import time

from app.adapters.cassandra.options import CassandraUserPassword
from app.adapters.cassandra.session import make_cluster, options_from_url
from tests.utils.services import CASSANDRA, SCYLLA

DEADLINE_SECONDS = 600
PAUSE_SECONDS = 5


def _signs_in(url: str) -> str | None:
    """None once a sign-in succeeds, else the reason it did not."""
    options = CassandraUserPassword(**options_from_url(url))
    try:
        cluster = make_cluster(options, (options.host, options.port))
        cluster.connect()
        cluster.shutdown()
    except Exception as exc:  # noqa: BLE001 - any failure means "not yet"
        return f"{type(exc).__name__}: {exc}"
    return None


def main() -> int:
    started = time.monotonic()
    for server in (CASSANDRA, SCYLLA):
        while (reason := _signs_in(server.url())) is not None:
            if time.monotonic() - started > DEADLINE_SECONDS:
                sys.stderr.write(f"{server.name} did not answer: {reason}\n")
                return 1
            time.sleep(PAUSE_SECONDS)
        elapsed = time.monotonic() - started
        sys.stdout.write(f"{server.name} ready after {elapsed:.0f}s\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
