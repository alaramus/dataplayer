"""Talking to a container runtime, over the socket this server was given.

The Docker Engine API is HTTP, and httpx speaks it over a Unix socket, so this
is a client rather than a dependency: one module, the requests this
application actually makes, and every answer reduced to something safe to show
(D82). The old application shelled out to `docker compose` with a command line
built by an f-string.

Nothing here knows what a service is. It is handed names and a specification
that were decided elsewhere (D80), and it does what it is told.
"""

import json
import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings
from app.services.engine import (
    Availability,
    ContainerState,
    ContainerStatus,
    EngineError,
    EngineUnavailable,
    LogLines,
)
from app.services.plan import SERVICE_LABEL, ContainerSpec
from app.services.tools import ToolResult, ToolRun

logger = logging.getLogger(__name__)

# How long to wait for the daemon to answer an ordinary command. A pull is not
# ordinary and has its own, because an image is somebody else's network.
COMMAND_TIMEOUT_SECONDS = 30.0
PULL_TIMEOUT_SECONDS = 900.0
# What "is anything there" is allowed to cost: this is asked while a person is
# waiting for a page, so it fails fast rather than truthfully.
PROBE_TIMEOUT_SECONDS = 2.0
# How long a program run in a container may take. A dump of a large database
# is minutes rather than seconds, and the job that owns it is what a person
# watches meanwhile.
TOOL_TIMEOUT_SECONDS = 3600.0
# How much of a program's output is kept for the answer. A failed `pg_dump`
# says why in one line; a successful one says nothing at all.
TOOL_OUTPUT_LINES = 40

# A container that stops on its own comes back, and one this application asked
# to stop stays stopped. `unless-stopped` is exactly that promise, and it is
# written here rather than in a template because it is a rule about every
# service this server keeps, not about what kind of thing one is.
RESTART_POLICY = "unless-stopped"

# What the daemon's own status codes mean, in words that describe the
# situation rather than the machine. The daemon's message names image
# digests, socket paths and directories of the host; none of it crosses.
_REFUSALS: Mapping[int, str] = {
    304: "It is already in that state",
    400: "The container runtime would not accept that request",
    403: "The container runtime refused: this server may not do that",
    404: "It is not there any more",
    409: "It is busy, or something with that name already exists",
    500: "The container runtime failed while doing it",
}


# How many lines of a container's output are ever fetched at once. A tail is
# for finding out why something did not start, not for reading a log file: a
# person who needs the whole thing has the machine it is on.
MAX_LOG_LINES = 500

# The eight-byte header the daemon puts in front of every chunk of a
# container's output when the container has no TTY. Nothing about it is
# optional and nothing about it is documented anywhere near the endpoint, so
# it is named here: one byte of stream, three of padding, four of length.
_LOG_HEADER = 8


@dataclass(frozen=True)
class _Answer:
    status: int
    body: bytes

    def json(self) -> Any:
        try:
            return json.loads(self.body)
        except ValueError:
            return None


