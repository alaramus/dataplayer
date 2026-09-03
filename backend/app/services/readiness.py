"""Waiting until a started service can actually be used.

A container that is running is not a database that is ready: PostgreSQL
initialises its data directory on first start, and the port answers before the
server does. The old application waited by calling the adapter's own
`check_connection` up to thirty times, which was the right idea inside the
wrong machinery — so the idea is kept and the machinery is a job (D83).

Asking the source itself rather than the runtime is the point: "ready" means
"this connector works", and the only thing that can say so is the thing that
will be used.
"""

import asyncio
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from app.adapters import registry
from app.adapters.registry import AdapterContext
from app.connectors.service import build_adapter

logger = logging.getLogger(__name__)

# How often to ask. Short enough that a database ready in three seconds is not
# waited on for ten, long enough that a minute of waiting is sixty attempts
# rather than six hundred.
INTERVAL_SECONDS = 1.0


@runtime_checkable
class ReadinessProbe(Protocol):
    """Whether the source at these options answers, within a time.

    A protocol so that a job can be exercised without a database of its own to
    wait for — the same reason the engine is one. There is one implementation
    and it is below; a test supplies its own.
    """

    async def __call__(
        self,
        adapter_type: str,
        options: Mapping[str, Any],
        *,
        home_dir: Path,
        timeout_seconds: int,
    ) -> bool: ...


async def wait_until_ready(
    adapter_type: str,
    options: Mapping[str, Any],
    *,
    home_dir: Path,
    timeout_seconds: int,
) -> bool:
    """Ask the source whether it works, until it does or time runs out.

    No pooling: this is a series of one-off connections to something that is
    not ready yet, and a pool would keep the failures.
    """
    kind = registry.get(adapter_type)
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    attempts = 0
    while True:
        attempts += 1
        adapter = build_adapter(
            kind, dict(options), AdapterContext(home_dir=home_dir)
        )
        result = await adapter.check_connection()
        if result.ok:
            logger.info("Service answered after %d attempts", attempts)
            return True
        if asyncio.get_running_loop().time() >= deadline:
            logger.info("Service did not answer within %ds", timeout_seconds)
            return False
        await asyncio.sleep(INTERVAL_SECONDS)
