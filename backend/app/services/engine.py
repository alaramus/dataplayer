"""What a container runtime has to be able to do, and what happens without one.

A protocol rather than a class with a Docker client in it, for the reason the
adapters are protocols: the jobs that use it are the subject, and they must be
testable without a daemon. The one implementation here is the honest one for a
server that has no runtime at all — every method refuses, and says so in a
sentence a person can act on.

An engine's own errors never cross this boundary. A daemon names sockets,
image digests and paths on the machine it runs on; `EngineError` carries this
repository's words instead, which is the same rule the adapters follow for
driver text.
"""

import uuid
from dataclasses import dataclass
from typing import Annotated, Literal, Protocol, runtime_checkable

from fastapi import Depends, Request

from app.adapters.terminal import ConsoleProgram, Terminal, TerminalSize
from app.core.config import settings
from app.core.translation import N_, say
from app.jobs.runner import JobFailed
from app.services.plan import ContainerSpec
from app.services.tools import ToolResult, ToolRun
from app.terminals.consoles import ConsoleRefused


class EngineError(JobFailed):
    """The runtime could not do it, said safely.

    A `JobFailed` because that is exactly what it is: the message reaches the
    owner of the job, so it must already be fit to read.
    """


class EngineUnavailable(EngineError):
    """There is no container runtime to talk to."""


@dataclass(frozen=True)
class Availability:
    """Whether this server can run services at all, and why not when it cannot.

    A statement rather than an exception: "there is no runtime here" is an
    answer to a question somebody asked, and a screen showing what can be
    started needs it before anything is attempted (D82).
    """

    available: bool
    # In words a person can act on, and never the daemon's own: its text names
    # the sockets, images and directories of this machine.
    reason: str | None = None
    # What is there, when something is. Shown because a person deciding to
    # start a database may want to know what will run it.
    version: str | None = None


# What a container is doing, in the words this application uses rather than
# the daemon's twelve. Three, because three is what any decision here turns
# on: it is up, it is there and not up, or it is not there.
ContainerState = Literal["running", "stopped", "missing"]


@dataclass(frozen=True)
class ContainerStatus:
    """What the runtime says about one container it was asked about."""

    name: str
    state: ContainerState
    # The service id the container was labelled with, when it carries one.
    # This is how a container found on the machine is matched to a row, and
    # why the label rather than the name is what code matches on (D80).
    service_id: str | None = None
    # The port on the host it answers on, when it was published there at all.
    # Read off the container rather than asked for: the runtime picks a free
    # one, and this is where the answer comes back from.
    published_port: int | None = None


@dataclass(frozen=True)
class LogLines:
    """The tail of what a container has printed, and nothing else.

    A list rather than a stream: this is what a person reads after something
    went wrong, and a follow-along stream is a socket, a bound and a decision
    about back-pressure that nobody has asked for yet.
    """

    lines: list[str]


@runtime_checkable
class ServiceEngine(Protocol):
    """What a container runtime must do, from this application's side.

    Each verb takes names the server decided (D80). What a container is doing
    is asked of the engine when somebody asks rather than kept here, because
    a container can stop without this application being told.
    """

    async def availability(self) -> Availability: ...

    async def pull(self, image: str) -> None: ...

    async def create(self, spec: ContainerSpec) -> None: ...

    async def start(self, container: str) -> None: ...

    async def stop(self, container: str) -> None: ...

    async def restart(self, container: str) -> None: ...

    async def remove(self, container: str, *, volume: str | None) -> None: ...

    async def status(self, container: str) -> ContainerStatus: ...

    async def managed(self) -> list[ContainerStatus]: ...

    async def logs(self, container: str, *, tail: int) -> LogLines: ...

    async def run_once(self, run: ToolRun) -> ToolResult: ...


# Chosen at assembly, where no request is: English, worded where it is said.
NO_ENGINE_MESSAGE = N_(
    "This server has no container runtime, so it cannot run services"
)
SWITCHED_OFF_MESSAGE = N_("Managed services are switched off on this server")


class NoEngine:
    """The engine of a server that will not start containers.

    Not a stub standing in for something unfinished: it is the truth about a
    deployment where services are switched off or no runtime is reachable, and
    every job it is asked to do fails at its first step with a sentence rather
    than a traceback.

    The reason is carried rather than fixed, because the two situations are
    different and a person can act on only one of them.
    """

    def __init__(self, reason: str = NO_ENGINE_MESSAGE) -> None:
        self._reason = reason

    async def availability(self) -> Availability:
        return Availability(available=False, reason=say(self._reason))

    async def pull(self, image: str) -> None:
        raise EngineUnavailable(say(self._reason))

    async def create(self, spec: ContainerSpec) -> None:
        raise EngineUnavailable(say(self._reason))

    async def start(self, container: str) -> None:
        raise EngineUnavailable(say(self._reason))

    async def stop(self, container: str) -> None:
        raise EngineUnavailable(say(self._reason))

    async def restart(self, container: str) -> None:
        raise EngineUnavailable(say(self._reason))

    async def remove(self, container: str, *, volume: str | None) -> None:
        raise EngineUnavailable(say(self._reason))

    async def status(self, container: str) -> ContainerStatus:
        raise EngineUnavailable(say(self._reason))

    async def managed(self) -> list[ContainerStatus]:
        raise EngineUnavailable(say(self._reason))

    async def logs(self, container: str, *, tail: int) -> LogLines:
        raise EngineUnavailable(say(self._reason))

    async def run_once(self, run: ToolRun) -> ToolResult:
        raise EngineUnavailable(say(self._reason))

    async def open_console(
        self, program: ConsoleProgram, size: TerminalSize, *, owner: uuid.UUID
    ) -> Terminal:
        raise ConsoleRefused(say(self._reason))


def get_engine(request: Request) -> ServiceEngine:
    """The engine of the running application.

    Through the application rather than a module global, for the same reason
    the resource store and the job runner are: what outlives a request belongs
    to the application.
    """
    engine = request.app.state.service_engine
    if not isinstance(engine, ServiceEngine):
        raise RuntimeError("The application has no engine; is the lifespan running?")
    return engine


ServiceEngineDep = Annotated[ServiceEngine, Depends(get_engine)]


# What a server without a network can say. Reaching a service is reaching a
# container by name, and a name resolves only on a network they share, so a
# service that could be started and not reached is not offered at all.
NO_NETWORK_MESSAGE = N_("This server has no network to put a service on")


async def service_offer(engine: ServiceEngine) -> Availability:
    """Whether a service could be started here and then used.

    The runtime first, because it is the more fundamental answer, and the
    network second: a server that cannot reach what it starts is offering
    something nobody could open.
    """
    runtime = await engine.availability()
    if not runtime.available:
        return runtime
    if not settings.SERVICE_NETWORK:
        return Availability(available=False, reason=say(NO_NETWORK_MESSAGE))
    return runtime