class DockerEngine:
    """One installation's container runtime, reached over its socket.

    Built with a path rather than reaching for the environment, so a test
    hands it a transport and a deployment hands it a socket.
    """

    def __init__(
        self,
        socket_path: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._socket_path = socket_path
        # A test supplies its own transport; a deployment gets one that talks
        # to the socket. Either way the requests below are the same requests.
        self._transport = transport

    @asynccontextmanager
    async def _client(self, seconds: float) -> AsyncIterator[httpx.AsyncClient]:
        """A client for one exchange, held to httpx's own timeout.

        The bound belongs to the request rather than to a task wrapper: a
        timed-out HTTP call must close its connection, which the transport
        does and `asyncio.timeout` around it would not.
        """
        transport = self._transport or httpx.AsyncHTTPTransport(uds=self._socket_path)
        # The host name is a formality: the socket decides where this goes.
        async with httpx.AsyncClient(
            transport=transport, base_url="http://docker", timeout=seconds
        ) as client:
            yield client

    async def availability(self) -> Availability:
        """Whether there is a runtime here, and what it is.

        Asked while somebody waits for a page, so it is held to a short
        timeout and never raises: not being able to reach a daemon is an
        answer, not a failure.
        """
        try:
            async with self._client(PROBE_TIMEOUT_SECONDS) as client:
                response = await client.get("/version")
        except httpx.HTTPError:
            return Availability(
                available=False,
                reason="This server cannot reach a container runtime",
            )
        if response.status_code != 200:
            return Availability(
                available=False,
                reason="The container runtime did not answer as one",
            )
        version = response.json().get("Version")
        return Availability(available=True, version=str(version) if version else None)

    async def pull(self, image: str) -> None:
        """Fetch an image, and wait for the whole of it.

        The daemon answers 200 and then streams what it is doing, so an error
        arrives inside a successful response — reading the stream to the end
        is both how the pull completes and how a failure is noticed.
        """
        repository, _, tag = image.partition(":")
        async with self._client(PULL_TIMEOUT_SECONDS) as client:
            try:
                async with client.stream(
                    "POST",
                    "/images/create",
                    params={"fromImage": repository, "tag": tag or "latest"},
                ) as response:
                    if response.status_code >= 400:
                        await response.aread()
                        raise _refusal(response.status_code)
                    async for line in response.aiter_lines():
                        _refuse_if_the_stream_says_so(line)
            except httpx.HTTPError as failure:
                raise _unreachable(failure) from None

    async def create(self, spec: ContainerSpec) -> None:
        """Make the container, and the volume it keeps its data in.

        The volume first: a container created with a mount for a volume that
        does not exist would have one made for it with the daemon's defaults,
        and a volume this application made is one it can recognise later.
        """
        await self._request(
            "POST",
            "/volumes/create",
            json={"Name": spec.volume, "Labels": dict(spec.labels)},
            expected=(201,),
        )
        await self._request(
            "POST",
            "/containers/create",
            params={"name": spec.name},
            json=_creation_body(spec),
            expected=(201,),
        )

    async def start(self, container: str) -> None:
        # 304 is "already started", which is what was asked for.
        await self._request(
            "POST", f"/containers/{container}/start", expected=(204, 304)
        )

    async def stop(self, container: str) -> None:
        await self._request(
            "POST", f"/containers/{container}/stop", expected=(204, 304)
        )

    async def restart(self, container: str) -> None:
        await self._request("POST", f"/containers/{container}/restart", expected=(204,))

    async def remove(self, container: str, *, volume: str | None) -> None:
        """Take the container away, and the volume with it when asked.

        Both accept "it was not there" as success: removal is the one command
        whose goal is a state rather than an event, and a person retrying a
        half-finished removal must not be told off for the half that worked.

        What is removed is checked to be ours first. Names are predictable —
        template plus a service id — so a container of that name that this
        application did not make is a container it must not take away (D86).
        """
        found = await self.status(container)
        if found.state != "missing" and found.service_id is None:
            raise EngineError(
                "That container was not made by this application"
            )
        await self._request(
            "DELETE",
            f"/containers/{container}",
            params={"force": "true"},
            expected=(204, 404),
        )
        if volume is not None:
            await self._request(
                "DELETE", f"/volumes/{volume}", expected=(204, 404)
            )

    async def status(self, container: str) -> ContainerStatus:
        """What one container is doing, or that it is not there.

        Absence is an answer rather than an error: a service whose container
        somebody removed by hand is a state this application has to be able to
        show, and it is the whole point of asking.
        """
        answer = await self._request(
            "GET", f"/containers/{container}/json", expected=(200, 404)
        )
        if answer.status == 404:
            return ContainerStatus(name=container, state="missing")
        body = answer.json() or {}
        labels = (body.get("Config") or {}).get("Labels") or {}
        return ContainerStatus(
            name=container,
            state=_state_of(body.get("State") or {}),
            service_id=labels.get(SERVICE_LABEL),
        )

    async def managed(self) -> list[ContainerStatus]:
        """Every container on this machine that this application made.

        Matched by label rather than by name: a name is for a person to read
        and could be changed, and the point of this list is to find what no
        row claims any more (D84).
        """
        answer = await self._request(
            "GET",
            "/containers/json",
            params={
                "all": "true",
                "filters": json.dumps({"label": [SERVICE_LABEL]}),
            },
            expected=(200,),
        )
        found: list[ContainerStatus] = []
        for entry in answer.json() or []:
            names = entry.get("Names") or []
            labels = entry.get("Labels") or {}
            found.append(
                ContainerStatus(
                    # The daemon writes names with a leading slash.
                    name=str(names[0]).lstrip("/") if names else str(entry.get("Id")),
                    state="running" if entry.get("State") == "running" else "stopped",
                    service_id=labels.get(SERVICE_LABEL),
                )
            )
        return found

    async def logs(self, container: str, *, tail: int) -> LogLines:
        """The last lines a container printed, on both of its streams.

        The daemon multiplexes the two into one body with a header per chunk,
        so the header is stripped rather than shown: a person reading why
        PostgreSQL would not start should not have to read framing bytes.
        """
        answer = await self._request(
            "GET",
            f"/containers/{container}/logs",
            params={
                "stdout": "true",
                "stderr": "true",
                "tail": str(min(tail, MAX_LOG_LINES)),
            },
            expected=(200,),
        )
        return LogLines(lines=_demultiplexed(answer.body))

    async def run_once(self, run: ToolRun) -> ToolResult:
        """Run one program in one container, and take the container away.

        Create, start, wait, read, remove — in that order, and the removal
        happens whatever the program did, because a container kept for its
        exit code is a container nobody will ever look at again.
        """
        await self._request(
            "POST",
            "/containers/create",
            params={"name": run.name},
            json=_tool_body(run),
            expected=(201,),
        )
        try:
            await self._request(
                "POST", f"/containers/{run.name}/start", expected=(204, 304)
            )
            waited = await self._wait(run.name)
            output = await self.logs(run.name, tail=TOOL_OUTPUT_LINES)
        finally:
            await self._request(
                "DELETE",
                f"/containers/{run.name}",
                params={"force": "true"},
                expected=(204, 404),
            )
        return ToolResult(exit_code=waited, output=output.lines)

    async def _wait(self, container: str) -> int:
        """Block until the container exits, and answer with its code."""
        try:
            async with self._client(TOOL_TIMEOUT_SECONDS) as client:
                response = await client.post(f"/containers/{container}/wait")
        except httpx.HTTPError as failure:
            raise _unreachable(failure) from None
        if response.status_code != 200:
            raise _refusal(response.status_code)
        code = response.json().get("StatusCode")
        return int(code) if code is not None else 1

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        json: Any | None = None,
        expected: tuple[int, ...],
    ) -> _Answer:
        try:
            async with self._client(COMMAND_TIMEOUT_SECONDS) as client:
                response = await client.request(
                    method, path, params=params, json=json
                )
        except httpx.HTTPError as failure:
            raise _unreachable(failure) from None
        if response.status_code not in expected:
            # Logged with the daemon's own words, because they are useful to
            # whoever runs this server; answered without them, because they
            # name its paths and images.
            logger.warning(
                "Docker refused %s %s: %s %s",
                method,
                path,
                response.status_code,
                response.text[:500],
            )
            raise _refusal(response.status_code)
        return _Answer(status=response.status_code, body=response.content)


