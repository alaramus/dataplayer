"""A container runtime a test can hold in its hand.

The engine is a protocol precisely so that the lifecycle can be exercised
without a daemon: this records what it was told, and can be made to refuse one
verb so that a failure is a thing a test arranges rather than waits for.
"""

from collections.abc import AsyncIterator, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from app.core.config import settings
from app.jobs.runner import JobRunner
from app.services.engine import Availability, EngineError, ServiceEngine
from app.services.jobs import handlers
from app.services.plan import ContainerSpec


class FakeEngine:
    """Does as it is told, and remembers what that was."""

    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.pulled: list[str] = []
        self.created: list[ContainerSpec] = []
        self.started: list[str] = []
        self.stopped: list[str] = []
        self.restarted: list[str] = []
        self.removed: list[tuple[str, str | None]] = []
        self.refuse_on: str | None = None

    async def availability(self) -> Availability:
        if self.available:
            return Availability(available=True, version="test")
        return Availability(available=False, reason="Not in this test")

    def _maybe_refuse(self, what: str) -> None:
        if self.refuse_on == what:
            raise EngineError(f"The engine would not {what}")

    async def pull(self, image: str) -> None:
        self._maybe_refuse("pull")
        self.pulled.append(image)

    async def create(self, spec: ContainerSpec) -> None:
        self._maybe_refuse("create")
        self.created.append(spec)

    async def start(self, container: str) -> None:
        self._maybe_refuse("start")
        self.started.append(container)

    async def stop(self, container: str) -> None:
        self._maybe_refuse("stop")
        self.stopped.append(container)

    async def restart(self, container: str) -> None:
        self._maybe_refuse("restart")
        self.restarted.append(container)

    async def remove(self, container: str, *, volume: str | None) -> None:
        self._maybe_refuse("remove")
        self.removed.append((container, volume))


def probe_answering(ready: bool) -> Any:
    """A source that answers, or one that never does, without either existing."""

    async def probe(
        _adapter_type: str,
        _options: Mapping[str, Any],
        *,
        home_dir: Path,
        timeout_seconds: int,
    ) -> bool:
        # The signature is the protocol's; what it is asked makes no
        # difference to an answer a test has already decided.
        del home_dir, timeout_seconds
        return ready

    return probe


@contextmanager
def engine_of(
    application: FastAPI,
    engine: ServiceEngine,
    *,
    ready: bool = True,
    network: str = "test-network",
) -> Iterator[None]:
    """Run the application as one that can start services, and put it back.

    Three things are swapped, because a service needs all three: an engine to
    do the work, a network to be reachable on, and something that says whether
    what was started answers.
    """
    saved_engine = application.state.service_engine
    saved_runner = application.state.job_runner
    saved_network = settings.SERVICE_NETWORK
    application.state.service_engine = engine
    application.state.job_runner = JobRunner(handlers(engine, probe_answering(ready)))
    settings.SERVICE_NETWORK = network
    try:
        yield
    finally:
        application.state.service_engine = saved_engine
        application.state.job_runner = saved_runner
        settings.SERVICE_NETWORK = saved_network


@asynccontextmanager
async def running_with(
    application: FastAPI, engine: ServiceEngine
) -> AsyncIterator[None]:
    """The same, for a test that awaits inside it."""
    with engine_of(application, engine):
        yield
