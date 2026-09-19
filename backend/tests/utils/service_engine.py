"""A container runtime a test can hold in its hand.

The engine is a protocol precisely so that the lifecycle can be exercised
without a daemon: this records what it was told, and can be made to refuse one
verb so that a failure is a thing a test arranges rather than waits for.
"""

import asyncio
from collections.abc import AsyncIterator, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any

from anyio import to_thread
from fastapi import FastAPI
from sqlmodel import delete, select

from app.connectors.models import Connector
from app.core.config import settings
from app.core.db import async_session_maker
from app.jobs.models import Job
from app.jobs.runner import JobRunner
from app.metrics.jobs import handlers as metrics_handlers
from app.services.backups import handlers as backup_handlers
from app.services.engine import (
    Availability,
    ContainerStatus,
    EngineError,
    LogLines,
    ServiceEngine,
)
from app.services.jobs import handlers
from app.services.models import ManagedService
from app.services.plan import ContainerSpec
from app.services.readiness import ReadinessProbe
from app.services.tools import ToolResult, ToolRun


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
        # What it will say is on the machine, by container name. Empty means a
        # runtime holding nothing, which is what a first creation meets.
        self.holds: dict[str, str] = {}
        self.printed: list[str] = []
        # A verb to stop on until something lets it go, so that a test about
        # cancelling is about cancelling rather than about who was faster.
        self.hold_on: str | None = None
        self.holding = asyncio.Event()
        # What port it will say the runtime gave a published container, if
        # any. The number is the runtime's answer everywhere, so a test that
        # wants one says it here rather than in a request.
        self.gives_port: int | None = None
        # What a program run in a container did, and where it wrote.
        self.ran: list[ToolRun] = []
        self.exit_code = 0
        self.writes: str | None = None

    async def availability(self) -> Availability:
        if self.available:
            return Availability(available=True, version="test")
        return Availability(available=False, reason="Not in this test")

    def _maybe_refuse(self, what: str) -> None:
        if self.refuse_on == what:
            raise EngineError(f"The engine would not {what}")

    async def _maybe_hold(self, what: str) -> None:
        if self.hold_on == what:
            self.holding.set()
            await asyncio.Event().wait()

    async def pull(self, image: str) -> None:
        self._maybe_refuse("pull")
        await self._maybe_hold("pull")
        self.pulled.append(image)

    async def create(self, spec: ContainerSpec) -> None:
        self._maybe_refuse("create")
        self.created.append(spec)
        self.holds[spec.name] = "created"


    async def start(self, container: str) -> None:
        self._maybe_refuse("start")
        self.started.append(container)
        self.holds[container] = "running"

    async def stop(self, container: str) -> None:
        self._maybe_refuse("stop")
        self.stopped.append(container)
        self.holds[container] = "stopped"

    async def restart(self, container: str) -> None:
        self._maybe_refuse("restart")
        self.restarted.append(container)

    async def remove(self, container: str, *, volume: str | None) -> None:
        self._maybe_refuse("remove")
        self.removed.append((container, volume))
        self.holds.pop(container, None)

    async def status(self, container: str) -> ContainerStatus:
        self._maybe_refuse("status")
        state = self.holds.get(container)
        if state is None:
            return ContainerStatus(name=container, state="missing")
        return ContainerStatus(
            name=container,
            state="running" if state == "running" else "stopped",
            published_port=self.gives_port,
        )

    async def managed(self) -> list[ContainerStatus]:
        self._maybe_refuse("managed")
        return [
            ContainerStatus(
                name=name,
                state="running" if state == "running" else "stopped",
                service_id=None,
            )
            for name, state in self.holds.items()
        ]

    async def logs(self, container: str, *, tail: int) -> LogLines:
        self._maybe_refuse("logs")
        return LogLines(lines=self.printed[-tail:])

    async def run_once(self, run: ToolRun) -> ToolResult:
        self._maybe_refuse("run_once")
        self.ran.append(run)
        if self.writes is not None:
            # A dump is a file: a fake that only recorded the request would
            # let a job pass that wrote nothing.
            await to_thread.run_sync(_write_a_file, Path(self.writes))
        return ToolResult(exit_code=self.exit_code, output=self.printed)


def probe_answering(ready: bool) -> Any:
    """A source that answers, or one that never does, without either existing."""

    async def probe(
        _adapter_type: str,
        options: Mapping[str, str | int],
        *,
        home_dir: Path,
        timeout_seconds: int,
    ) -> dict[str, str | int] | None:
        # The signature is the protocol's; what it is asked makes no
        # difference to an answer a test has already decided.
        del home_dir, timeout_seconds
        return dict(options) if ready else None

    return probe


class FakeFiller:
    """Sample data that is put in without a database to put it in.

    Records what it was asked to fill, so a test can say that an automatic
    start filled its server and a chosen one that said no did not.
    """

    def __init__(self, *, refuses: bool = False) -> None:
        self.filled: list[str] = []
        self.refuses = refuses

    async def __call__(
        self,
        adapter_type: str,
        _options: Mapping[str, Any],
        *,
        home_dir: Path,
    ) -> str | None:
        del home_dir
        if self.refuses:
            raise RuntimeError("no")
        self.filled.append(adapter_type)
        return "demo_lab: 12 tables"


@contextmanager
def engine_of(
    application: FastAPI,
    engine: ServiceEngine,
    *,
    ready: bool = True,
    network: str = "test-network",
    storage_volume: str = "test-storage",
    filler: FakeFiller | None = None,
    probe: ReadinessProbe | None = None,
) -> Iterator[None]:
    """Run the application as one that can start services, and put it back.

    Four things are swapped, because the work needs all four: an engine to do
    it, a network to be reachable on, something that says whether what was
    started answers, and somewhere a program may write.
    """
    saved_engine = application.state.service_engine
    saved_runner = application.state.job_runner
    saved_network = settings.SERVICE_NETWORK
    saved_storage = settings.SERVICE_STORAGE_VOLUME
    application.state.service_engine = engine
    answering = probe or probe_answering(ready)
    application.state.job_runner = JobRunner(
        {
            **handlers(engine, answering, filler or FakeFiller()),
            **backup_handlers(engine),
            **metrics_handlers(engine, answering),
        }
    )
    settings.SERVICE_NETWORK = network
    settings.SERVICE_STORAGE_VOLUME = storage_volume
    try:
        yield
    finally:
        application.state.service_engine = saved_engine
        application.state.job_runner = saved_runner
        settings.SERVICE_NETWORK = saved_network
        settings.SERVICE_STORAGE_VOLUME = saved_storage


@asynccontextmanager
async def running_with(
    application: FastAPI, engine: ServiceEngine
) -> AsyncIterator[None]:
    """The same, for a test that awaits inside it."""
    with engine_of(application, engine):
        yield


def _write_a_file(target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"a dump")

async def forget_services() -> None:
    """Take away every service a test made, and the connections they became.

    The connections matter as much as the rows: a service that reaches the end
    of its job leaves a real connector behind, and half a dozen of them called
    "PostgreSQL 1" make every other test that reads the connector table read a
    table full of ties.
    """
    async with async_session_maker() as session:
        services = list((await session.exec(select(ManagedService))).all())
        connector_ids = [
            service.connector_id
            for service in services
            if service.connector_id is not None
        ]
        await session.exec(delete(Job))
        await session.exec(delete(ManagedService))
        for connector_id in connector_ids:
            connector = await session.get(Connector, connector_id)
            if connector is not None:
                await session.delete(connector)
        await session.commit()