def _creation_body(spec: ContainerSpec) -> dict[str, Any]:
    """The container, as the Engine API wants it written.

    Everything in it comes from the specification, which came from a template
    and from what the server decided. There is no branch here on anything a
    request carried, because nothing a request carries reaches this far.
    """
    port = f"{spec.container_port}/tcp"
    host_config: dict[str, Any] = {
        "Mounts": [
            {
                "Type": "volume",
                "Source": spec.volume,
                "Target": spec.data_path,
            }
        ],
        "RestartPolicy": {"Name": RESTART_POLICY},
        # What it may take of the machine. Written here rather than in a
        # template because it is a rule about every service this server keeps,
        # and because a template that could choose its own limits could choose
        # none (D86).
        "Memory": settings.SERVICE_MEMORY_MB * 1024 * 1024,
        "NanoCpus": int(settings.SERVICE_CPUS * 1_000_000_000),
        "PidsLimit": settings.SERVICE_PIDS_LIMIT,
    }
    if spec.published_port is not None:
        # Bound to the loopback address rather than to every interface: a
        # database somebody asked this server to start is not a database they
        # asked it to publish to the network.
        host_config["PortBindings"] = {
            port: [{"HostIp": "127.0.0.1", "HostPort": str(spec.published_port)}]
        }
    body: dict[str, Any] = {
        "Image": spec.image,
        "Env": [f"{key}={value}" for key, value in sorted(spec.environment.items())],
        "Labels": dict(spec.labels),
        "ExposedPorts": {port: {}},
        "HostConfig": host_config,
    }
    if spec.command:
        body["Cmd"] = list(spec.command)
    if spec.network is not None:
        body["NetworkingConfig"] = {"EndpointsConfig": {spec.network: {}}}
    return body


