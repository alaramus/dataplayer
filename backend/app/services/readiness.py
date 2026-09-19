"""Waiting until a started service can actually be used.

A container that is running is not a database that is ready: PostgreSQL
initialises its data directory on first start, and the port answers before the
server does. The old application waited by calling the adapter's own
`check_connection` up to thirty times, which was the right idea inside the
wrong machinery — so the idea is kept and the machinery is a job (D83).

Asking the source itself rather than the runtime is the point: "ready" means
"this connector works", and the only thing that can say so is the thing that
will be used. A server that proves itself with a key is asked for that key
first, and trusted by it from then on (D153).
"""

import asyncio
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from app.adapters import registry
from app.adapters.credentials import PinsServerKey
from app.adapters.options import server_key_names
from app.adapters.protocol import AdapterError, SupportsSampleData
from app.adapters.registry import AdapterContext
from app.connectors.service import build_adapter

logger = logging.getLogger(__name__)

# How often to ask. Short enough that a database ready in three seconds is not
# waited on for ten, long enough that a minute of waiting is sixty attempts
# rather than six hundred.
INTERVAL_SECONDS = 1.0


@runtime_checkable
class ReadinessProbe(Protocol):
    """The options the source at these options answered to, within a time.

    None when it did not answer. The options come back rather than a yes
    because answering can settle one of them: the key a server proves itself
    with, which the connector then trusts (D153).

    A protocol so that a job can be exercised without a database of its own to
    wait for — the same reason the engine is one. There is one implementation
    and it is below; a test supplies its own.
    """

    async def __call__(
        self,
        adapter_type: str,
        options: Mapping[str, str | int],
        *,
        home_dir: Path,
        timeout_seconds: int,
    ) -> dict[str, str | int] | None: ...


async def wait_until_ready(
    adapter_type: str,
    options: Mapping[str, str | int],
    *,
    home_dir: Path,
    timeout_seconds: int,
) -> dict[str, str | int] | None:
    """Ask the source whether it works, until it does or time runs out.

    No pooling: this is a series of one-off connections to something that is
    not ready yet, and a pool would keep the failures.
    """
    kind = registry.get(adapter_type)
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    answered = dict(options)
    driver = kind.adapter_class
    if issubclass(driver, PinsServerKey) and driver.pinned_server_key(answered) is None:
        presented = await _first_server_key(driver, answered, deadline)
        if presented is None:
            logger.info("Service presented no key within %ds", timeout_seconds)
            return None
        for field in server_key_names(kind.options_schema):
            answered[field] = presented
    attempts = 0
    while True:
        attempts += 1
        adapter = build_adapter(kind, dict(answered), AdapterContext(home_dir=home_dir))
        result = await adapter.check_connection()
        if result.ok:
            logger.info("Service answered after %d attempts", attempts)
            return answered
        if asyncio.get_running_loop().time() >= deadline:
            logger.info("Service did not answer within %ds", timeout_seconds)
            return None
        await asyncio.sleep(INTERVAL_SECONDS)


async def _first_server_key(
    driver: type[PinsServerKey], options: Mapping[str, str | int], deadline: float
) -> str | None:
    """The key a server this application has just started presents, trusted
    without a person comparing it (D153).

    Asked until it answers, and once: OpenSSH shuts out an address that keeps
    leaving before it signs in, and asking for a key is exactly that. A port
    nothing listens on yet refuses without counting.
    """
    while True:
        try:
            return (await driver.presented_server_key(options)).public_key
        except AdapterError:
            if asyncio.get_running_loop().time() >= deadline:
                return None
        await asyncio.sleep(INTERVAL_SECONDS)


@runtime_checkable
class SampleDataFiller(Protocol):
    """Whether the source at these options was given something to look at.

    A protocol beside the readiness probe, and for the same reason: a job that
    only talks to fakes is a job a test can exercise without a database. The
    one implementation is below.
    """

    async def __call__(
        self,
        adapter_type: str,
        options: Mapping[str, Any],
        *,
        home_dir: Path,
    ) -> str | None: ...


async def install_sample_data(
    adapter_type: str,
    options: Mapping[str, Any],
    *,
    home_dir: Path,
) -> str | None:
    """Put this project's demonstration schema into a server that is ready.

    `None` when the source has no such capability, which is not a failure: the
    person asked for a database, and this is the part of the answer that
    source cannot give. A type that can answers with one line saying what is
    now in it (D2).
    """
    kind = registry.get(adapter_type)
    adapter = build_adapter(kind, dict(options), AdapterContext(home_dir=home_dir))
    if not isinstance(adapter, SupportsSampleData):
        return None
    written = await adapter.install_sample_data()
    logger.info("Sample data installed: %s", written)
    return written
