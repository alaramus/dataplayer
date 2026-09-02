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

from typing import Protocol, runtime_checkable

from app.jobs.runner import JobFailed
from app.services.plan import ContainerSpec


class EngineError(JobFailed):
    """The runtime could not do it, said safely.

    A `JobFailed` because that is exactly what it is: the message reaches the
    owner of the job, so it must already be fit to read.
    """


class EngineUnavailable(EngineError):
    """There is no container runtime to talk to."""


@runtime_checkable
class ServiceEngine(Protocol):
    """The five things a service's life is made of.

    Each takes names the server decided (D80) and returns nothing: what a
    container is doing is asked of the engine when somebody asks, rather than
    kept here.
    """

    async def pull(self, image: str) -> None: ...

    async def create(self, spec: ContainerSpec) -> None: ...

    async def start(self, container: str) -> None: ...

    async def stop(self, container: str) -> None: ...

    async def restart(self, container: str) -> None: ...

    async def remove(self, container: str, *, volume: str | None) -> None: ...


NO_ENGINE_MESSAGE = "This server has no container runtime, so it cannot run services"


class NoEngine:
    """The engine of a server that cannot start containers.

    Not a stub standing in for something unfinished: it is the truth about a
    deployment without access to a runtime, and it is what the application
    runs with until one is detected. Every job it is asked to do fails at its
    first step with a sentence rather than a traceback.
    """

    async def pull(self, image: str) -> None:
        raise EngineUnavailable(NO_ENGINE_MESSAGE)

    async def create(self, spec: ContainerSpec) -> None:
        raise EngineUnavailable(NO_ENGINE_MESSAGE)

    async def start(self, container: str) -> None:
        raise EngineUnavailable(NO_ENGINE_MESSAGE)

    async def stop(self, container: str) -> None:
        raise EngineUnavailable(NO_ENGINE_MESSAGE)

    async def restart(self, container: str) -> None:
        raise EngineUnavailable(NO_ENGINE_MESSAGE)

    async def remove(self, container: str, *, volume: str | None) -> None:
        raise EngineUnavailable(NO_ENGINE_MESSAGE)