def _refuse_if_the_stream_says_so(line: str) -> None:
    """A pull reports failure inside a stream the daemon called successful."""
    if not line.strip():
        return
    try:
        message = json.loads(line)
    except ValueError:
        return
    if isinstance(message, dict) and ("error" in message or "errorDetail" in message):
        logger.warning("Docker pull failed: %s", str(message)[:500])
        raise EngineError("The image could not be fetched")


def _refusal(status: int) -> EngineError:
    return EngineError(_REFUSALS.get(status, "The container runtime refused"))


def _unreachable(failure: httpx.HTTPError) -> EngineUnavailable:
    logger.warning("Docker is unreachable: %s", failure)
    return EngineUnavailable("This server cannot reach a container runtime")


def _state_of(state: Mapping[str, Any]) -> ContainerState:
    """The daemon's twelve words for what a container is doing, reduced to two.

    Everything that is not running is stopped as far as anything here is
    concerned: what a person does about `exited`, `dead` and `created` is the
    same thing.
    """
    return "running" if state.get("Running") else "stopped"


def _demultiplexed(body: bytes) -> list[str]:
    """The text out of the daemon's framed output.

    A container started without a TTY has its two streams interleaved with an
    eight-byte header in front of each chunk. A container with one has none,
    and its output is plain — so a body that does not parse as frames is
    returned as it stands rather than mangled.
    """
    if not body:
        return []
    text: list[bytes] = []
    at = 0
    while at + _LOG_HEADER <= len(body):
        stream = body[at]
        if stream not in (0, 1, 2):
            return _lines(body)
        size = int.from_bytes(body[at + 4 : at + _LOG_HEADER], "big")
        chunk = body[at + _LOG_HEADER : at + _LOG_HEADER + size]
        if len(chunk) != size:
            return _lines(body)
        text.append(chunk)
        at += _LOG_HEADER + size
    if at != len(body):
        return _lines(body)
    return _lines(b"".join(text))


def _lines(body: bytes) -> list[str]:
    decoded = body.decode("utf-8", errors="replace")
    return [line for line in decoded.splitlines() if line.strip()]


def _tool_body(run: ToolRun) -> dict[str, Any]:
    """One program, as the Engine API wants it written.

    No restart policy and no published port: this container exists to exit.
    The limits are the same ones a service is held to — a dump is not a reason
    to let something take the machine (D86).
    """
    body: dict[str, Any] = {
        "Image": run.image,
        "Cmd": list(run.argv),
        "Env": [f"{key}={value}" for key, value in sorted(run.environment.items())],
        "Labels": dict(run.labels),
        "HostConfig": {
            "Mounts": [
                {
                    "Type": "volume",
                    "Source": mount.volume,
                    "Target": mount.path,
                    "ReadOnly": mount.read_only,
                }
                for mount in run.mounts
            ],
            "Memory": settings.SERVICE_MEMORY_MB * 1024 * 1024,
            "NanoCpus": int(settings.SERVICE_CPUS * 1_000_000_000),
            "PidsLimit": settings.SERVICE_PIDS_LIMIT,
        },
    }
    if run.network is not None:
        body["NetworkingConfig"] = {"EndpointsConfig": {run.network: {}}}
    return body
