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

from dataclasses import dataclass
from typing import Annotated, Protocol, runtime_checkable

from fastapi import Depends, Request

from app.jobs.runner import JobFailed
from app.services.plan import ContainerSpec


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


@runtime_checkable
class ServiceEngine(Protocol):
    """What a container runtime must do: say whether it is there, and five verbs.

    Each verb takes names the server decided (D80) and returns nothing: what a
    container is doing is asked of the engine when somebody asks, rather than
    kept here.
    """

    async def availability(self) -> Availability: ...

    async def pull(self, image: str) -> None: ...

    async def create(self, spec: ContainerSpec) -> None: ...

    async def start(self, container: str) -> None: ...

    async def stop(self, container: str) -> None: ...

    async def restart(self, container: str) -> None: ...

    async def remove(self, container: str, *, volume: str | None) -> None: ...


NO_ENGINE_MESSAGE = "This server has no container runtime, so it cannot run services"
SWITCHED_OFF_MESSAGE = "Managed services are switched off on this server"


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
        return Availability(available=False, reason=self._reason)

    async def pull(self, image: str) -> None:
        raise EngineUnavailable(self._reason)

    async def create(self, spec: ContainerSpec) -> None:
        raise EngineUnavailable(self._reason)

    async def start(self, container: str) -> None:
        raise EngineUnavailable(self._reason)

    async def stop(self, container: str) -> None:
        raise EngineUnavailable(self._reason)

    async def restart(self, container: str) -> None:
        raise EngineUnavailable(self._reason)

    async def remove(self, container: str, *, volume: str | None) -> None:
        raise EngineUnavailable(self._reason)


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
